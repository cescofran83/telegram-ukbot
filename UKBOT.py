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
model = whisper.load_model("tiny")
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

    # Voce nella lingua tradotta
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

    file = await update.message.voice.get_file()
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_file:
        await file.download_to_drive(ogg_file.name)
        ogg_path = ogg_file.name

    wav_path = ogg_path.replace(".ogg", ".wav")
    AudioSegment.from_ogg(ogg_path).export(wav_path, format="wav")
    result = model.transcribe(wav_path)
    os.remove(ogg_path)
    os.remove(wav_path)

    await translate_and_reply(update, result["text"])

# === COMANDO /start CON TASTIERA VISIBILE ===
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

# === AVVIO BOT PER RENDER ===
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
