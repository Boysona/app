import telebot
import logging
import os
from datetime import datetime
from flask import Flask, request

BOT_TOKEN = "7770743573:AAFtj6Eq-laEzWgK0vG7qc6bqy6r-Te4fLk"
WEBHOOK_URL_BASE = "top-selene-cadenuux57-5d5cdd61.koyeb.app/"
WEBHOOK_URL_PATH = f"/{BOT_TOKEN}"
WEBHOOK_URL = WEBHOOK_URL_BASE + WEBHOOK_URL_PATH
PORT = int(os.environ.get("PORT", 8443))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
bot_start_time = None

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def set_bot_info_and_startup():
    global bot_start_time
    bot_start_time = datetime.now()
    try:
        # Full description (English)
        bot.set_my_description(
            "This bot can transcribe and summarize (voice messages, audio files, or videos) quickly and accurately for free"
        )
        # Short description (English)
        bot.set_my_short_description(
            "Transcribe and Summarize your audio and video in seconds totally free\n\nFor help? Contact: @boyso20"
        )
        # English version with language_code
        bot.set_my_description(
            "This bot can transcribe and summarize (voice messages, audio files, or videos) quickly and accurately for free",
            language_code="en"
        )
        bot.set_my_short_description(
            "Transcribe and Summarize your audio and video in seconds totally free\n\nFor help? Contact: @boyso20",
            language_code="en"
        )
        # Arabic version
        bot.set_my_description(
            " هذا البوت يستطيع نسخ وتلخيص (الرسائل الصوتية، الملفات الصوتية أو مقاطع الفيديو) بسرعة وبدقة مجانًا.",
            language_code="ar"
        )
        bot.set_my_short_description(
            " انسخ ولخص الصوتيات والفيديو مجانًا خلال ثوانٍ.\nللمساعدة: @boyso20",
            language_code="ar"
        )

        # --- New languages added below ---
        # Spanish version
        bot.set_my_description(
            "Este bot puede transcribir y resumir (mensajes de voz, archivos de audio o videos) rápida y precisamente de forma gratuita.",
            language_code="es"
        )
        bot.set_my_short_description(
            "Transcribe y resume tu audio y video en segundos totalmente gratis\n\n¿Ayuda? Contacto: @boyso20",
            language_code="es"
        )

        # Uzbek version (Latin)
        bot.set_my_description(
            " Ushbu bot ovozli xabarlar, audio fayllar yoki videolarni tez va aniq transkribe qilib, xulosalashi mumkin — bepul.",
            language_code="uz"
        )
        bot.set_my_short_description(
            "Ovoz va videongizni soniyalar ichida transkribe va xulosa qiling, butunlay bepul\n\nYordam: @boyso20",
            language_code="uz"
        )

        # Persian / Farsi version
        bot.set_my_description(
            "این ربات می‌تواند پیام‌های صوتی، فایل‌های صوتی یا ویدیوها را به سرعت و با دقت رونویسی و خلاصه کند — رایگان.",
            language_code="fa"
        )
        bot.set_my_short_description(
            " صوت و ویدیوهای خود را در عرض چند ثانیه رایگان رونویسی و خلاصه کنید.\nکمک: @boyso20",
            language_code="fa"
        )
        # --- end new languages ---

        bot.delete_my_commands()
        logging.info("Bot info updated with English, Arabic, Spanish, Uzbek and Persian descriptions.")
    except Exception as e:
        logging.error(f"Failed to set bot info: {e}")

@bot.message_handler(content_types=["text"])
def default_handler(message):
    bot.reply_to(
        message,
        "👋 Send me any text and I will convert it into speech using Microsoft Edge TTS."
    )

@bot.message_handler(content_types=["voice", "audio", "video"])
def media_handler(message):
    bot.reply_to(message, "⏳ Processing your media...")
    text = fake_tts()
    bot.send_message(message.chat.id, text)

def fake_tts():
    return "🔊 (Here is where the generated speech/audio will be returned — add TTS engine later)."

@app.route(WEBHOOK_URL_PATH, methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return "", 200
    else:
        return "Bad Request", 403

if __name__ == "__main__":
    set_bot_info_and_startup()
    try:
        bot.remove_webhook()
        logging.info("Webhook removed successfully.")
    except Exception as e:
        logging.error(f"Failed to remove webhook: {e}")

    try:
        bot.set_webhook(url=WEBHOOK_URL)
        logging.info(f"Webhook set successfully to URL: {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Failed to set webhook: {e}")

    app.run(host="0.0.0.0", port=PORT)
