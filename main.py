import os
import logging
import requests
import telebot
import json
from flask import Flask, request, abort, render_template_string, jsonify
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import threading
import time
import io
from pymongo import MongoClient
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import subprocess
import tempfile
import glob
import math
import speech_recognition as sr
from concurrent.futures import ThreadPoolExecutor
import re
from collections import Counter
import wave
import google.generativeai as genai

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CHUNK_DURATION_SEC = int(os.environ.get("CHUNK_DURATION_SEC", "55"))
CHUNK_BATCH_SIZE = int(os.environ.get("CHUNK_BATCH_SIZE", "20"))
CHUNK_BATCH_PAUSE_SEC = int(os.environ.get("CHUNK_BATCH_PAUSE_SEC", "5"))
RECOGNITION_MAX_RETRIES = int(os.environ.get("RECOGNITION_MAX_RETRIES", "3"))
RECOGNITION_RETRY_WAIT = int(os.environ.get("RECOGNITION_RETRY_WAIT", "3"))
AUDIO_SAMPLE_RATE = int(os.environ.get("AUDIO_SAMPLE_RATE", "16000"))
AUDIO_CHANNELS = int(os.environ.get("AUDIO_CHANNELS", "1"))
TELEGRAM_MAX_BYTES = int(os.environ.get("TELEGRAM_MAX_BYTES", str(20 * 1024 * 1024)))
MAX_WEB_UPLOAD_MB = int(os.environ.get("MAX_WEB_UPLOAD_MB", "250"))
REQUEST_TIMEOUT_TELEGRAM = int(os.environ.get("REQUEST_TIMEOUT_TELEGRAM", "300"))
REQUEST_TIMEOUT_LLM = int(os.environ.get("REQUEST_TIMEOUT_LLM", "60"))
TRANSCRIBE_MAX_WORKERS = int(os.environ.get("TRANSCRIBE_MAX_WORKERS", "4"))
PREPEND_SILENCE_SEC = int(os.environ.get("PREPEND_SILENCE_SEC", "5"))
AMBIENT_CALIB_SEC = float(os.environ.get("AMBIENT_CALIB_SEC", "3"))
REQUEST_TIMEOUT_GEMINI = int(os.environ.get("REQUEST_TIMEOUT_GEMINI", "300"))
REQUEST_TIMEOUT_ASSEMBLY = int(os.environ.get("REQUEST_TIMEOUT_ASSEMBLY", "180"))
ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY", "f692ac671b6e4d388e53f445f0d7d686")
BOT_TOKENS = [
    "7770743573:AAEhVz2jKwdJjhrm3XH0bAhhLucg2H4AvMY",
    "7790991731:AAF4NHGm0BJCf08JTdBaUWKzwfs82_Y9Ecw",
]
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyB1HVBY1a8XGE3bijTNJVBO1W759yK5KGc")
WEBHOOK_BASE = os.environ.get("WEBHOOK_BASE", "https://usual-daffie-cadenuux57-87ddad45.koyeb.app/")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6964068910"))
SECRET_KEY = os.environ.get("SECRET_KEY", "super-secret-please-change")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://hoskasii:GHyCdwpI0PvNuLTg@cluster0.dy7oe7t.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
DB_NAME = os.environ.get("DB_NAME", "telegram_bot_db")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
users_collection = db["users"]
groups_collection = db["groups"]

app = Flask(__name__)

bots = []
for token in BOT_TOKENS:
    bots.append(telebot.TeleBot(token, threaded=True, parse_mode='HTML'))

serializer = URLSafeTimedSerializer(SECRET_KEY)

LANG_OPTIONS = [
    ("🇬🇧 English", "en"),
    ("🇸🇦 العربية", "ar"),
    ("🇪🇸 Español", "es"),
    ("🇫🇷 Français", "fr"),
    ("🇷🇺 Русский", "ru"),
    ("🇩🇪 Deutsch", "de"),
    ("🇮🇳 हिन्दी", "hi"),
    ("🇮🇷 فارسی", "fa"),
    ("🇮🇩 Indonesia", "id"),
    ("🇺🇦 Українська", "uk"),
    ("🇦🇿 Azərbaycan", "az"),
    ("🇮🇹 Italiano", "it"),
    ("🇹🇷 Türkçe", "tr"),
    ("🇧🇬 Български", "bg"),
    ("🇷🇸 Srpski", "sr"),
    ("🇵🇰 اردو", "ur"),
    ("🇹🇭 ไทย", "th"),
    ("🇻🇳 Tiếng Việt", "vi"),
    ("🇯🇵 日本語", "ja"),
    ("🇰🇷 한국어", "ko"),
    ("🇨🇳 中文", "zh"),
    ("🇳🇱 Nederlands", "nl"),
    ("🇸🇪 Svenska", "sv"),
    ("🇳🇴 Norsk", "no"),
    ("🇮🇱 עברית", "he"),
    ("🇩🇰 Dansk", "da"),
    ("🇪🇹 አማርኛ", "am"),
    ("🇫🇮 Suomi", "fi"),
    ("🇧🇩 বাংলা", "bn"),
    ("🇰🇪 Kiswahili", "sw"),
    ("🇪🇹 Oromoo", "om"),
    ("🇳🇵 नेपाली", "ne"),
    ("🇵🇱 Polski", "pl"),
    ("🇬🇷 Ελληνικά", "el"),
    ("🇨🇿 Čeština", "cs"),
    ("🇮🇸 Íslenska", "is"),
    ("🇱🇹 Lietuvių", "lt"),
    ("🇱🇻 Latviešu", "lv"),
    ("🇭🇷 Hrvatski", "hr"),
    ("🇷🇸 Bosanski", "bs"),
    ("🇭🇺 Magyar", "hu"),
    ("🇷🇴 Română", "ro"),
    ("🇸🇴 Somali", "so"),
    ("🇲🇾 Melayu", "ms"),
    ("🇺🇿 O'zbekcha", "uz"),
    ("🇵🇭 Tagalog", "tl"),
    ("🇵🇹 Português", "pt"),
]

CODE_TO_LABEL = {code: label for (label, code) in LANG_OPTIONS}
LABEL_TO_CODE = {label: code for (label, code) in LANG_OPTIONS}

