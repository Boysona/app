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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CHUNK_DURATION_SEC = int(os.environ.get("CHUNK_DURATION_SEC", "55"))
CHUNK_BATCH_SIZE = int(os.environ.get("CHUNK_BATCH_SIZE", "30"))
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
ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY", "3da64715f8304ca3a7c78638c4bfd90c")

BOT_TOKENS = [
    "7770743573:AAELOYGUgVT_AhA1SHPzLszK0IjwOVKz7p8",
    "7790991731:AAF4NHGm0BJCf08JTdBaUWKzwfs82_Y9Ecw",
]
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDOsEOu98sYFCzPZtvk9nZXOc3mitjuq-I")
WEBHOOK_BASE = os.environ.get("WEBHOOK_BASE", "https://civilian-cherri-cadenuux57-b04883d4.koyeb.app/")
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

def get_user_send_mode(user_id: str) -> str:
    user_data = users_collection.find_one({"_id": user_id})
    if user_data and "stt_send_mode" in user_data:
        return user_data["stt_send_mode"]
    return "file"

def set_user_send_mode(user_id: str, mode: str):
    if mode not in ("file", "split"):
        mode = "file"
    users_collection.update_one(
        {"_id": user_id},
        {"$set": {"stt_send_mode": mode}},
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

def build_result_mode_keyboard(prefix: str = "result_mode"):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("📄 .txt file", callback_data=f"{prefix}|file"))
    markup.add(InlineKeyboardButton("💬 Split messages", callback_data=f"{prefix}|split"))
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
            bot_obj.edit_message_text(f"🔄 Processing{dots[idx % len(dots)]}", chat_id=chat_id, message_id=message_id)
        except Exception:
            pass
        idx = (idx + 1) % len(dots)
        time.sleep(0.6)

def normalize_text_offline(text: str) -> str:
    if not text:
        return text
    t = re.sub(r'\s+', ' ', text).strip()
    return t

