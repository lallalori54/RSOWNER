import os
import re
import json
import asyncio
from html import escape
from datetime import datetime
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8892866207:AAFWJv_F7SjP1rWkM_oTCfKf9YOL3YAC1XI"
ADMIN_GROUP_ID = -1004356447626
TOPIC_MAP_FILE = "/tmp/topic_map.json"
app = Flask(__name__)

def load_data():
    try:
        with open(TOPIC_MAP_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"user_to_topic": {}, "topic_to_user": {}}

def save_data(data):
    try:
        with open(TOPIC_MAP_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Save error: {e}")

def extract_user_id(text):
    if not text:
        return None
    m = re.search(r'🆔\s*UID\s*:\s*(\d+)', text)
    if m:
        return int(m.group(1))
    m = re.search(r'🆔\s*(\d{6,})', text)
    if m:
        return int(m.group(1))
    m = re.search(r'ID\s*:\s*(\d{6,})', text)
    if m:
        return int(m.group(1))
    m = re.search(r'<code>(\d{6,})</code>', text)
    if m:
        return int(m.group(1))
    return None

async def get_user_topic(context, user):
    data = load_data()
    uid = str(user.id)
    
    if uid in data["user_to_topic"]:
        return int(data["user_to_topic"][uid])
    
    display = f"@{user.username}" if user.username else user.first_name
    name = f"👤 {display[:30]}"
    
    try:
        topic = await context.bot.create_forum_topic(
            chat_id=ADMIN_GROUP_ID,
            name=name
        )
        thread_id = topic.message_thread_id
        
        header = (
            f"┌─ <b>👤 USER INFO</b>\n"
            f"├ <b>Name:</b> {escape(user.first_name)}\n"
            f"├ <b>Username:</b> @{escape(user.username or 'N/A')}\n"
            f"├ 🆔 <b>UID:</b> <code>{user.id}</code>\n"
            f"├ 🔗 <a href='tg://user?id={user.id}'>Open Profile</a>\n"
            f"└─{'━'*30}"
        )
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            message_thread_id=thread_id,
            text=header,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        
        data["user_to_topic"][uid] = thread_id
        data["topic_to_user"][str(thread_id)] = user.id
        save_data(data)
        return thread_id
        
    except Exception as e:
        print(f"Topic error: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>Welcome to Support Center!</b>\n\n"
        "📩 Send your message here.\n"
        "Our team will reply shortly.\n\n"
        "✅ Supported: text, photos, videos, stickers, docs, voice, location",
        parse_mode="HTML"
    )

async def handle_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.message
    
    if msg.chat_id == ADMIN_GROUP_ID:
        return
    
    topic_id = await get_user_topic(context, user)
    time_str = datetime.now().strftime("%H:%M")
    name_display = escape(user.first_name)
    
    # UID line - REQUIRED for admin reply to work when mapping is lost
    uid_line = f"🆔 UID: {user.id}"
    
    try:
        if msg.text:
            text = (
                f"⏰ <b>{time_str}</b> | <b>{name_display}</b>\n"
                f"{uid_line}\n"
                f"{'━'*20}\n"
                f"{escape(msg.text)}"
            )
            if topic_id:
                await context.bot.send_message(
                    chat_id=ADMIN_GROUP_ID,
                    message_thread_id=topic_id,
                    text=text,
                    parse_mode="HTML"
                )
            else:
                await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=text, parse_mode="HTML")
        else:
            header_text = (
                f"⏰ <b>{time_str}</b> | <b>{name_display}</b>\n"
                f"{uid_line}"
            )
            if topic_id:
                header = await context.bot.send_message(
                    chat_id=ADMIN_GROUP_ID,
                    message_thread_id=topic_id,
                    text=header_text,
                    parse_mode="HTML"
                )
                await msg.copy(
                    chat_id=ADMIN_GROUP_ID,
                    message_thread_id=topic_id,
                    reply_to_message_id=header.message_id
                )
            else:
                header = await context.bot.send_message(
                    chat_id=ADMIN_GROUP_ID,
                    text=header_text,
                    parse_mode="HTML"
                )
                await msg.copy(
                    chat_id=ADMIN_GROUP_ID,
                    reply_to_message_id=header.message_id
                )
        
        # 1 second auto-delete
        confirm = await msg.reply_text("✅ <b>Message delivered!</b>", parse_mode="HTML")
        await asyncio.sleep(1)
        try:
            await confirm.delete()
        except:
            pass
        
    except Exception as e:
        print(f"Forward error: {e}")
        await msg.reply_text("❌ <b>Failed to send message.</b>", parse_mode="HTML")

async def handle_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_GROUP_ID:
        return
    
    msg = update.message
    user_id = None
    
    # Method 1: Topic mapping (works for fresh messages if /tmp still exists)
    if msg.message_thread_id:
        data = load_data()
        user_id = data.get("topic_to_user", {}).get(str(msg.message_thread_id))
    
    # Method 2: Reply to user message (ALWAYS works because UID is in every msg)
    if not user_id and msg.reply_to_message:
        replied = msg.reply_to_message
        user_id = extract_user_id(replied.text) or extract_user_id(replied.caption)
        # Check the header message (for media posts)
        if not user_id and replied.reply_to_message:
            user_id = extract_user_id(replied.reply_to_message.text) or extract_user_id(replied.reply_to_message.caption)
    
    # Method 3: Walk up reply chain
    if not user_id and msg.reply_to_message:
        current = msg.reply_to_message
        depth = 0
        while current and depth < 5:
            user_id = extract_user_id(current.text) or extract_user_id(current.caption)
            if user_id:
                break
            current = current.reply_to_message
            depth += 1
    
    if not user_id:
        await msg.reply_text(
            "❌ <b>User not found!</b>\n\n"
            "• <b>Reply</b> to any user message (100% works)\n"
            "• Or user hasn't messaged yet",
            parse_mode="HTML"
        )
        return
    
    try:
        await msg.copy(chat_id=user_id)
        
        # 1 second auto-delete
        confirm = await msg.reply_text("✅ <b>Sent!</b>", parse_mode="HTML")
        await asyncio.sleep(1)
        try:
            await confirm.delete()
        except:
            pass
            
    except Exception as e:
        err = str(e).lower()
        if "blocked" in err:
            await msg.reply_text("❌ <b>User blocked the bot.</b>", parse_mode="HTML")
        elif "not found" in err or "chat not found" in err:
            await msg.reply_text("❌ <b>User deleted the chat.</b>", parse_mode="HTML")
        else:
            await msg.reply_text(f"❌ <b>Failed:</b> {escape(str(e))}", parse_mode="HTML")

def build_app():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Chat(chat_id=ADMIN_GROUP_ID), handle_admin))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_user))
    return application

@app.route("/", methods=["GET"])
def home():
    return "✅ SUPPORT BOT ONLINE"

@app.route("/", methods=["POST"])
def webhook():
    try:
        json_data = request.get_json(force=True)
        
        async def process():
            application = build_app()
            await application.initialize()
            await application.start()
            try:
                update = Update.de_json(json_data, application.bot)
                await application.process_update(update)
            finally:
                await application.stop()
                await application.shutdown()
        
        asyncio.run(process())
        return "OK", 200
    except Exception as e:
        print(f"Error: {e}")
        return "Error", 500
