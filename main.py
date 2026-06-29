import os
import asyncio
import logging
import threading
from flask import Flask, request, jsonify, send_from_directory
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from bot.handlers import router as bot_router
from bot.middlewares import DbSessionMiddleware
from database.base import get_db, init_db
from services.security import validate_telegram_init_data
from services.whisper_service import WhisperService

# Setup Logging
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# -----------------------------
# 1. FLASK APP & WEB APP API
# -----------------------------
api = Flask(__name__)

@api.before_request
async def startup():
    # Ensure DB tables exist on first request
    await init_db()

@api.route('/api/whisper', methods=['POST'])
async def get_whisper():
    req = request.get_json()
    whisper_id = req.get("whisper_id")
    init_data = req.get("init_data")

    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        return jsonify({"detail": "Bot token not configured"}), 500

    # 1. Validate Telegram Signature
    user_data = validate_telegram_init_data(init_data, bot_token)
    if not user_data:
        return jsonify({"detail": "Invalid or expired authentication"}), 401

    # 2. Extract authenticated user ID
    try:
        user_id = int(user_data.get("user", {}).get("id", 0))
    except (ValueError, TypeError):
        return jsonify({"detail": "Invalid user data"}), 401

    if user_id == 0:
        return jsonify({"detail": "User not found"}), 401

    # 3. Fetch whisper securely
    async for session in get_db():
        service = WhisperService(session)
        whisper = await service.get_whisper_secure(whisper_id, user_id)

        if not whisper:
            return jsonify({"detail": "❌ This whisper is not for you, it has expired, or it was a one-time view."}), 403

        # 4. Return data
        return jsonify({
            "message": whisper.message,
            "media_type": whisper.media_type,
            "media_file_id": whisper.media_file_id,
            "sender_name": None if whisper.is_anonymous else whisper.sender_name,
            "viewed": whisper.viewed,
            "deleted": whisper.delete_after_reading and whisper.viewed
        })

# Serve Web App HTML
@api.route('/webapp')
def serve_webapp():
    return send_from_directory('webapp', 'index.html')

@api.route('/webapp/<path:path>')
def serve_webapp_assets(path):
    return send_from_directory('webapp', path)


# -----------------------------
# 2. TELEGRAM BOT (Background)
# -----------------------------
def run_bot():
    """Function to run aiogram polling in a separate thread."""
    if not BOT_TOKEN:
        logging.error("BOT_TOKEN is not set")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Register middleware and routers
    dp.update.middleware(DbSessionMiddleware())
    dp.include_router(bot_router)

    logging.info("Starting Telegram Bot Polling...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(dp.start_polling(bot))
    except Exception as e:
        logging.error(f"Bot polling error: {e}")
    finally:
        loop.close()


# -----------------------------
# 3. MAIN EXECUTION
# -----------------------------
if __name__ == '__main__':
    # Start Aiogram bot in a background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Start Flask app in the main thread (Render binds to PORT here)
    port = int(os.environ.get('PORT', 5000))
    logging.info(f"Starting Flask server on port {port}...")
    api.run(host='0.0.0.0', port=port)
