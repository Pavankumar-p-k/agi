"""
JARVIS Telegram Bot — bridges Telegram to /api/chat.
Requires: python-telegram-bot==20.7, httpx
"""
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import httpx
import os

JARVIS_URL = os.getenv("JARVIS_SERVER", "http://127.0.0.1:8000")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var not set. Get one from t.me/BotFather")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "JARVIS online. Send any message to chat.\n"
        "/status — system health\n"
        "/search <query> — web search"
    )

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    await update.message.reply_text("Thinking...")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{JARVIS_URL}/api/chat",
                json={"message": user_msg, "tier": "local"},
            )
        data = r.json()
        reply = data.get("response", "Error getting response")
        tags = data.get("epistemic_tags", [])
        if tags:
            reply = f"{reply}\n\nTags: {', '.join(tags)}"
        await update.message.reply_text(reply[:4096])
    except Exception as e:
        await update.message.reply_text(f"JARVIS error: {str(e)[:200]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{JARVIS_URL}/health")
        data = r.json()
        await update.message.reply_text(
            f"JARVIS Status\n"
            f"Server: online\n"
            f"Ollama: {'OK' if data.get('ollama') else 'DOWN'}\n"
            f"STT: {'OK' if data.get('stt_loaded') else 'unloaded'}\n"
            f"TTS: {'OK' if data.get('tts_loaded') else 'unloaded'}\n"
            f"DB: {'OK' if data.get('db_connected') else 'DOWN'}"
        )
    except Exception:
        await update.message.reply_text("Server offline")

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage: /search <your query>")
        return
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{JARVIS_URL}/api/chat",
            json={"message": f"search {query}", "tier": "local"},
        )
    await update.message.reply_text(r.json().get("response", "No results")[:4096])

def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    print(f"[Telegram] Bot polling (server={JARVIS_URL})...")
    app.run_polling()

if __name__ == "__main__":
    run_bot()