STT_LANGUAGES = {}
for label, code in LANG_OPTIONS:
    STT_LANGUAGES[label.split(" ", 1)[-1]] = {
        "code": code,
        "emoji": label.split(" ", 1)[0],
        "native": label.split(" ", 1)[-1]
    }

user_transcriptions = {}
memory_lock = threading.Lock()
in_memory_data = {"pending_media": {}}
admin_broadcast_state = {}

ALLOWED_EXTENSIONS = {
    "mp3", "wav", "m4a", "ogg", "webm", "flac", "mp4", "mkv", "avi", "mov", "hevc", "aac", "aiff", "amr", "wma", "opus", "m4v", "ts", "flv", "3gp"
}

FFMPEG_ENV = os.environ.get("FFMPEG_BINARY", "")
POSSIBLE_FFMPEG_PATHS = [FFMPEG_ENV, "./ffmpeg", "/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "ffmpeg"]
FFMPEG_BINARY = None
for p in POSSIBLE_FFMPEG_PATHS:
    if not p:
        continue
    try:
        subprocess.run([p, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        FFMPEG_BINARY = p
        break
    except Exception:
        continue
if FFMPEG_BINARY is None:
    logging.warning("ffmpeg binary not found. Set FFMPEG_BINARY env var or place ffmpeg in ./ffmpeg or /usr/bin/ffmpeg")

ASSEMBLY_LANG_SET = {"en", "ar", "es", "fr", "ru", "de", "hi", "fa", "zh", "ko", "ja", "it", "uk"}

def update_user_activity(user_id: int):
    user_id_str = str(user_id)
    now = datetime.now()
    users_collection.update_one(
        {"_id": user_id_str},
        {"$set": {"last_active": now}, "$setOnInsert": {"first_seen": now, "stt_conversion_count": 0}},
        upsert=True
    )

def increment_processing_count(user_id: str, service_type: str):
    field_to_inc = f"{service_type}_conversion_count"
    users_collection.update_one(
        {"_id": str(user_id)},
        {"$inc": {field_to_inc: 1}}
    )

def get_stt_user_lang(user_id: str) -> str:
    user_data = users_collection.find_one({"_id": user_id})
    if user_data and "stt_language" in user_data:
        return user_data["stt_language"]
    return "en"

def set_stt_user_lang(user_id: str, lang_code: str):
    users_collection.update_one(
        {"_id": user_id},
        {"$set": {"stt_language": lang_code}},
        upsert=True
    )

def user_has_stt_setting(user_id: str) -> bool:
    user_data = users_collection.find_one({"_id": user_id})
    return user_data is not None and "stt_language" in user_data

def save_pending_media(user_id: str, media_type: str, data: dict):
    with memory_lock:
        in_memory_data["pending_media"][user_id] = {
            "media_type": media_type,
            "data": data,
            "saved_at": datetime.now()
        }

def pop_pending_media(user_id: str):
    with memory_lock:
        return in_memory_data["pending_media"].pop(user_id, None)

def delete_transcription_later(user_id: str, message_id: int):
    time.sleep(600)
    with memory_lock:
        if user_id in user_transcriptions and message_id in user_transcriptions[user_id]:
            del user_transcriptions[user_id][message_id]

def select_speech_model_for_lang(language_code: str):
    return "universal"

def is_transcoding_like_error(msg: str) -> bool:
    if not msg:
        return False
    m = msg.lower()
    checks = [
        "transcoding failed",
        "file does not appear to contain audio",
        "text/html",
        "html document",
        "unsupported media type",
        "could not decode",
    ]
    return any(ch in m for ch in checks)

def build_lang_keyboard(callback_prefix: str, row_width: int = 3, message_id: int = None):
    markup = InlineKeyboardMarkup(row_width=row_width)
    buttons = []
    for label, code in LANG_OPTIONS:
        if message_id is not None:
            cb = f"{callback_prefix}|{code}|{message_id}"
        else:
            cb = f"{callback_prefix}|{code}"
        buttons.append(InlineKeyboardButton(label, callback_data=cb))
    for i in range(0, len(buttons), row_width):
        markup.add(*buttons[i:i+row_width])
    return markup

def build_admin_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Send Broadcast", callback_data="admin_send_broadcast"))
    markup.add(InlineKeyboardButton("Total Users", callback_data="admin_total_users"))
    return markup

def signed_upload_token(chat_id: int, lang_code: str, bot_index: int = 0):
    payload = {"chat_id": chat_id, "lang": lang_code, "bot_index": int(bot_index)}
    return serializer.dumps(payload)

def unsign_upload_token(token: str, max_age_seconds: int = 3600):
    data = serializer.loads(token, max_age=max_age_seconds)
    return data

def animate_processing_message(bot_obj, chat_id, message_id, stop_event):
    dots = [".", "..", "..."]
    idx = 0
    while not stop_event():
        try:
            bot_obj.edit_message_text(f"🔄 Processing {dots[idx % len(dots)]}", chat_id=chat_id, message_id=message_id)
        except Exception:
            pass
        idx = (idx + 1) % len(dots)
        time.sleep(0.6)

def normalize_text_offline(text: str) -> str:
    if not text:
        return text
    t = re.sub(r'\s+', ' ', text).strip()
    return t

def safe_extension_from_filename(filename: str):
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()

def telegram_file_stream(file_url, chunk_size=256*1024):
    with requests.get(file_url, stream=True, timeout=REQUEST_TIMEOUT_TELEGRAM) as r:
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                yield chunk

def telegram_file_info_and_url(bot_token: str, file_id):
    import urllib.request
    url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
    resp = requests.get(url, timeout=REQUEST_TIMEOUT_TELEGRAM)
    resp.raise_for_status()
    j = resp.json()
    file_path = j.get("result", {}).get("file_path")
    file_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    class Dummy:
        pass
    d = Dummy()
    d.file_path = file_path
    return d, file_url

def convert_to_wav(input_path: str, output_wav_path: str):
    if FFMPEG_BINARY is None:
        raise RuntimeError("ffmpeg binary not found")
    cmd = [
        FFMPEG_BINARY,
        "-y",
        "-i",
        input_path,
        "-ar",
        str(AUDIO_SAMPLE_RATE),
        "-ac",
        str(AUDIO_CHANNELS),
        output_wav_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

def get_wav_duration(wav_path: str) -> float:
    with wave.open(wav_path, 'rb') as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / float(rate)

def prepend_silence_to_wav(original_wav: str, output_wav: str, silence_sec: int):
    if FFMPEG_BINARY is None:
        raise RuntimeError("ffmpeg binary not found")
    tmp_dir = os.path.dirname(output_wav) or tempfile.gettempdir()
    silence_file = os.path.join(tmp_dir, f"silence_{int(time.time()*1000)}.wav")
    cmd_create_silence = [
        FFMPEG_BINARY,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=channel_layout=mono:sample_rate={AUDIO_SAMPLE_RATE}",
        "-t",
        str(silence_sec),
        "-ar",
        str(AUDIO_SAMPLE_RATE),
        "-ac",
        str(AUDIO_CHANNELS),
        silence_file
    ]
    subprocess.run(cmd_create_silence, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    cmd_concat = [
        FFMPEG_BINARY,
        "-y",
        "-i",
        silence_file,
        "-i",
        original_wav,
        "-filter_complex",
        "[0:0][1:0]concat=n=2:v=0:a=1[out]",
        "-map",
        "[out]",
        output_wav
    ]
    subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    try:
        os.remove(silence_file)
    except Exception:
        pass

def split_wav_to_chunks(wav_path: str, out_dir: str, chunk_duration_sec: int):
    if FFMPEG_BINARY is None:
        raise RuntimeError("ffmpeg binary not found")
    os.makedirs(out_dir, exist_ok=True)
    pattern = os.path.join(out_dir, "chunk%03d.wav")
    cmd = [
        FFMPEG_BINARY,
        "-y",
        "-i",
        wav_path,
        "-ar",
        str(AUDIO_SAMPLE_RATE),
        "-ac",
        str(AUDIO_CHANNELS),
        "-f",
        "segment",
        "-segment_time",
        str(chunk_duration_sec),
        "-reset_timestamps",
        "1",
        pattern
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    files = sorted(glob.glob(os.path.join(out_dir, "chunk*.wav")))
    return files

def create_prepended_chunk(chunk_path: str, silence_sec: int):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp.close()
    out_path = tmp.name
    try:
        prepend_silence_to_wav(chunk_path, out_path, silence_sec)
        return out_path
    except Exception:
        try:
            os.remove(out_path)
        except Exception:
            pass
        raise

def recognize_chunk_file(recognizer, file_path: str, language: str):
    last_exc = None
    prepended_path = None
    for attempt in range(1, RECOGNITION_MAX_RETRIES + 1):
        try:
            try:
                prepended_path = create_prepended_chunk(file_path, PREPEND_SILENCE_SEC)
            except Exception:
                prepended_path = None
            use_path = prepended_path if prepended_path else file_path
            with sr.AudioFile(use_path) as source:
                try:
                    recognizer.adjust_for_ambient_noise(source, duration=AMBIENT_CALIB_SEC)
                except Exception:
                    pass
                audio = recognizer.record(source)
            if language:
                text = recognizer.recognize_google(audio, language=language)
            else:
                text = recognizer.recognize_google(audio)
            if prepended_path:
                try:
                    os.remove(prepended_path)
                except Exception:
                    pass
            return text
        except sr.UnknownValueError:
            if prepended_path:
                try:
                    os.remove(prepended_path)
                except Exception:
                    pass
            return ""
        except sr.RequestError as e:
            last_exc = e
            if prepended_path:
                try:
                    os.remove(prepended_path)
                except Exception:
                    pass
            time.sleep(RECOGNITION_RETRY_WAIT * attempt)
            continue
        except ConnectionResetError as e:
            last_exc = e
            if prepended_path:
                try:
                    os.remove(prepended_path)
                except Exception:
                    pass
            time.sleep(RECOGNITION_RETRY_WAIT * attempt)
            continue
        except OSError as e:
            last_exc = e
            if prepended_path:
                try:
                    os.remove(prepended_path)
                except Exception:
                    pass
            break
    if last_exc is not None:
        raise last_exc
    return ""

def transcribe_file_with_speech_recognition(input_file_path: str, language_code: str):
    tmpdir = tempfile.mkdtemp(prefix="stt_")
    try:
        base_wav = os.path.join(tmpdir, "converted.wav")
        try:
            convert_to_wav(input_file_path, base_wav)
        except Exception as e:
            raise RuntimeError("Conversion to WAV failed: " + str(e))
        chunk_files = split_wav_to_chunks(base_wav, tmpdir, CHUNK_DURATION_SEC)
        if not chunk_files:
            raise RuntimeError("No audio chunks created")
        texts = []
        def transcribe_chunk(chunk_path):
            recognizer = sr.Recognizer()
            return recognize_chunk_file(recognizer, chunk_path, language_code)
        with ThreadPoolExecutor(max_workers=TRANSCRIBE_MAX_WORKERS) as executor:
            results = list(executor.map(transcribe_chunk, chunk_files))
        for r in results:
            if r:
                texts.append(r)
        final_text = "\n".join(texts)
        return final_text
    finally:
        try:
            for f in glob.glob(os.path.join(tmpdir, "*")):
                try:
                    os.remove(f)
                except Exception:
                    pass
            try:
                os.rmdir(tmpdir)
            except Exception:
                pass
        except Exception:
            pass

def transcribe_with_assemblyai(file_path: str, language_code: str, timeout_seconds: int = REQUEST_TIMEOUT_ASSEMBLY):
    headers = {"authorization": ASSEMBLYAI_API_KEY}
    upload_url = None
    with open(file_path, "rb") as f:
        try:
            resp = requests.post("https://api.assemblyai.com/v2/upload", headers=headers, data=f, timeout=timeout_seconds)
            resp.raise_for_status()
            j = resp.json()
            upload_url = j.get("upload_url") or j.get("url") or j.get("data") or None
            if not upload_url:
                if isinstance(j, dict) and len(j) == 1:
                    val = next(iter(j.values()))
                    if isinstance(val, str) and val.startswith("http"):
                        upload_url = val
            if not upload_url:
                raise RuntimeError("Upload failed: no upload_url returned")
        except Exception as e:
            raise RuntimeError("AssemblyAI upload failed: " + str(e))
    try:
        payload = {"audio_url": upload_url}
        if language_code:
            payload["language_code"] = language_code
        resp = requests.post("https://api.assemblyai.com/v2/transcript", headers={**headers, "content-type": "application/json"}, json=payload, timeout=timeout_seconds)
        resp.raise_for_status()
        job = resp.json()
        job_id = job.get("id")
        if not job_id:
            raise RuntimeError("AssemblyAI transcript creation failed")
        poll_url = f"https://api.assemblyai.com/v2/transcript/{job_id}"
        start = time.time()
        while True:
            r = requests.get(poll_url, headers=headers, timeout=30)
            r.raise_for_status()
            status_json = r.json()
            status = status_json.get("status")
            if status == "completed":
                return status_json.get("text", "")
            if status == "error":
                raise RuntimeError("AssemblyAI transcription error: " + str(status_json.get("error", "")))
            if time.time() - start > timeout_seconds:
                raise RuntimeError("AssemblyAI transcription timed out")
            time.sleep(3)
    except Exception as e:
        raise RuntimeError("AssemblyAI transcription failed: " + str(e))

def transcribe_via_selected_service(input_path: str, lang_code: str):
    use_assembly = lang_code in ASSEMBLY_LANG_SET
    if use_assembly:
        try:
            text = transcribe_with_assemblyai(input_path, lang_code)
            if text is None:
                raise RuntimeError("AssemblyAI returned no text")
            return text, "assemblyai"
        except Exception as e:
            logging.exception("AssemblyAI failed, falling back to speech_recognition")
            try:
                text = transcribe_file_with_speech_recognition(input_path, lang_code)
                return text, "speech_recognition"
            except Exception as e2:
                raise RuntimeError("Both AssemblyAI and speech_recognition failed: " + str(e2))
    else:
        try:
            text = transcribe_file_with_speech_recognition(input_path, lang_code)
            return text, "speech_recognition"
        except Exception as e:
            logging.exception("speech_recognition failed, attempting AssemblyAI as fallback")
            try:
                text = transcribe_with_assemblyai(input_path, lang_code)
                return text, "assemblyai"
            except Exception as e2:
                raise RuntimeError("Both speech_recognition and AssemblyAI failed: " + str(e2))

def send_summary_or_file(bot_obj, chat_id, summary, reply_to_message_id=None, filename_prefix='summary'):
    if summary is None:
        return
    if len(summary) <= 4000:
        if reply_to_message_id:
            bot_obj.send_message(chat_id, summary, reply_to_message_id=reply_to_message_id)
        else:
            bot_obj.send_message(chat_id, summary)
    else:
        bio = io.BytesIO(summary.encode('utf-8'))
        try:
            bio.name = f"{filename_prefix}.txt"
        except Exception:
            pass
        bio.seek(0)
        if reply_to_message_id:
            bot_obj.send_document(chat_id, document=bio, reply_to_message_id=reply_to_message_id)
        else:
            bot_obj.send_document(chat_id, document=bio)

def send_transcript_and_summary(bot_obj, chat_id, transcript, summary, reply_to_message_id=None, transcript_prefix='transcript', summary_prefix='summary'):
    if transcript is not None and transcript != "":
        if len(transcript) <= 4000:
            try:
                if reply_to_message_id:
                    bot_obj.send_message(chat_id, transcript, reply_to_message_id=reply_to_message_id)
                else:
                    bot_obj.send_message(chat_id, transcript)
            except Exception:
                try:
                    bio = io.BytesIO(transcript.encode('utf-8'))
                    bio.name = f"{transcript_prefix}.txt"
                    bio.seek(0)
                    if reply_to_message_id:
                        bot_obj.send_document(chat_id, document=bio, reply_to_message_id=reply_to_message_id)
                    else:
                        bot_obj.send_document(chat_id, document=bio)
                except Exception:
                    pass
        else:
            bio = io.BytesIO(transcript.encode('utf-8'))
            try:
                bio.name = f"{transcript_prefix}.txt"
            except Exception:
                pass
            bio.seek(0)
            try:
                if reply_to_message_id:
                    bot_obj.send_document(chat_id, document=bio, reply_to_message_id=reply_to_message_id)
                else:
                    bot_obj.send_document(chat_id, document=bio)
            except Exception:
                pass
    if summary is not None and summary != "":
        if len(summary) <= 4000:
            try:
                if reply_to_message_id:
                    bot_obj.send_message(chat_id, summary, reply_to_message_id=reply_to_message_id)
                else:
                    bot_obj.send_message(chat_id, summary)
            except Exception:
                try:
                    bio = io.BytesIO(summary.encode('utf-8'))
                    bio.name = f"{summary_prefix}.txt"
                    bio.seek(0)
                    if reply_to_message_id:
                        bot_obj.send_document(chat_id, document=bio, reply_to_message_id=reply_to_message_id)
                    else:
                        bot_obj.send_document(chat_id, document=bio)
                except Exception:
                    pass
        else:
            bio = io.BytesIO(summary.encode('utf-8'))
            try:
                bio.name = f"{summary_prefix}.txt"
            except Exception:
                pass
            bio.seek(0)
            try:
                if reply_to_message_id:
                    bot_obj.send_document(chat_id, document=bio, reply_to_message_id=reply_to_message_id)
                else:
                    bot_obj.send_document(chat_id, document=bio)
            except Exception:
                pass

def handle_media_common(message, bot_obj, bot_token, bot_index=0):
    user_id_str = str(message.from_user.id)
    chat_id_str = str(message.chat.id)
    update_user_activity(message.from_user.id)
    file_id = None
    file_size = None
    filename = None
    if message.voice:
        file_id = message.voice.file_id
        file_size = message.voice.file_size
        filename = "voice.ogg"
    elif message.audio:
        file_id = message.audio.file_id
        file_size = message.audio.file_size
        filename = getattr(message.audio, "file_name", "audio")
    elif message.video:
        file_id = message.video.file_id
        file_size = message.video.file_size
        filename = getattr(message.video, "file_name", "video.mp4")
    elif message.document:
        mime = getattr(message.document, "mime_type", None)
        filename = getattr(message.document, "file_name", None) or "file"
        ext = safe_extension_from_filename(filename)
        if mime and ("audio" in mime or "video" in mime):
            file_id = message.document.file_id
            file_size = message.document.file_size
        elif ext in ALLOWED_EXTENSIONS:
            file_id = message.document.file_id
            file_size = message.document.file_size
        else:
            bot_obj.send_message(message.chat.id, "Sorry, I can only process audio or video files.")
            return
    lang = get_stt_user_lang(user_id_str)
    if file_size and file_size > TELEGRAM_MAX_BYTES:
        token = signed_upload_token(message.chat.id, lang, bot_index)
        upload_link = f"{WEBHOOK_BASE.rstrip('/')}/upload/{token}"
        max_display_mb = TELEGRAM_MAX_BYTES // (1024 * 1024)
        text = f'🫩Telegram API doesn’t allow me to download your file if it’s larger than {max_display_mb}MB: <a href="{upload_link}">Please upload your file here</a>'
        bot_obj.send_message(message.chat.id, text, disable_web_page_preview=True, parse_mode='HTML', reply_to_message_id=message.message_id)
        return
    processing_msg = bot_obj.send_message(message.chat.id, "🔄 Processing...", reply_to_message_id=message.message_id)
    processing_msg_id = processing_msg.message_id
    stop_animation = {"stop": False}
    def stop_event():
        return stop_animation["stop"]
    animation_thread = threading.Thread(target=animate_processing_message, args=(bot_obj, message.chat.id, processing_msg_id, stop_event))
    animation_thread.start()
    try:
        tf, file_url = telegram_file_info_and_url(bot_token, file_id)
        tmpf = tempfile.NamedTemporaryFile(delete=False, suffix="." + (safe_extension_from_filename(filename) or "tmp"))
        try:
            with requests.get(file_url, stream=True, timeout=REQUEST_TIMEOUT_TELEGRAM) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=256*1024):
                    if chunk:
                        tmpf.write(chunk)
            tmpf.flush()
            tmpf.close()
            try:
                text, used_service = transcribe_via_selected_service(tmpf.name, lang)
            except Exception as e:
                error_msg = str(e)
                logging.exception("Error during transcription")
                if "ffmpeg" in error_msg.lower():
                    bot_obj.send_message(message.chat.id, "⚠️ Server error: ffmpeg not found or conversion failed. Contact admin @boyso.", reply_to_message_id=message.message_id)
                elif is_transcoding_like_error(error_msg):
                    bot_obj.send_message(message.chat.id, "⚠️ Transcription error: file is not audible. Please send a different file.", reply_to_message_id=message.message_id)
                else:
                    bot_obj.send_message(message.chat.id, f"Error during transcription: {error_msg}", reply_to_message_id=message.message_id)
                return
            
            summary = None
            if text and len(text) > 1000:
                try:
                    summary = summarize_with_gemini(text, lang)
                except Exception:
                    summary = "Error generating summary."
            send_transcript_and_summary(bot_obj, message.chat.id, text, summary, reply_to_message_id=message.message_id)
            increment_processing_count(user_id_str, "stt")
        finally:
            try:
                os.remove(tmpf.name)
            except Exception:
                pass
    except Exception as e:
        error_msg = str(e)
        logging.exception("Error in transcription process")
        if is_transcoding_like_error(error_msg):
            bot_obj.send_message(message.chat.id, "⚠️ Transcription error: file is not audible. Please send a different file.", reply_to_message_id=message.message_id)
        else:
            bot_obj.send_message(message.chat.id, f"Error during transcription: {error_msg}", reply_to_message_id=message.message_id)
    finally:
        stop_animation["stop"] = True
        animation_thread.join()
        try:
            bot_obj.delete_message(message.chat.id, processing_msg_id)
        except Exception:
            pass

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Upload File</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #f0f2f5;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            color: #333;
        }
        .container {
            background-color: #fff;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
            text-align: center;
            width: 90%;
            max-width: 500px;
            box-sizing: border-box;
        }
        h2 {
            margin-top: 0;
            color: #555;
            font-size: 1.5rem;
        }
        p {
            font-size: 0.9rem;
            color: #666;
            margin-bottom: 20px;
        }
        .file-upload-wrapper {
            position: relative;
            overflow: hidden;
            display: inline-block;
            cursor: pointer;
            width: 100%;
        }
        .file-upload-input {
            position: absolute;
            left: 0;
            top: 0;
            opacity: 0;
            cursor: pointer;
            font-size: 100px;
            width: 100%;
            height: 100%;
        }
        .file-upload-label {
            background-color: #007bff;
            color: #fff;
            padding: 12px 20px;
            border-radius: 8px;
            transition: background-color 0.3s;
            display: block;
            font-size: 1rem;
        }
        .file-upload-label:hover {
            background-color: #0056b3;
        }
        #file-name {
            margin-top: 15px;
            font-style: italic;
            color: #777;
            font-size: 0.9rem;
            word-wrap: break-word;
            overflow-wrap: break-word;
            min-height: 20px;
        }
        #progress-bar-container {
            width: 100%;
            background-color: #e0e0e0;
            border-radius: 5px;
            margin-top: 20px;
            display: none;
        }
        #progress-bar {
            width: 0%;
            height: 15px;
            background-color: #28a745;
            border-radius: 5px;
            text-align: center;
            color: white;
            line-height: 15px;
            transition: width 0.3s ease;
        }
        #status-message {
            margin-top: 15px;
            font-weight: bold;
        }
        .loading-spinner {
            display: none;
            width: 40px;
            height: 40px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #007bff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        @media (max-width: 600px) {
            .container {
                padding: 20px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>Upload Your Audio/Video</h2>
        <p>Your file is too big for Telegram, but you can upload it here. Max size: {{ max_mb }}MB.</p>
        <div class="file-upload-wrapper">
            <input type="file" id="file-input" class="file-upload-input" accept=".mp3,.wav,.m4a,.ogg,.webm,.flac,.mp4,.mkv,.avi,.mov,.hevc,.aac,.aiff,.amr,.wma,.opus,.m4v,.ts,.flv,.3gp">
            <label for="file-input" class="file-upload-label">
                <span id="upload-text">Choose File to Upload</span>
            </label>
        </div>
        <div id="file-name"></div>
        <div id="progress-bar-container">
            <div id="progress-bar">0%</div>
        </div>
        <div id="status-message"></div>
        <div class="loading-spinner" id="spinner"></div>
    </div>
    <script>
        const fileInput = document.getElementById('file-input');
        const fileNameDiv = document.getElementById('file-name');
        const progressBarContainer = document.getElementById('progress-bar-container');
        const progressBar = document.getElementById('progress-bar');
        const statusMessageDiv = document.getElementById('status-message');
        const spinner = document.getElementById('spinner');
        const uploadTextSpan = document.getElementById('upload-text');

        const MAX_SIZE_MB = {{ max_mb }};

        fileInput.addEventListener('change', function() {
            if (this.files.length > 0) {
                const file = this.files[0];
                fileNameDiv.textContent = `Selected: ${file.name}`;
                statusMessageDiv.textContent = '';
                progressBarContainer.style.display = 'none';
                progressBar.style.width = '0%';
                progressBar.textContent = '0%';
                if (file.size > MAX_SIZE_MB * 1024 * 1024) {
                    statusMessageDiv.style.color = 'red';
                    statusMessageDiv.textContent = `Error: File size exceeds the maximum limit of ${MAX_SIZE_MB}MB.`;
                    uploadTextSpan.textContent = 'Choose File to Upload';
                    fileNameDiv.textContent = '';
                } else {
                    uploadFile(file);
                }
            }
        });

        function uploadFile(file) {
            const formData = new FormData();
            formData.append('file', file);
            
            const xhr = new XMLHttpRequest();
            xhr.open('POST', window.location.href);

            xhr.upload.addEventListener('progress', function(e) {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    progressBarContainer.style.display = 'block';
                    progressBar.style.width = percent + '%';
                    progressBar.textContent = percent + '%';
                    statusMessageDiv.textContent = `Uploading... ${percent}%`;
                    if (percent === 100) {
                        statusMessageDiv.textContent = 'Upload complete. Processing...';
                        spinner.style.display = 'block';
                    }
                }
            });

            xhr.onload = function() {
                spinner.style.display = 'none';
                if (xhr.status === 200) {
                    statusMessageDiv.style.color = '#28a745';
                    statusMessageDiv.textContent = 'Success! Your Transcription  will be sent to your Telegram chat shortly.';
                } else {
                    statusMessageDiv.style.color = 'red';
                    statusMessageDiv.textContent = `Error: ${xhr.responseText || 'An unknown error occurred.'}`;
                }
            };
            xhr.onerror = function() {
                spinner.style.display = 'none';
                statusMessageDiv.style.color = 'red';
                statusMessageDiv.textContent = 'Network error. Please try again.';
            };
            xhr.send(formData);
        }
    </script>
</body>
</html>
"""

@app.route("/upload/<token>", methods=['GET', 'POST'])
def upload_large_file(token):
    try:
        data = unsign_upload_token(token, max_age_seconds=3600)
    except SignatureExpired:
        return "<h3>Link expired</h3>", 400
    except BadSignature:
        return "<h3>Invalid link</h3>", 400
    chat_id = data.get("chat_id")
    lang = data.get("lang", "en")
    bot_index = int(data.get("bot_index", 0))
    if bot_index < 0 or bot_index >= len(bots):
        bot_index = 0
    if request.method == 'GET':
        return render_template_string(HTML_TEMPLATE, lang_options=LANG_OPTIONS, selected_lang=lang, max_mb=MAX_WEB_UPLOAD_MB)
    file = request.files.get('file')
    if not file:
        return "No file uploaded", 400
    file_bytes = file.read()
    if len(file_bytes) > MAX_WEB_UPLOAD_MB * 1024 * 1024:
        return f"File too large. Max allowed is {MAX_WEB_UPLOAD_MB}MB.", 400
    def bytes_to_tempfile(b):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".upload")
        tmp.write(b)
        tmp.flush()
        tmp.close()
        return tmp.name
    def process_uploaded_file(chat_id_inner, lang_inner, path, bot_index_inner):
        try:
            bot_to_use = bots[bot_index_inner] if 0 <= bot_index_inner < len(bots) else bots[0]
            try:
                text, used = transcribe_via_selected_service(path, lang_inner)
            except Exception:
                try:
                    bot_to_use.send_message(chat_id_inner, "Error occurred while transcribing the uploaded file.")
                except Exception:
                    pass
                return
            
            summary = None
            if text and len(text) > 1000:
                try:
                    summary = summarize_with_gemini(text, lang_inner)
                except Exception:
                    summary = "Error generating summary."
                
            if not summary:
                summary = None
                
            try:
                send_transcript_and_summary(bot_to_use, chat_id_inner, text, summary)
                increment_processing_count(str(chat_id_inner), "stt")
            except Exception:
                try:
                    bot_to_use.send_message(chat_id_inner, "Error sending summary message. The process completed but could not be delivered as a message.")
                except Exception:
                    pass
                return
        finally:
            try:
                os.remove(path)
            except Exception:
                pass
    tmp_path = bytes_to_tempfile(file_bytes)
    threading.Thread(target=process_uploaded_file, args=(chat_id, lang, tmp_path, bot_index), daemon=True).start()
    return jsonify({"status": "accepted", "message": "Upload accepted. Processing started. Your summary will be sent to your Telegram chat when ready."})

def summarize_with_gemini(text: str, language: str) -> str:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
    label = CODE_TO_LABEL.get(language, language)
    try:
        language_name = label.split(" ",1)[-1]
    except Exception:
        language_name = str(language)
    instruction = f"Summarize the following text in {language_name}. Produce a concise, professional, high-quality summary that inspires confidence.Do not include introductions, disclaimers, extra notes, or metadata. Output only the summary."
    prompt = f"{instruction}\n\n{text}"
    response = model.generate_content(prompt)
    return response.text.strip()

@app.route("/assemblyai", methods=["POST"])
def assemblyai_endpoint():
    lang = request.form.get("language", "en")
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "no file provided"}), 400
    b = f.read()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".upload")
    try:
        tmp.write(b)
        tmp.flush()
        tmp.close()
        try:
            text = transcribe_with_assemblyai(tmp.name, lang)
            return jsonify({"text": text}), 200
        except Exception as e:
            try:
                text = transcribe_file_with_speech_recognition(tmp.name, lang)
                return jsonify({"text": text, "fallback": "speech_recognition"}), 200
            except Exception as e2:
                return jsonify({"error": str(e2)}), 500
    finally:
        try:
            os.remove(tmp.name)
        except Exception:
            pass

def register_handlers(bot_obj, bot_token, bot_index):
    @bot_obj.message_handler(commands=['start', 'admin'])
    def start_handler(message):
        try:
            chat_id = message.chat.id
            if chat_id == ADMIN_ID and message.text.lower() == '/admin':
                bot_obj.send_message(
                    chat_id,
                    "👋 Welcome, Admin! Choose an option:",
                    reply_markup=build_admin_keyboard()
                )
            else:
                update_user_activity(message.from_user.id)
                bot_obj.send_message(
                    message.chat.id,
                    "Choose your file language for transcription using the below buttons:",
                    reply_markup=build_lang_keyboard("start_select_lang")
                )
        except Exception:
            logging.exception("Error in start_handler")

    @bot_obj.callback_query_handler(func=lambda c: c.data and c.data.startswith("start_select_lang|"))
    def start_select_lang_callback(call):
        try:
            uid = str(call.from_user.id)
            _, lang_code = call.data.split("|", 1)
            lang_label = CODE_TO_LABEL.get(lang_code, lang_code)
            set_stt_user_lang(uid, lang_code)
            try:
                bot_obj.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass
            welcome_text = (
     f"👋 Welcome!    \n"
                "• Send me\n"
                "• voice message\n"
                "• audio file\n"
                "• video\n"
                "• to transcribe for free"
            )
            bot_obj.send_message(call.message.chat.id, welcome_text)
            bot_obj.answer_callback_query(call.id, f"✅ Language set to {lang_label}")
        except Exception:
            logging.exception("Error in start_select_lang_callback")
            try:
                bot_obj.answer_callback_query(call.id, "❌ Error setting language", show_alert=True)
            except Exception:
                pass

    @bot_obj.message_handler(commands=['help'])
    def handle_help(message):
        try:
            update_user_activity(message.from_user.id)
            text = (
              "Commands supported:\n"
                "/start - Show welcome message\n"
                "/lang  - Change language\n"
                "/help  - This help message\n\n"
                "Send me a voice/audio/video (up to 20MB for Telegram) to transcribe.\n"
                "If it's larger than Telegram limits, you'll be provided a secure web upload link (supports up to 250MB). Need more help? Contact: @boyso20"  
            )
            bot_obj.send_message(message.chat.id, text)
        except Exception:
            logging.exception("Error in handle_help")

    @bot_obj.message_handler(commands=['lang'])
    def handle_lang(message):
        try:
            kb = build_lang_keyboard("stt_lang")
            bot_obj.send_message(message.chat.id, "Choose your file language for transcription using the below buttons:", reply_markup=kb)
        except Exception:
            logging.exception("Error in handle_lang")

    @bot_obj.callback_query_handler(lambda c: c.data and c.data.startswith("stt_lang|"))
    def on_stt_language_select(call):
        try:
            uid = str(call.from_user.id)
            _, lang_code = call.data.split("|", 1)
            lang_label = CODE_TO_LABEL.get(lang_code, lang_code)
            set_stt_user_lang(uid, lang_code)
            bot_obj.answer_callback_query(call.id, f"✅ Language set: {lang_label}")
            try:
                bot_obj.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass
        except Exception:
            logging.exception("Error in on_stt_language_select")
            try:
                bot_obj.answer_callback_query(call.id, "❌ Error setting language", show_alert=True)
            except Exception:
                pass

    @bot_obj.message_handler(content_types=['new_chat_members'])
    def handle_new_chat_members(message):
        try:
            if message.new_chat_members[0].id == bot_obj.get_me().id:
                group_data = {
                    '_id': str(message.chat.id),
                    'title': message.chat.title,
                    'type': message.chat.type,
                    'added_date': datetime.now()
                }
                groups_collection.update_one({'_id': group_data['_id']}, {'$set': group_data}, upsert=True)
                bot_obj.send_message(message.chat.id, "Thanks for adding me! I'm ready to summarize your media files.")
        except Exception:
            logging.exception("Error in handle_new_chat_members")

    @bot_obj.message_handler(content_types=['left_chat_member'])
    def handle_left_chat_member(message):
        try:
            if message.left_chat_member.id == bot_obj.get_me().id:
                groups_collection.delete_one({'_id': str(message.chat.id)})
        except Exception:
            logging.exception("Error in handle_left_chat_member")

    @bot_obj.message_handler(content_types=['voice', 'audio', 'video', 'document'])
    def handle_media_types(message):
        try:
            if message.chat.id == ADMIN_ID and admin_broadcast_state.get(message.chat.id, False):
                bot_obj.send_message(message.chat.id, "Broadcasting your media now...")
                all_users_chat_ids = users_collection.distinct("_id")
                sent_count = 0
                failed_count = 0
                for user_chat_id_str in all_users_chat_ids:
                    try:
                        user_chat_id = int(user_chat_id_str)
                        if user_chat_id == ADMIN_ID:
                            continue
                        bot_obj.copy_message(user_chat_id, message.chat.id, message.message_id)
                        sent_count += 1
                        time.sleep(0.1)
                    except telebot.apihelper.ApiTelegramException as e:
                        logging.error(f"Failed to send broadcast to user {user_chat_id}: {e}")
                        failed_count += 1
                    except Exception as e:
                        logging.error(f"Unexpected error broadcasting to user {user_chat_id}: {e}")
                        failed_count += 1
                bot_obj.send_message(message.chat.id, f"Broadcast complete! Successfully sent to {sent_count} users. Failed for {failed_count} users.")
                bot_obj.send_message(
                    message.chat.id,
                    "What else, Admin?",
                    reply_markup=build_admin_keyboard()
                )
                return
            handle_media_common(message, bot_obj, bot_token, bot_index)
        except Exception:
            logging.exception("Error in handle_media_types")

    @bot_obj.callback_query_handler(func=lambda c: c.data and c.data.startswith("admin_"))
    def admin_inline_callback(call):
        try:
            if call.from_user.id != ADMIN_ID:
                bot_obj.answer_callback_query(call.id, "Unauthorized", show_alert=True)
                return
            if call.data == "admin_total_users":
                total_users = users_collection.count_documents({})
                bot_obj.edit_message_text(f"Total users registered: {total_users}", chat_id=call.message.chat.id, message_id=call.message.message_id)
                bot_obj.send_message(
                    call.message.chat.id,
                    "What else, Admin?",
                    reply_markup=build_admin_keyboard()
                )
                bot_obj.answer_callback_query(call.id)
            elif call.data == "admin_send_broadcast":
                admin_broadcast_state[call.message.chat.id] = True
                bot_obj.send_message(call.message.chat.id, "Okay, Admin. Send me the message (text, photo, video, document, etc.) you want to broadcast to all users. To cancel, type /cancel_broadcast")
                bot_obj.answer_callback_query(call.id, "Send your broadcast message now")
            else:
                bot_obj.answer_callback_query(call.id)
        except Exception:
            logging.exception("Error in admin_inline_callback")

    @bot_obj.message_handler(commands=['cancel_broadcast'], func=lambda message: message.chat.id == ADMIN_ID and admin_broadcast_state.get(message.chat.id, False))
    def cancel_broadcast(message):
        try:
            if message.chat.id in admin_broadcast_state:
                del admin_broadcast_state[message.chat.id]
            bot_obj.send_message(
                message.chat.id,
                "Broadcast cancelled. What else, Admin?",
                reply_markup=build_admin_keyboard()
            )
        except Exception:
            logging.exception("Error in cancel_broadcast")

    @bot_obj.message_handler(content_types=['text', 'photo', 'video', 'document', 'audio', 'voice'], func=lambda message: message.chat.id == ADMIN_ID and admin_broadcast_state.get(message.chat.id, False))
    def handle_broadcast_message(message):
        try:
            if message.chat.id in admin_broadcast_state:
                del admin_broadcast_state[message.chat.id]
            bot_obj.send_message(message.chat.id, "Broadcasting your message now...")
            all_users_chat_ids = users_collection.distinct("_id")
            sent_count = 0
            failed_count = 0
            for user_chat_id_str in all_users_chat_ids:
                try:
                    user_chat_id = int(user_chat_id_str)
                    if user_chat_id == ADMIN_ID:
                        continue
                    bot_obj.copy_message(user_chat_id, message.chat.id, message.message_id)
                    sent_count += 1
                    time.sleep(0.1)
                except telebot.apihelper.ApiTelegramException as e:
                    logging.error(f"Failed to send broadcast to user {user_chat_id}: {e}")
                    failed_count += 1
                except Exception as e:
                    logging.error(f"Unexpected error broadcasting to user {user_chat_id}: {e}")
                    failed_count += 1
            bot_obj.send_message(message.chat.id, f"Broadcast complete! Successfully sent to {sent_count} users. Failed for {failed_count} users.")
            bot_obj.send_message(
                message.chat.id,
                "What else, Admin?",
                reply_markup=build_admin_keyboard()
            )
        except Exception:
            logging.exception("Error in handle_broadcast_message")

    @bot_obj.message_handler(content_types=['text'])
    def handle_text_messages(message):
        try:
            if message.chat.id == ADMIN_ID and not admin_broadcast_state.get(message.chat.id, False):
                bot_obj.send_message(
                    message.chat.id,
                    "Admin, please use the admin options.",
                    reply_markup=build_admin_keyboard()
                )
                return
            bot_obj.send_message(message.chat.id, "I can only process audio, video, or document files to provide a summary. Please send one of those, or use /lang to change your language settings.")
        except Exception:
            logging.exception("Error in handle_text_messages")

for idx, bot_obj in enumerate(bots):
    register_handlers(bot_obj, BOT_TOKENS[idx], idx)

@app.route("/", methods=["GET", "POST", "HEAD"])
def webhook_root():
    if request.method in ("GET", "HEAD"):
        bot_index = request.args.get("bot_index")
        try:
            bot_index_val = int(bot_index) if bot_index is not None else 0
        except Exception:
            bot_index_val = 0
        now_iso = datetime.utcnow().isoformat() + "Z"
        return jsonify({"status": "ok", "time": now_iso, "bot_index": bot_index_val}), 200
    if request.method == "POST":
        content_type = request.headers.get("Content-Type", "")
        if content_type and content_type.startswith("application/json"):
            raw = request.get_data().decode("utf-8")
            try:
                payload = json.loads(raw)
            except Exception:
                payload = None
            bot_index = request.args.get("bot_index")
            if not bot_index and isinstance(payload, dict):
                bot_index = payload.get("bot_index")
            header_idx = request.headers.get("X-Bot-Index")
            if header_idx:
                bot_index = header_idx
            try:
                bot_index_val = int(bot_index) if bot_index is not None else 0
            except Exception:
                bot_index_val = 0
            if bot_index_val < 0 or bot_index_val >= len(bots):
                return abort(404)
            try:
                update = telebot.types.Update.de_json(raw)
                bots[bot_index_val].process_new_updates([update])
            except Exception:
                logging.exception("Error processing incoming webhook update")
            return "", 200
    return abort(403)

@app.route("/set_webhook", methods=["GET", "POST"])
def set_webhook_route():
    results = []
    for idx, bot_obj in enumerate(bots):
        try:
            url = WEBHOOK_BASE.rstrip("/") + f"/?bot_index={idx}"
            bot_obj.delete_webhook()
            time.sleep(0.2)
            bot_obj.set_webhook(url=url)
            results.append({"index": idx, "url": url, "status": "ok"})
        except Exception as e:
            logging.error(f"Failed to set webhook for bot {idx}: {e}")
            results.append({"index": idx, "error": str(e)})
    return jsonify({"results": results}), 200

@app.route("/delete_webhook", methods=["GET", "POST"])
def delete_webhook_route():
    results = []
    for idx, bot_obj in enumerate(bots):
        try:
            bot_obj.delete_webhook()
            results.append({"index": idx, "status": "deleted"})
        except Exception as e:
            logging.error(f"Failed to delete webhook for bot {idx}: {e}")
            results.append({"index": idx, "error": str(e)})
    return jsonify({"results": results}), 200

def set_webhook_on_startup():
    for idx, bot_obj in enumerate(bots):
        try:
            bot_obj.delete_webhook()
            time.sleep(0.2)
            url = WEBHOOK_BASE.rstrip("/") + f"/?bot_index={idx}"
            bot_obj.set_webhook(url=url)
            logging.info(f"Main bot webhook set successfully to {url}")
        except Exception as e:
            logging.error(f"Failed to set main bot webhook on startup: {e}")

def set_bot_info_and_startup():
    set_webhook_on_startup()

if __name__ == "__main__":
    try:
        set_bot_info_and_startup()
        try:
            client.admin.command('ping')
            logging.info("Successfully connected to MongoDB!")
        except Exception as e:
            logging.error("Could not connect to MongoDB: %s", e)
    except Exception:
        logging.exception("Failed during startup")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
