import os
import tempfile
import logging
import openai
from gtts import gTTS
from dotenv import load_dotenv
from pydub import AudioSegment
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)
from deep_translator import GoogleTranslator
from langdetect import detect
import asyncio

# === CONFIGURAZIONE ===
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
logging.basicConfig(level=logging.INFO)

# === UTENTI CON TRADUZIONE FORZATA ===
forced_uk_users = set()
forced_ru_users = set()

# === FUNZIONE TRADUZIONE + RISPOSTA VOCALE ===
async def translate_and_reply(update: Update, text: str):
    try:
        source_lang = detect(text)
    except:
        await update.message.reply_text("❌ Non riesco a rilevare la lingua.")
        return

    if source_lang == 'uk':
        target_lang = 'it'
    elif source_lang == 'ru':
        target_lang = 'it'
    elif source_lang == 'it':
        target_lang = 'uk'
    else:
        await update.message.reply_text("❌ Posso tradurre solo tra italiano, ucraino e russo.")
        return

    translated = GoogleTranslator(source='auto', target=target_lang).translate(text)

    await update.message.reply_text(
        f"📝 Testo rilevato ({source_lang}): {text.strip()}\n\n🔁 Traduzione ({target_lang}): {translated.strip()}"
    )

    tts = gTTS(translated, lang=target_lang)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as audio_file:
        tts.save(audio_file.name)
        with open(audio_file.name, 'rb') as voice_file:
            await update.message.reply_voice(voice=voice_file)
        os.remove(audio_file.name)

# === GESTIONE TESTO ===
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        return
    await translate_and_reply(update, update.message.text)

# === GESTIONE VOCALE ===
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        return

    logging.info("🎙️ Ricevuto vocale, inizio download...")

    try:
        file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_file:
            await file.download_to_drive(ogg_file.name)
            ogg_path = ogg_file.name
            logging.info(f"✅ File scaricato: {ogg_path}")

        mp3_path = ogg_path.replace(".ogg", ".mp3")
        AudioSegment.converter = "/usr/bin/ffmpeg"
        AudioSegment.from_ogg(ogg_path).export(mp3_path, format="mp3")
        logging.info(f"🎧 Convertito in MP3: {mp3_path}")

        openai.api_key = OPENAI_API_KEY
        user_id = update.message.from_user.id

        with open(mp3_path, "rb") as audio_file:
            if user_id in forced_uk_users:
                transcript = openai.Audio.transcribe("whisper-1", audio_file, language="uk")
            elif user_id in forced_ru_users:
                transcript = openai.Audio.transcribe("whisper-1", audio_file, language="ru")
            else:
                transcript = openai.Audio.transcribe("whisper-1", audio_file)

        logging.info(f"📜 Testo trascritto: {transcript['text']}")
        os.remove(ogg_path)
        os.remove(mp3_path)

        await translate_and_reply(update, transcript["text"])

    except Exception as e:
        logging.error(f"❌ Errore durante la trascrizione cloud: {e}")
        await update.message.reply_text("⚠️ Errore durante la trascrizione del vocale.")

# === COMANDI PER FORZARE LINGUA ===
async def force_uk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    forced_uk_users.add(user_id)
    forced_ru_users.discard(user_id)
    await update.message.reply_text("✅ Da ora i tuoi vocali saranno trascritti come *ucraini*.")

async def force_ru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    forced_ru_users.add(user_id)
    forced_uk_users.discard(user_id)
    await update.message.reply_text("✅ Da ora i tuoi vocali saranno trascritti come *russi*.")

async def auto_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    forced_uk_users.discard(user_id)
    forced_ru_users.discard(user_id)
    await update.message.reply_text("✅ Da ora verrà usato il rilevamento automatico della lingua.")

# === COMANDO /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["/forzauk", "/forzarusso", "/autolingua"]]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=False
    )

    await update.message.reply_text(
        "👋 Benvenuto!\nInviami un messaggio o un vocale in italiano, ucraino o russo.\n"
        "Ti risponderò con la traduzione e la voce nella lingua corretta.\n\n"
        "➡️ /forzauk = forza vocale come ucraino\n"
        "➡️ /forzarusso = forza vocale come russo\n"
        "➡️ /autolingua = torna al rilevamento automatico",
        reply_markup=reply_markup
    )

# === AVVIO ASINCRONO CON RE-REGISTRAZIONE WEBHOOK ===
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("forzauk", force_uk))
    app.add_handler(CommandHandler("forzarusso", force_ru))
    app.add_handler(CommandHandler("autolingua", auto_lang))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Rimuove e reimposta il webhook (fix standby Render)
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.bot.set_webhook(f"{RENDER_EXTERNAL_URL}")

    port = int(os.environ.get("PORT", 5000))

    await app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="/",
        webhook_url=f"{RENDER_EXTERNAL_URL}",
        allowed_updates=Update.ALL_TYPES,
    )

if __name__ == "__main__":
    asyncio.run(main())
