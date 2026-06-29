import os
import sys
import asyncio
import logging
import threading
import traceback
from flask import Flask, request, jsonify, send_from_directory
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from bot.handlers import router as bot_router
from bot.middlewares import DbSessionMiddleware
from database.base import get_db, init_db
from services.security import validate_telegram_init_data
from services.whisper_service import WhisperService

# -------------------------------------------------------------------
# 1. Setup Logging
# -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# 2. Environment Validation
# -------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")

if not BOT_TOKEN:
    logger.error("FATAL: BOT_TOKEN environment variable is missing. Telegram bot will NOT start.")
if not WEBAPP_URL:
    logger.warning("WARNING: WEBAPP_URL environment variable is missing. Inline Web App buttons may not work correctly.")

# -------------------------------------------------------------------
# 3. Flask App & API Endpoints (Untouched Business Logic)
# -------------------------------------------------------------------
api = Flask(__name__)

@api.before_request
async def startup_db_check():
    # Using a Flask application context variable to ensure DB init runs exactly once
    if not api.config.get("DB_INITIALIZED", False):
        logger.info("Initializing database for the first time...")
        await init_db()
        api.config["DB_INITIALIZED"] = True
        logger.info("Database initialized successfully.")

@api.route('/api/whisper', methods=['POST'])
async def get_whisper():
    req = request.get_json()
    whisper_id = req.get("whisper_id")
    init_data = req.get("init_data")

    if not BOT_TOKEN:
        return jsonify({"detail": "Bot token not configured"}), 500

    user_data = validate_telegram_init_data(init_data, BOT_TOKEN)
    if not user_data:
        return jsonify({"detail": "Invalid or expired authentication"}), 401

    try:
        user_id = int(user_data.get("user", {}).get("id", 0))
    except (ValueError, TypeError):
        return jsonify({"detail": "Invalid user data"}), 401

    if user_id == 0:
        return jsonify({"detail": "User not found"}), 401

    async for session in get_db():
        service = WhisperService(session)
        whisper = await service.get_whisper_secure(whisper_id, user_id)

        if not whisper:
            return jsonify({"detail": "❌ This whisper is not for you, it has expired, or it was a one-time view."}), 403

        return jsonify({
            "message": whisper.message,
            "media_type": whisper.media_type,
            "media_file_id": whisper.media_file_id,
            "sender_name": None if whisper.is_anonymous else whisper.sender_name,
            "viewed": whisper.viewed,
            "deleted": whisper.delete_after_reading and whisper.viewed
        })

@api.route('/webapp')
def serve_webapp():
    return send_from_directory('webapp', 'index.html')

@api.route('/webapp/<path:path>')
def serve_webapp_assets(path):
    return send_from_directory('webapp', path)


# -------------------------------------------------------------------
# 4. Aiogram Background Polling Setup
# -------------------------------------------------------------------
_bot_thread_instance = None
_bot_thread_lock = threading.Lock()

def _run_bot_polling():
    """
    Dedicated thread target to run the aiogram event loop and bot polling.
    Handles exceptions safely and ensures clean loop closure.
    """
    if not BOT_TOKEN:
        logger.error("Cannot start Telegram bot polling: BOT_TOKEN is missing.")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    dp.update.middleware(DbSessionMiddleware())
    dp.include_router(bot_router)

    logger.info("Telegram bot background task started. Beginning polling...")
    try:
        loop.run_until_complete(dp.start_polling(bot))
    except Exception as e:
        logger.error(f"Telegram bot polling encountered an error: {e}\n{traceback.format_exc()}")
    finally:
        logger.info("Telegram bot polling stopped. Closing event loop.")
        # Cleanup pending tasks
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

def _start_bot_thread():
    """
    Starts the bot polling thread exactly once, safely preventing duplicates.
    """
    global _bot_thread_instance
    with _bot_thread_lock:
        if _bot_thread_instance is None or not _bot_thread_instance.is_alive():
            _bot_thread_instance = threading.Thread(target=_run_bot_polling, daemon=True)
            _bot_thread_instance.start()
            logger.info("Background daemon thread for Telegram bot spawned.")
        else:
            logger.debug("Bot polling thread is already running. Skipping duplicate initialization.")


# -------------------------------------------------------------------
# 5. Auto-Start Trigger for Gunicorn
# -------------------------------------------------------------------
# When Gunicorn runs `gunicorn main:api`, it imports the `main` module.
# We hook into Python's module import system to detect when this specific 
# file (`main`) is imported by Gunicorn, triggering the background thread 
# automatically exactly once without needing `if __name__ == '__main__':`.
if not hasattr(sys.modules.get('__main__'), '__file__') or \
   (hasattr(sys.modules.get('__main__'), '__file__') and 
    os.path.basename(sys.modules['__main__'].__file__) == 'main.py'):
    
    # This executes automatically when imported by Gunicorn (`main:api`)
    # OR when run directly (`python main.py`).
    _start_bot_thread()


# -------------------------------------------------------------------
# 6. Direct Execution Block (Optional fallback for local `python main.py`)
# -------------------------------------------------------------------
if __name__ == '__main__':
    # If run directly via `python main.py`, start the Flask development server.
    # Note: The bot thread is already started by the hook above.
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Flask development server on port {port}...")
    try:
        api.run(host='0.0.0.0', port=port)
    except KeyboardInterrupt:
        logger.info("Flask server interrupted by user.")
    finally:
        logger.info("Flask server shut down.")
