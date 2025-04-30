import os
import tempfile
import logging
import whisper
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

# === CONFIGURAZIONE ===
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
model = whisper.load_model("tiny")  # più leggero per Render
logging.basicConfig(level=logging.INFO)

# === FUNZIONE TRADUZIONE + RISPOSTA VOCALE ===
async def translate_and_reply(update: Update, text: str):
    try:
        source_lang = detect(text)
    except:
        await update.message.reply_text("❌ Non riesco a rilevare la lingua.")
        return

    if source_lang == 'uk':
        target_lang = 'it'
    elif source_lang == 'it':
        target_lang = 'uk'
    else:
        target_lang = 'uk'

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

# === GESTIONE VOCALE CON LOG ===
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

        wav_path = ogg_path.replace(".ogg", ".wav")
        AudioSegment.converter = "/usr/bin/ffmpeg"  # Percorso statico per Render
        AudioSegment.from_ogg(ogg_path).export(wav_path, format="wav")
        logging.info(f"🎧 Convertito in WAV: {wav_path}")

        result = model.transcribe(wav_path)
        logging.info(f"📜 Testo trascritto: {result['text']}")

        os.remove(ogg_path)
        os.remove(wav_path)

        await translate_and_reply(update, result["text"])
    except Exception as e:
        logging.error(f"❌ Errore nella gestione del vocale: {e}")
        await update.message.reply_text("⚠️ Errore durante l'elaborazione del vocale.")

# === COMANDO /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["/start"]]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=False
    )

    await update.message.reply_text(
        "👋 Benvenuto!\nInviami un messaggio o un vocale in italiano o ucraino.\n"
        "Ti risponderò con la traduzione e la voce nella lingua corretta.",
        reply_markup=reply_markup
    )

# === AVVIO BOT PER RENDER.COM (webhook) ===
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    port = int(os.environ.get("PORT", 5000))
    webhook_url = os.environ.get("RENDER_EXTERNAL_URL")

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=f"{webhook_url}"
    )

if __name__ == "__main__":
    main()
