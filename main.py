import os
import logging
import requests
import telebot
import json
from flask import Flask, request, abort, jsonify
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BOT_TOKENS = [
    os.environ.get("BOT_TOKEN_1", "8107285502:AAGsDRaO8aY8dYnaDHkniWoEBHDD4svuFU8"),
    os.environ.get("BOT_TOKEN_2", "7770743573:AAFtj6Eq-laEzWgK0vG7qc6bqy6r-Te4fLk"),
]
WEBHOOK_BASE = os.environ.get("WEBHOOK_BASE", "https://civilian-cherri-cadenuux57-b04883d4.koyeb.app/")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6964068910"))
SECRET_KEY = os.environ.get("SECRET_KEY", "super-secret-please-change")

app = Flask(__name__)

bots = []
for token in BOT_TOKENS:
    bots.append(telebot.TeleBot(token, threaded=True, parse_mode='HTML'))

users_store = {}
groups_store = {}
admin_broadcast_state = {}
memory_lock = threading.Lock()

def build_admin_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Send Broadcast", callback_data="admin_send_broadcast"))
    markup.add(InlineKeyboardButton("Total Users", callback_data="admin_total_users"))
    return markup

def update_user_activity(user_id: int, chat_title: str = None, chat_type: str = None):
    uid = str(user_id)
    now = datetime.utcnow()
    with memory_lock:
        u = users_store.get(uid)
        if u:
            u["last_active"] = now
        else:
            users_store[uid] = {"first_seen": now, "last_active": now, "chat_title": chat_title or "", "chat_type": chat_type or ""}