def extract_key_points_offline(text: str, max_points: int = 6) -> str:
    if not text:
        return ""
    sentences = re.split(r'(?<=[\.\!\?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return ""
    words = re.findall(r'\w+', text.lower())
    words = [w for w in words if len(w) > 3]
    if not words:
        selected = sentences[:max_points]
        return "\n".join(f"- {s}" for s in selected)
    freq = Counter(words)
    sentence_scores = []
    for s in sentences:
        s_words = re.findall(r'\w+', s.lower())
        score = sum(freq.get(w, 0) for w in s_words)
        sentence_scores.append((score, s))
    sentence_scores.sort(key=lambda x: x[0], reverse=True)
    top = sentence_scores[:max_points]
    top_sentences = sorted(top, key=lambda x: sentences.index(x[1]))
    result_lines = [f"- {s}" for _, s in top_sentences]
    return "\n".join(result_lines)

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

def split_text_into_chunks(text: str, limit: int = 4096):
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + limit, n)
        if end < n:
            last_space = text.rfind(" ", start, end)
            if last_space > start:
                end = last_space
        chunk = text[start:end].strip()
        if not chunk:
            end = start + limit
            chunk = text[start:end].strip()
        chunks.append(chunk)
        start = end
    return chunks

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
            bot_obj.send_message(message.chat.id, "Sorry, I can only transcribe audio or video files.")
            return
    lang = get_stt_user_lang(user_id_str)
    if file_size and file_size > TELEGRAM_MAX_BYTES:
        token = signed_upload_token(message.chat.id, lang, bot_index)
        upload_link = f"{WEBHOOK_BASE}/upload/{token}"
        pretty_size_mb = round(file_size / (1024*1024), 2)
        text = (
            "📁 <b>File Too Large for Telegram</b>\n"
            f"Your file is {pretty_size_mb}MB, which exceeds Telegram's 20MB limit.\n\n"
            "🌐 <b>Upload via Web Interface:</b>\n"
            "👆 Click the link below to upload your large file:\n\n"
            f"🔗 <a href=\"{upload_link}\">Upload Large File</a>\n\n"
            f"✅ Your language preference ({lang}) is already set!\n"
            "Link expires in 1 hour."
        )
        bot_obj.send_message(message.chat.id, text, disable_web_page_preview=True, reply_to_message_id=message.message_id)
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
            corrected_text = normalize_text_offline(text)
            uid_key = str(message.chat.id)
            user_mode = get_user_send_mode(uid_key)
            if len(corrected_text) > 4000:
                if user_mode == "file":
                    f = io.BytesIO(corrected_text.encode("utf-8"))
                    f.name = "transcription.txt"
                    markup = InlineKeyboardMarkup()
                    sent = bot_obj.send_document(message.chat.id, f, reply_to_message_id=message.message_id, reply_markup=markup)
                    try:
                        buttons = []
                        #buttons.append(InlineKeyboardButton("⭐️Clean transcript", callback_data=f"clean_up|{message.chat.id}|{sent.message_id}"))
                        if len(corrected_text) > 1000:
                            buttons.append(InlineKeyboardButton("Get Summarize", callback_data=f"get_key_points|{message.chat.id}|{sent.message_id}"))
                        for b in buttons:
                            markup.add(b)
                        bot_obj.edit_message_reply_markup(message.chat.id, sent.message_id, reply_markup=markup)
                    except Exception:
                        pass
                    try:
                        user_transcriptions.setdefault(uid_key, {})[sent.message_id] = corrected_text
                        threading.Thread(target=delete_transcription_later, args=(uid_key, sent.message_id), daemon=True).start()
                    except Exception:
                        pass
                else:
                    chunks = split_text_into_chunks(corrected_text, limit=4096)
                    last_sent = None
                    markup = InlineKeyboardMarkup()
                    for idx, chunk in enumerate(chunks):
                        if idx == 0:
                            last_sent = bot_obj.send_message(message.chat.id, chunk, reply_to_message_id=message.message_id)
                        else:
                            last_sent = bot_obj.send_message(message.chat.id, chunk)
                    try:
                        buttons = []
                        #buttons.append(InlineKeyboardButton("⭐️Clean transcript", callback_data=f"clean_up|{message.chat.id}|{last_sent.message_id}"))
                        if len(corrected_text) > 1000:
                            buttons.append(InlineKeyboardButton("Get Summarize", callback_data=f"get_key_points|{message.chat.id}|{last_sent.message_id}"))
                        for b in buttons:
                            markup.add(b)
                        bot_obj.edit_message_reply_markup(message.chat.id, last_sent.message_id, reply_markup=markup)
                    except Exception:
                        pass
                    try:
                        user_transcriptions.setdefault(uid_key, {})[last_sent.message_id] = corrected_text
                        threading.Thread(target=delete_transcription_later, args=(uid_key, last_sent.message_id), daemon=True).start()
                    except Exception:
                        pass
            else:
                markup = InlineKeyboardMarkup()
                sent_msg = bot_obj.send_message(message.chat.id, corrected_text or "No transcription text was returned.", reply_to_message_id=message.message_id, reply_markup=markup)
                try:
                    buttons = []
                    #buttons.append(InlineKeyboardButton("⭐️Clean transcript", callback_data=f"clean_up|{message.chat.id}|{sent_msg.message_id}"))
                    if len(corrected_text) > 1000:
                        buttons.append(InlineKeyboardButton("Get Summarize", callback_data=f"get_key_points|{message.chat.id}|{sent_msg.message_id}"))
                    for b in buttons:
                        markup.add(b)
                    bot_obj.edit_message_reply_markup(message.chat.id, sent_msg.message_id, reply_markup=markup)
                except Exception:
                    pass
                try:
                    user_transcriptions.setdefault(uid_key, {})[sent_msg.message_id] = corrected_text
                    threading.Thread(target=delete_transcription_later, args=(uid_key, sent_msg.message_id), daemon=True).start()
                except Exception:
                    pass
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
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>Media to Text Bot</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"/>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet"/>
    <style>
        :root {
            --primary: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --success: linear-gradient(135deg, #10b981, #059669);
            --danger: linear-gradient(135deg, #ef4444, #dc2626);
            --card-bg: rgba(255, 255, 255, 0.95);
            --shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--primary);
            min-height: 100vh;
            overflow-x: hidden;
        }
        .app-container {
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .main-card {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border-radius: 20px;
            box-shadow: var(--shadow);
            border: 1px solid rgba(255, 255, 255, 0.2);
            max-width: 600px;
            width: 100%;
            overflow: hidden;
            transition: all 0.3s ease;
        }
        .main-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 32px 64px -12px rgba(0, 0, 0, 0.3);
        }
        .header {
            background: var(--primary);
            color: white;
            padding: 2.5rem 2rem;
            text-align: center;
            position: relative;
            overflow: hidden;
        }
        .header h1 {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }
        .header p {
            opacity: 0.9;
            font-size: 1.1rem;
        }
        .card-body { padding: 2.5rem; }
        .form-group { margin-bottom: 2rem; }
        .form-label {
            font-weight: 600;
            color: #374151;
            margin-bottom: 0.8rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 1.1rem;
        }
        .form-select, .form-control {
            border: 2px solid #e5e7eb;
            border-radius: 15px;
            padding: 1rem 1.2rem;
            font-size: 1rem;
            transition: all 0.3s ease;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        .form-select:focus, .form-control:focus {
            border-color: #667eea;
            box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.1);
            outline: none;
        }
        .upload-area {
            border: 3px dashed #d1d5db;
            border-radius: 20px;
            padding: 3rem 2rem;
            text-align: center;
            transition: all 0.3s ease;
            cursor: pointer;
            background: #f8fafc;
            position: relative;
        }
        .upload-area:hover {
            border-color: #667eea;
            background: #f0f9ff;
            transform: scale(1.02);
        }
        .upload-area.dragover {
            border-color: #667eea;
            background: #667eea;
            color: white;
        }
        .upload-icon {
            font-size: 4rem;
            color: #667eea;
            margin-bottom: 1.5rem;
            transition: all 0.3s ease;
        }
        .dragover .upload-icon { color: white; transform: scale(1.2); }
        .upload-text {
            font-size: 1.3rem;
            font-weight: 600;
            color: #374151;
            margin-bottom: 0.8rem;
        }
        .dragover .upload-text { color: white; }
        .upload-hint {
            color: #6b7280;
            font-size: 1rem;
        }
        .dragover .upload-hint { color: rgba(255, 255, 255, 0.9); }
        .btn-primary {
            background: var(--primary);
            border: none;
            border-radius: 15px;
            padding: 1rem 2.5rem;
            font-weight: 600;
            font-size: 1.1rem;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        .btn-primary:hover {
            transform: translateY(-3px);
            box-shadow: 0 15px 35px -5px rgba(102, 126, 234, 0.4);
        }
        .status-message {
            padding: 1.5rem;
            border-radius: 15px;
            margin: 2rem 0;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 1rem;
            font-size: 1.1rem;
        }
        .status-processing {
            background: linear-gradient(135deg, #3b82f6, #1d4ed8);
            color: white;
        }
        .status-success {
            background: var(--success);
            color: white;
        }
        .status-error {
            background: var(--danger);
            color: white;
        }
        .result-container {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 15px;
            padding: 2rem;
            margin-top: 2rem;
        }
        .result-text {
            font-family: 'Georgia', serif;
            line-height: 1.8;
            color: #1f2937;
            font-size: 1.1rem;
        }
        .close-notice {
            background: linear-gradient(135deg, #10b981, #059669);
            color: white;
            padding: 1.5rem;
            border-radius: 15px;
            margin: 2rem 0;
            text-align: center;
            font-weight: 600;
            font-size: 1.1rem;
        }
        .progress-wrap { margin-top: 1rem; text-align: left; }
        .progress-bar-outer {
            width: 100%;
            background: #e6eefc;
            border-radius: 12px;
            overflow: hidden;
            height: 18px;
        }
        .progress-bar-inner {
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg,#6ee7b7,#3b82f6);
            transition: width 0.2s ease;
        }
        .bytes-info {
            margin-top: 0.5rem;
            font-size: 0.95rem;
            color: #374151;
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
        }
        .pulse-icon { animation: pulse 2s infinite; }
        .hidden { display: none !important; }
        @media (max-width: 768px) {
            .app-container { padding: 15px; }
            .main-card { margin: 0; }
            .header h1 { font-size: 1.8rem; }
            .card-body { padding: 2rem; }
            .upload-area { padding: 2.5rem 1.5rem; }
            .upload-icon { font-size: 3rem; }
        }
    </style>
</head>
<body>
    <div class="app-container">
        <div class="main-card">
            <div class="header">
                <h1><i class="fas fa-microphone-alt"></i> Media to Text Bot</h1>
                <p>Transform your media files into accurate text</p>
            </div>
            <div class="card-body">
                <form id="transcriptionForm" enctype="multipart/form-data" method="post">
                    <div class="form-group">
                        <label class="form-label" for="language">
                            <i class="fas fa-globe-americas"></i> Language
                        </label>
                        <select class="form-select" id="language" name="language" required>
                            {% for label, code in lang_options %}
                            <option value="{{ code }}" {% if code == selected_lang %}selected{% endif %}>{{ label }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">
                            <i class="fas fa-file-audio"></i> Media File
                        </label>
                        <div class="upload-area" id="uploadArea">
                            <div class="upload-icon">
                                <i class="fas fa-cloud-upload-alt"></i>
                            </div>
                            <div class="upload-text">Drop your media here</div>
                            <div class="upload-hint">MP3, WAV, M4A, OGG, WEBM, FLAC, MP4, MKV, AVI, MOV, HEVC • Max {{ max_mb }}MB</div>
                            <input type="file" id="audioFile" name="file" accept=".mp3,.wav,.m4a,.ogg,.webm,.flac,.mp4,.mkv,.avi,.mov,.hevc,.aac,.aiff,.amr,.wma,.opus,.m4v,.ts,.flv,.3gp" class="d-none" required>
                        </div>
                    </div>
                    <button type="button" id="uploadButton" class="btn btn-primary w-100">
                        <i class="fas fa-magic"></i> Upload & Start
                    </button>
                </form>
                <div id="statusContainer"></div>
                <div id="resultContainer"></div>
            </div>
        </div>
    </div>
    <script>
        class TranscriptionApp {
            constructor() {
                this.initializeEventListeners();
            }
            initializeEventListeners() {
                this.uploadArea = document.getElementById('uploadArea');
                this.fileInput = document.getElementById('audioFile');
                this.uploadButton = document.getElementById('uploadButton');
                this.statusContainer = document.getElementById('statusContainer');
                this.resultContainer = document.getElementById('resultContainer');
                this.uploadArea.addEventListener('click', () => this.fileInput.click());
                this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
                this.uploadArea.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    this.uploadArea.classList.add('dragover');
                });
                this.uploadArea.addEventListener('dragleave', () => {
                    this.uploadArea.classList.remove('dragover');
                });
                this.uploadArea.addEventListener('drop', (e) => {
                    e.preventDefault();
                    this.uploadArea.classList.remove('dragover');
                    const files = e.dataTransfer.files;
                    if (files.length > 0) {
                        this.fileInput.files = files;
                        this.handleFileSelect({ target: this.fileInput });
                    }
                });
                this.uploadButton.addEventListener('click', (e) => this.handleSubmit(e));
            }
            humanFileSize(bytes) {
                if (bytes === 0) return '0 B';
                const k = 1024;
                const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
            }
            handleFileSelect(e) {
                const file = e.target.files[0];
                if (file) {
                    const uploadText = document.querySelector('.upload-text');
                    uploadText.textContent = `Selected: ${file.name} (${this.humanFileSize(file.size)})`;
                }
            }
            showUploadingUI() {
                this.statusContainer.innerHTML = `
                    <div class="status-message status-processing">
                        <i class="fas fa-spinner fa-spin pulse-icon"></i>
                        <div>
                            <div id="uploadStatusText">Upload Processing..</div>
                            <div class="progress-wrap">
                                <div class="progress-bar-outer"><div id="progressInner" class="progress-bar-inner"></div></div>
                                <div id="bytesInfo" class="bytes-info"></div>
                            </div>
                        </div>
                    </div>
                `;
            }
            async handleSubmit(e) {
                e.preventDefault();
                const file = this.fileInput.files[0];
                if (!file) {
                    alert("Please choose a file to upload.");
                    return;
                }
                if (file.size > {{ max_mb }} * 1024 * 1024) {
                    alert("File is too large. Max allowed is {{ max_mb }}MB.");
                    return;
                }
                const formData = new FormData();
                formData.append('file', file);
                formData.append('language', document.getElementById('language').value);
                this.showUploadingUI();
                const progressInner = document.getElementById('progressInner');
                const bytesInfo = document.getElementById('bytesInfo');
                const uploadStatusText = document.getElementById('uploadStatusText');
                const xhr = new XMLHttpRequest();
                xhr.open('POST', window.location.pathname, true);
                xhr.upload.onprogress = (event) => {
                    if (event.lengthComputable) {
                        const percent = Math.round((event.loaded / event.total) * 100);
                        progressInner.style.width = percent + '%';
                        bytesInfo.textContent = `${(event.loaded/1024/1024).toFixed(2)} MB / ${(event.total/1024/1024).toFixed(2)} MB (${percent}%)`;
                        uploadStatusText.textContent = `Uploading... ${percent}%`;
                    } else {
                        progressInner.style.width = '50%';
                        bytesInfo.textContent = `${(event.loaded/1024/1024).toFixed(2)} MB uploaded`;
                        uploadStatusText.textContent = `Uploading...`;
                    }
                };
                xhr.onload = () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        let respText = "Upload accepted. Processing started. You may close this tab.";
                        try {
                            const j = JSON.parse(xhr.responseText);
                            if (j && j.message) respText = j.message;
                        } catch (err) {
                            respText = xhr.responseText || respText;
                        }
                        this.statusContainer.innerHTML = `
                            <div class="close-notice">
                                <i class="fas fa-check-circle"></i>
                                ${respText}
                            </div>
                        `;
                    } else {
                        let text = xhr.responseText || 'Upload failed';
                        this.statusContainer.innerHTML = `
                            <div class="status-message status-error">
                                <i class="fas fa-exclamation-triangle"></i>
                                <span>Upload failed. ${text}</span>
                            </div>
                        `;
                    }
                };
                xhr.onerror = () => {
                    this.statusContainer.innerHTML = `
                        <div class="status-message status-error">
                            <i class="fas fa-exclamation-triangle"></i>
                            <span>Upload failed. Please try again.</span>
                        </div>
                    `;
                };
                xhr.send(formData);
            }
        }
        document.addEventListener('DOMContentLoaded', () => {
            new TranscriptionApp();
        });
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
            corrected_text = normalize_text_offline(text)
            sent_msg = None
            try:
                markup = InlineKeyboardMarkup()
                uid_key = str(chat_id_inner)
                user_mode = get_user_send_mode(uid_key)
                if len(corrected_text) > 4000:
                    if user_mode == "file":
                        fobj = io.BytesIO(corrected_text.encode("utf-8"))
                        fobj.name = "transcription.txt"
                        sent_msg = bot_to_use.send_document(chat_id_inner, fobj, reply_markup=markup)
                    else:
                        chunks = split_text_into_chunks(corrected_text, limit=4096)
                        last_sent = None
                        for idx, chunk in enumerate(chunks):
                            if idx == 0:
                                last_sent = bot_to_use.send_message(chat_id_inner, chunk)
                            else:
                                last_sent = bot_to_use.send_message(chat_id_inner, chunk)
                        sent_msg = last_sent
                else:
                    sent_msg = bot_to_use.send_message(chat_id_inner, corrected_text or "No transcription text was returned.", reply_markup=markup)
                try:
                    buttons = []
                    #buttons.append(InlineKeyboardButton("⭐Clean transcript", callback_data=f"clean_up|{chat_id_inner}|{sent_msg.message_id}"))
                    if len(corrected_text) > 1000:
                        buttons.append(InlineKeyboardButton("Get Summarize", callback_data=f"get_key_points|{chat_id_inner}|{sent_msg.message_id}"))
                    for b in buttons:
                        markup.add(b)
                    bot_to_use.edit_message_reply_markup(chat_id_inner, sent_msg.message_id, reply_markup=markup)
                except Exception:
                    pass
            except Exception:
                try:
                    bot_to_use.send_message(chat_id_inner, "Error sending transcription message. The transcription completed but could not be delivered as a message.")
                except Exception:
                    pass
                return
            try:
                uid_key = str(chat_id_inner)
                user_transcriptions.setdefault(uid_key, {})[sent_msg.message_id] = corrected_text
                threading.Thread(target=delete_transcription_later, args=(uid_key, sent_msg.message_id), daemon=True).start()
                increment_processing_count(str(chat_id_inner), "stt")
            except Exception:
                pass
        finally:
            try:
                os.remove(path)
            except Exception:
                pass
    tmp_path = bytes_to_tempfile(file_bytes)
    threading.Thread(target=process_uploaded_file, args=(chat_id, lang, tmp_path, bot_index), daemon=True).start()
    return jsonify({"status": "accepted", "message": "Upload accepted. Processing started. Your transcription will be sent to your Telegram chat when ready."})

def ask_gemini(text: str, instruction: str, timeout=REQUEST_TIMEOUT_GEMINI) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": instruction},
                    {"text": text}
                ]
            }
        ]
    }
    headers = {"Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    result = resp.json()
    if "candidates" in result and isinstance(result["candidates"], list) and len(result["candidates"]) > 0:
        cand = result['candidates'][0]
        try:
            return cand['content']['parts'][0]['text']
        except Exception:
            return json.dumps(cand)
    return json.dumps(result)

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
                current_mode = get_user_send_mode(str(message.from_user.id))
                mode_text = "📄 .txt file" if current_mode == "file" else "💬 Split messages"
                bot_obj.send_message(message.chat.id, f"Result delivery mode: {mode_text}. Change it below:", reply_markup=build_result_mode_keyboard())
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
                f"👋 Salaam!    \n"
                "• Send me\n"
                "• voice message\n"
                "• audio file\n"
                "• video\n"
                "• to transcribe for free ⭐️Other free bot is: @TextToSpeechBBot"
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
                "/lang  - Change result delivery mode\n"
                "/help  - This help message\n\n"
                "Send a voice/audio/video (up to 20MB for Telegram) and I will transcribe it.\n"
                "If it's larger than Telegram limits, you'll be provided a secure web upload link (supports up to 250MB) Need more help? Contact: @boyso20"  
            )
            bot_obj.send_message(message.chat.id, text)
        except Exception:
            logging.exception("Error in handle_help")

    @bot_obj.message_handler(commands=['lang'])
    def handle_lang(message):
        try:
            kb = build_lang_keyboard("stt_lang")
            bot_obj.send_message(message.chat.id, "Choose your file language for transcription using the below buttons:", reply_markup=kb)
            current_mode = get_user_send_mode(str(message.from_user.id))
            mode_text = "📄 .txt file" if current_mode == "file" else "💬 Split messages"
            bot_obj.send_message(message.chat.id, f"Result delivery mode: {mode_text}. Change it below:", reply_markup=build_result_mode_keyboard())
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

    @bot_obj.callback_query_handler(lambda c: c.data and c.data.startswith("result_mode|"))
    def on_result_mode_select(call):
        try:
            uid = str(call.from_user.id)
            _, mode = call.data.split("|", 1)
            set_user_send_mode(uid, mode)
            mode_text = "📄 .txt file" if mode == "file" else "💬 Split messages"
            try:
                bot_obj.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass
            bot_obj.answer_callback_query(call.id, f"✅ Result mode set: {mode_text}")
        except Exception:
            logging.exception("Error in on_result_mode_select")
            try:
                bot_obj.answer_callback_query(call.id, "❌ Error setting result mode", show_alert=True)
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
                bot_obj.send_message(message.chat.id, "Thanks for adding me! I'm ready to transcribe your media files.")
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

    @bot_obj.message_handler(content_types=['text'], func=lambda message: message.chat.id == ADMIN_ID and message.text == "Total Users")
    def handle_total_users(message):
        try:
            total_users = users_collection.count_documents({})
            bot_obj.send_message(message.chat.id, f"Total users registered: {total_users}")
            bot_obj.send_message(
                message.chat.id,
                "What else, Admin?",
                reply_markup=build_admin_keyboard()
            )
        except Exception:
            logging.exception("Error in handle_total_users")

    @bot_obj.message_handler(content_types=['text'], func=lambda message: message.chat.id == ADMIN_ID and message.text == "Send Broadcast")
    def handle_send_broadcast(message):
        try:
            admin_broadcast_state[message.chat.id] = True
            bot_obj.send_message(message.chat.id, "Okay, Admin. Send me the message (text, photo, video, document, etc.) you want to broadcast to all users. To cancel, type /cancel_broadcast")
        except Exception:
            logging.exception("Error in handle_send_broadcast")

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
            bot_obj.send_message(message.chat.id, "I can only process voice, audio, video, or document files for transcription. Please send one of those, or use /lang to change your language settings.")
        except Exception:
            logging.exception("Error in handle_text_messages")

    @bot_obj.callback_query_handler(lambda c: c.data and c.data.startswith("get_key_points|"))
    def get_key_points_callback(call):
        try:
            parts = call.data.split("|")
            if len(parts) == 3:
                _, chat_id_part, msg_id_part = parts
            elif len(parts) == 2:
                _, msg_id_part = parts
                chat_id_part = str(call.message.chat.id)
            else:
                bot_obj.answer_callback_query(call.id, "Invalid request", show_alert=True)
                return
            try:
                chat_id_val = int(chat_id_part)
                msg_id = int(msg_id_part)
            except Exception:
                bot_obj.answer_callback_query(call.id, "Invalid message id", show_alert=True)
                return
            uid_key = str(chat_id_val)
            stored = user_transcriptions.get(uid_key, {}).get(msg_id)
            if not stored:
                bot_obj.answer_callback_query(call.id, "⚠️ Get Summarize unavailable (maybe expired)", show_alert=True)
                return
            bot_obj.answer_callback_query(call.id, "Generating...")
            status_msg = bot_obj.send_message(call.message.chat.id, "🔄 Processing...", reply_to_message_id=call.message.message_id)
            stop_animation = {"stop": False}
            def stop_event():
                return stop_animation["stop"]
            animation_thread = threading.Thread(target=animate_processing_message, args=(bot_obj, call.message.chat.id, status_msg.message_id, stop_event))
            animation_thread.start()
            try:
                lang = get_stt_user_lang(str(chat_id_val)) or "en"
                instruction = f"Summarize this text (lang={lang}) without adding any introductions, notes, or extra phrases."
                try:
                    summary = ask_gemini(stored, instruction)
                except Exception:
                    summary = extract_key_points_offline(stored, max_points=6)
            except Exception:
                summary = ""
            stop_animation["stop"] = True
            animation_thread.join()
            if not summary:
                try:
                    bot_obj.edit_message_text("No Summary returned.", chat_id=call.message.chat.id, message_id=status_msg.message_id)
                except Exception:
                    pass
            else:
                try:
                    bot_obj.edit_message_text(f"{summary}", chat_id=call.message.chat.id, message_id=status_msg.message_id)
                except Exception:
                    pass
        except Exception:
            logging.exception("Error in get_key_points_callback")

    @bot_obj.callback_query_handler(lambda c: c.data and c.data.startswith("clean_up|"))
    def clean_up_callback(call):
        try:
            parts = call.data.split("|")
            if len(parts) == 3:
                _, chat_id_part, msg_id_part = parts
            elif len(parts) == 2:
                _, msg_id_part = parts
                chat_id_part = str(call.message.chat.id)
            else:
                bot_obj.answer_callback_query(call.id, "Invalid request", show_alert=True)
                return
            try:
                chat_id_val = int(chat_id_part)
                msg_id = int(msg_id_part)
            except Exception:
                bot_obj.answer_callback_query(call.id, "Invalid message id", show_alert=True)
                return
            uid_key = str(chat_id_val)
            stored = user_transcriptions.get(uid_key, {}).get(msg_id)
            if not stored:
                bot_obj.answer_callback_query(call.id, "⚠️ Clean up unavailable (maybe expired)", show_alert=True)
                return
            bot_obj.answer_callback_query(call.id, "Cleaning up...")
            status_msg = bot_obj.send_message(call.message.chat.id, "🔄 Processing...", reply_to_message_id=call.message.message_id)
            stop_animation = {"stop": False}
            def stop_event():
                return stop_animation["stop"]
            animation_thread = threading.Thread(target=animate_processing_message, args=(bot_obj, call.message.chat.id, status_msg.message_id, stop_event))
            animation_thread.start()
            try:
                lang = get_stt_user_lang(str(chat_id_val)) or "en"
                instruction = f"Clean and normalize this transcription (lang={lang}). Remove ASR artifacts like [inaudible], repeated words, filler noises, timestamps, and incorrect punctuation. Produce a clean, well-punctuated, readable text in the same language. Do not add introductions or explanations."
                try:
                    cleaned = ask_gemini(stored, instruction)
                except Exception:
                    cleaned = normalize_text_offline(stored)
            except Exception:
                cleaned = ""
            stop_animation["stop"] = True
            animation_thread.join()
            if not cleaned:
                try:
                    bot_obj.edit_message_text("No cleaned text returned.", chat_id=call.message.chat.id, message_id=status_msg.message_id)
                except Exception:
                    pass
                return
            uid_key = str(chat_id_val)
            user_mode = get_user_send_mode(uid_key)
            if len(cleaned) > 4000:
                if user_mode == "file":
                    f = io.BytesIO(cleaned.encode("utf-8"))
                    f.name = "transcription_cleaned.txt"
                    try:
                        bot_obj.delete_message(call.message.chat.id, status_msg.message_id)
                    except Exception:
                        pass
                    sent = bot_obj.send_document(call.message.chat.id, f, reply_to_message_id=call.message.message_id)
                    try:
                        user_transcriptions.setdefault(uid_key, {})[sent.message_id] = cleaned
                        threading.Thread(target=delete_transcription_later, args=(uid_key, sent.message_id), daemon=True).start()
                    except Exception:
                        pass
                else:
                    try:
                        bot_obj.delete_message(call.message.chat.id, status_msg.message_id)
                    except Exception:
                        pass
                    chunks = split_text_into_chunks(cleaned, limit=4096)
                    last_sent = None
                    for idx, chunk in enumerate(chunks):
                        if idx == 0:
                            last_sent = bot_obj.send_message(call.message.chat.id, chunk, reply_to_message_id=call.message.message_id)
                        else:
                            last_sent = bot_obj.send_message(call.message.chat.id, chunk)
                    try:
                        user_transcriptions.setdefault(uid_key, {})[last_sent.message_id] = cleaned
                        threading.Thread(target=delete_transcription_later, args=(uid_key, last_sent.message_id), daemon=True).start()
                    except Exception:
                        pass
            else:
                try:
                    bot_obj.edit_message_text(f"{cleaned}", chat_id=call.message.chat.id, message_id=status_msg.message_id)
                    uid_key = str(chat_id_val)
                    user_transcriptions.setdefault(uid_key, {})[status_msg.message_id] = cleaned
                    threading.Thread(target=delete_transcription_later, args=(uid_key, status_msg.message_id), daemon=True).start()
                except Exception:
                    pass
        except Exception:
            logging.exception("Error in clean_up_callback")

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
