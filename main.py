import os
import asyncio
import logging
import threading
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from bot.handlers import router as bot_router
from bot.middlewares import DbSessionMiddleware
from webapp_api import api
from flask import send_from_directory

# Setup Logging
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

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

# Serve React/Web App static files
@api.route('/webapp')
def serve_webapp():
    return send_from_directory('webapp', 'index.html')

@api.route('/webapp/<path:path>')
def serve_webapp_assets(path):
    return send_from_directory('webapp', path)

if __name__ == '__main__':
    # Start Aiogram bot in a background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Start Flask app in the main thread (Render binds to PORT here)
    port = int(os.environ.get('PORT', 5000))
    logging.info(f"Starting Flask server on port {port}...")
    api.run(host='0.0.0.0', port=port)