def register_handlers(bot_obj, bot_index):
    @bot_obj.message_handler(commands=['start', 'admin'])
    def start_handler(message):
        try:
            if message.chat.id == ADMIN_ID and message.text and message.text.lower().startswith('/admin'):
                bot_obj.send_message(message.chat.id, "Admin panel", reply_markup=build_admin_keyboard())
            else:
                update_user_activity(message.from_user.id)
                text = "⚠️This Bot not working new use this https://t.me/MediaToTextBot"
                bot_obj.send_message(message.chat.id, text, disable_web_page_preview=True)
        except Exception:
            logging.exception("start_handler error")

    @bot_obj.callback_query_handler(func=lambda c: c.data and c.data.startswith("admin_"))
    def admin_inline_callback(call):
        try:
            if call.from_user.id != ADMIN_ID:
                bot_obj.answer_callback_query(call.id, "Unauthorized", show_alert=True)
                return
            if call.data == "admin_total_users":
                with memory_lock:
                    total_users = len(users_store)
                bot_obj.edit_message_text(f"Total users seen: {total_users}", chat_id=call.message.chat.id, message_id=call.message.message_id)
                bot_obj.send_message(call.message.chat.id, "What else, Admin?", reply_markup=build_admin_keyboard())
                bot_obj.answer_callback_query(call.id)
            elif call.data == "admin_send_broadcast":
                admin_broadcast_state[call.message.chat.id] = True
                bot_obj.send_message(call.message.chat.id, "Send the message you want to broadcast to all known users. To cancel, type /cancel_broadcast")
                bot_obj.answer_callback_query(call.id, "Send your broadcast message now")
            else:
                bot_obj.answer_callback_query(call.id)
        except Exception:
            logging.exception("admin_inline_callback error")

    @bot_obj.message_handler(commands=['cancel_broadcast'])
    def cancel_broadcast(message):
        try:
            if message.chat.id in admin_broadcast_state:
                del admin_broadcast_state[message.chat.id]
            bot_obj.send_message(message.chat.id, "Broadcast cancelled. What else, Admin?", reply_markup=build_admin_keyboard())
        except Exception:
            logging.exception("cancel_broadcast error")

    @bot_obj.message_handler(func=lambda message: message.chat.id == ADMIN_ID and admin_broadcast_state.get(message.chat.id, False), content_types=['text', 'photo', 'video', 'document', 'audio', 'voice'])
    def handle_broadcast_message(message):
        try:
            if message.chat.id in admin_broadcast_state:
                del admin_broadcast_state[message.chat.id]
            bot_obj.send_message(message.chat.id, "Broadcasting your message now...")
            with memory_lock:
                all_users = list(users_store.keys())
            sent_count = 0
            failed_count = 0
            for uid_str in all_users:
                try:
                    uid = int(uid_str)
                    if uid == ADMIN_ID:
                        continue
                    try:
                        bot_obj.copy_message(uid, message.chat.id, message.message_id)
                        sent_count += 1
                    except telebot.apihelper.ApiTelegramException as e:
                        logging.error(f"broadcast fail to {uid}: {e}")
                        failed_count += 1
                    time.sleep(0.05)
                except Exception:
                    failed_count += 1
            bot_obj.send_message(message.chat.id, f"Broadcast complete! Sent to {sent_count} users. Failed for {failed_count} users.")
            bot_obj.send_message(message.chat.id, "What else, Admin?", reply_markup=build_admin_keyboard())
        except Exception:
            logging.exception("handle_broadcast_message error")

    @bot_obj.message_handler(content_types=['new_chat_members'])
    def handle_new_chat_members(message):
        try:
            if message.new_chat_members and message.new_chat_members[0].id == bot_obj.get_me().id:
                group_id = str(message.chat.id)
                groups_store[group_id] = {"title": message.chat.title or "", "type": message.chat.type or "", "added_date": datetime.utcnow()}
                bot_obj.send_message(message.chat.id, "Admin panel enabled. This instance is for administration only.")
        except Exception:
            logging.exception("handle_new_chat_members error")

    @bot_obj.message_handler(content_types=['left_chat_member'])
    def handle_left_chat_member(message):
        try:
            if message.left_chat_member and message.left_chat_member.id == bot_obj.get_me().id:
                groups_store.pop(str(message.chat.id), None)
        except Exception:
            logging.exception("handle_left_chat_member error")

    @bot_obj.message_handler(content_types=['voice', 'audio', 'video', 'document', 'photo'])
    def handle_media_types(message):
        try:
            update_user_activity(message.from_user.id)
            text = "This bot only offers an admin panel. To transcribe or summarize media, please use: https://t.me/MediaToTextBot"
            bot_obj.send_message(message.chat.id, text, disable_web_page_preview=True, reply_to_message_id=message.message_id)
        except Exception:
            logging.exception("handle_media_types error")

    @bot_obj.message_handler(content_types=['text'])
    def handle_text_messages(message):
        try:
            update_user_activity(message.from_user.id)
            if message.chat.id == ADMIN_ID:
                bot_obj.send_message(message.chat.id, "Admin panel", reply_markup=build_admin_keyboard())
            else:
                text = "This bot only offers an admin panel. To transcribe or summarize media, please use: https://t.me/MediaToTextBot"
                bot_obj.send_message(message.chat.id, text, disable_web_page_preview=True)
        except Exception:
            logging.exception("handle_text_messages error")

for idx, bot in enumerate(bots):
    register_handlers(bot, idx)

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
    for idx, bot in enumerate(bots):
        try:
            url = WEBHOOK_BASE.rstrip("/") + f"/?bot_index={idx}"
            bot.delete_webhook()
            time.sleep(0.2)
            bot.set_webhook(url=url)
            results.append({"index": idx, "url": url, "status": "ok"})
        except Exception as e:
            logging.error(f"set_webhook error for bot {idx}: {e}")
            results.append({"index": idx, "error": str(e)})
    return jsonify({"results": results}), 200

@app.route("/delete_webhook", methods=["GET", "POST"])
def delete_webhook_route():
    results = []
    for idx, bot in enumerate(bots):
        try:
            bot.delete_webhook()
            results.append({"index": idx, "status": "deleted"})
        except Exception as e:
            logging.error(f"delete_webhook error for bot {idx}: {e}")
            results.append({"index": idx, "error": str(e)})
    return jsonify({"results": results}), 200

def set_webhook_on_startup():
    for idx, bot in enumerate(bots):
        try:
            bot.delete_webhook()
            time.sleep(0.2)
            url = WEBHOOK_BASE.rstrip("/") + f"/?bot_index={idx}"
            bot.set_webhook(url=url)
            logging.info(f"Webhook set to {url}")
        except Exception as e:
            logging.error(f"Failed to set webhook on startup: {e}")

if __name__ == "__main__":
    try:
        set_webhook_on_startup()
    except Exception:
        logging.exception("startup error")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
