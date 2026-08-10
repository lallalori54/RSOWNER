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

# YEH BADALNA HAI: Apne admin group ka ID daalna
# Nikalne ka tarika: @getidsbot ko group mein add karo, /id likho
ADMIN_GROUP_ID = https://t.me/+sd5xVtUYLGBjNjE1

TOPIC_MAP_FILE = "/tmp/topic_map.json"
app = Flask(__name__)

# ==================== STORAGE ====================
def load_map():
    try:
        with open(TOPIC_MAP_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_map(data):
    try:
        with open(TOPIC_MAP_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Save error: {e}")

# ==================== HELPERS ====================
def extract_user_id(text):
    """Extract user ID from message text/caption."""
    if not text:
        return None
    m = re.search(r'🆔\s*ID:\s*(\d+)', text)
    if m:
        return int(m.group(1))
    m = re.search(r'\(ID:\s*(\d+)\)', text)
    if m:
        return int(m.group(1))
    return None

async def get_user_topic(context, user):
    """Get or create forum topic for a user."""
    mapping = load_map()
    uid = str(user.id)
    
    if uid in mapping:
        return int(mapping[uid])
    
    # Create new topic
    name = f"👤 {user.first_name[:15]} | ID:{user.id}"
    try:
        topic = await context.bot.create_forum_topic(
            chat_id=ADMIN_GROUP_ID,
            name=name
        )
        thread_id = topic.message_thread_id
        
        # Permanent header in topic
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
        
        mapping[uid] = thread_id
        save_map(mapping)
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
    """Forward user messages to admin topic."""
    user = update.effective_user
    msg = update.message
    
    # Ignore messages from admin group itself
    if msg.chat_id == ADMIN_GROUP_ID:
        return
    
    topic_id = await get_user_topic(context, user)
    time_str = datetime.now().strftime("%H:%M")
    
    if msg.text:
        text = (
            f"⏰ <b>{time_str}</b> | 🆔 <code>{user.id}</code>\n"
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
        # Media, sticker, etc.
        header_text = f"⏰ <b>{time_str}</b> | 🆔 <code>{user.id}</code>"
        
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
    
    # Confirm to user
    await msg.reply_text("✅ <b>Message delivered!</b> Please wait for response.", parse_mode="HTML")

async def handle_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin replies in the group."""
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_GROUP_ID:
        return
    
    msg = update.message
    
    # Admin must reply to a message
    if not msg.reply_to_message:
        return
    
    replied = msg.reply_to_message
    user_id = None
    
    # Check replied message itself
    user_id = extract_user_id(replied.text) or extract_user_id(replied.caption)
    
    # Check if replied message is a reply to header (for stickers/media)
    if not user_id and replied.reply_to_message:
        user_id = extract_user_id(replied.reply_to_message.text) or extract_user_id(replied.reply_to_message.caption)
    
    if not user_id:
        return  # Not a user message, ignore silently
    
    # Send to user (supports sticker, photo, video, doc, voice, text — everything)
    try:
        await msg.copy(chat_id=user_id)
        await msg.reply_text(f"✅ <b>Sent to user</b> <code>{user_id}</code>", parse_mode="HTML")
    except Exception as e:
        await msg.reply_text(f"❌ <b>Failed:</b> {escape(str(e))}", parse_mode="HTML")

# ==================== BUILD ====================
def build_app():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    # Admin group messages first
    application.add_handler(MessageHandler(filters.Chat(chat_id=ADMIN_GROUP_ID), handle_admin))
    # User messages
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
