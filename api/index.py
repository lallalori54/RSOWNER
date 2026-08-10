import os
import re
import json
import asyncio
from html import escape
from datetime import datetime
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== CONFIG ====================
BOT_TOKEN = "8892866207:AAFWJv_F7SjP1rWkM_oTCfKf9YOL3YAC1XI"
ADMIN_GROUP_ID = -1004356447626
TOPIC_MAP_FILE = "/tmp/topic_map.json"
app = Flask(__name__)

# ==================== STORAGE ====================
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
    # Match: 🆔 12345 or 🆔 ID: 12345 or 🆔 <code>12345</code>
    m = re.search(r'🆔\s*(?:ID\s*:)?\s*(?:<code>)?(\d+)', text)
    if m:
        return int(m.group(1))
    # Fallback
    m = re.search(r'\(ID:\s*(\d+)\)', text)
    if m:
        return int(m.group(1))
    return None

# ==================== TOPIC MANAGEMENT ====================
async def get_user_topic(context, user):
    data = load_data()
    uid = str(user.id)
    
    if uid in data["user_to_topic"]:
        return int(data["user_to_topic"][uid])
    
    # Create topic name with username
    display = f"@{user.username}" if user.username else user.first_name
    name = f"👤 {display[:25]} | ID:{user.id}"
    
    try:
        topic = await context.bot.create_forum_topic(
            chat_id=ADMIN_GROUP_ID,
            name=name
        )
        thread_id = topic.message_thread_id
        
        # Send user info header
        header = (
            f"┌─ <b>👤 USER INFO</b>\n"
            f"├ <b>Name:</b> {escape(user.first_name)}\n"
            f"├ <b>Username:</b> @{escape(user.username or 'N/A')}\n"
            f"├ 🆔 <b>ID:</b> <code>{user.id}</code>\n"
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
        
        # Save both mappings
        data["user_to_topic"][uid] = thread_id
        data["topic_to_user"][str(thread_id)] = user.id
        save_data(data)
        return thread_id
        
    except Exception as e:
        print(f"Topic error: {e}")
        return None

# ==================== HANDLERS ====================
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
    
    # Ignore admin group messages
    if msg.chat_id == ADMIN_GROUP_ID:
        return
    
    topic_id = await get_user_topic(context, user)
    time_str = datetime.now().strftime("%H:%M")
    
    # Build user display with username
    if user.username:
        user_display = f"👤 @{user.username}"
    else:
        user_display = f"👤 {escape(user.first_name)}"
    
    try:
        if msg.text:
            text = (
                f"⏰ <b>{time_str}</b> | {user_display} | 🆔 <code>{user.id}</code>\n"
                f"{'━'*25}\n"
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
            # Media / sticker / doc / voice etc.
            header_text = f"⏰ <b>{time_str}</b> | {user_display} | 🆔 <code>{user.id}</code>"
            
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
        
        await msg.reply_text("✅ <b>Message delivered!</b> Please wait for response.", parse_mode="HTML")
        
    except Exception as e:
        print(f"Forward error: {e}")
        await msg.reply_text(
            f"❌ <b>Failed to send message.</b>\nError: <code>{escape(str(e))}</code>",
            parse_mode="HTML"
        )

async def handle_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_GROUP_ID:
        return
    
    msg = update.message
    user_id = None
    
    # Method 1: From replied message
    if msg.reply_to_message:
        replied = msg.reply_to_message
        user_id = extract_user_id(replied.text) or extract_user_id(replied.caption)
        if not user_id and replied.reply_to_message:
            user_id = extract_user_id(replied.reply_to_message.text) or extract_user_id(replied.reply_to_message.caption)
    
    # Method 2: From topic thread_id (works even without replying!)
    if not user_id and msg.message_thread_id:
        data = load_data()
        user_id = data.get("topic_to_user", {}).get(str(msg.message_thread_id))
    
    if not user_id:
        await msg.reply_text(
            "❌ <b>Could not find user.</b>\nReply to a user message or send inside a user topic.",
            parse_mode="HTML"
        )
        return
    
    try:
        # Send admin message to user (text, sticker, photo, doc — anything)
        await msg.copy(chat_id=user_id)
        
        # Send confirmation and auto-delete after 10 sec
        confirm = await msg.reply_text("✅ <b>Sent!</b>", parse_mode="HTML")
        await asyncio.sleep(10)
        try:
            await confirm.delete()
        except:
            pass
            
    except Exception as e:
        await msg.reply_text(f"❌ <b>Failed:</b> {escape(str(e))}", parse_mode="HTML")

# ==================== BUILD ====================
def build_app():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Chat(chat_id=ADMIN_GROUP_ID), handle_admin))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_user))
    return application

# ==================== FLASK ====================
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
