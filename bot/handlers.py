import os
import logging
from aiogram import Router, F
from aiogram.types import Message, InlineQuery, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from sqlalchemy.ext.asyncio import AsyncSession
from services.whisper_service import WhisperService
from datetime import datetime, timezone, timedelta

router = Router()
logger = logging.getLogger(__name__)

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🤫 Welcome to Whisper Bot!\n\n"
        "To send a whisper, type:\n"
        "<code>@YourBotUsername Hello, this is a secret!</code>\n\n"
        "You can also attach photos, videos, or documents.",
        parse_mode="HTML"
    )

@router.inline_query()
async def handle_inline_query(inline_query: InlineQuery, db: AsyncSession):
    query_text = inline_query.query.strip()
    if not query_text:
        return

    # In a production app, parse target user/username from the query.
    # For this example, we assume the sender is sending it to themselves 
    # or you would implement a parser like: "@username My message"
    recipient_user_id = inline_query.from_user.id # Fallback for demo
    recipient_username = inline_query.from_user.username

    service = WhisperService(db)
    
    # Determine media
    media_file_id = None
    media_type = None
    if inline_query.query.strip() == "" and inline_query.inline_message_id:
         pass # Handle pure media if needed
         
    if inline_query.photo:
        media_file_id = inline_query.photo[-1].file_id
        media_type = "photo"
    elif inline_query.video:
        media_file_id = inline_query.video.file_id
        media_type = "video"
    elif inline_query.document:
        media_file_id = inline_query.document.file_id
        media_type = "document"
    elif inline_query.sticker:
        media_file_id = inline_query.sticker.file_id
        media_type = "sticker"

    # Save securely to DB (NO raw message in inline result)
    whisper = await service.create_whisper(
        sender_user_id=inline_query.from_user.id,
        sender_username=inline_query.from_user.username,
        recipient_user_id=recipient_user_id,
        recipient_username=recipient_username,
        message=query_text,
        media_file_id=media_file_id,
        media_type=media_type,
        is_one_time=True, # Example flags
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
    )

    webapp_url = os.getenv("WEBAPP_URL", "https://your-domain.com/webapp")
    deep_link = f"{webapp_url}?wid={whisper.whisper_id}"

    # Secure placeholder
    result = InlineQueryResultArticle(
        id=whisper.whisper_id,
        title="🤫 Secret Whisper",
        description="🔒 Tap to Open",
        input_message_content=InputTextMessageContent(
            message_text="🤫 Secret Whisper\n🔒 Tap to Open"
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔓 Open Whisper", web_app=InlineKeyboardWebApp(url=deep_link))]
            ]
        )
    )

    await inline_query.answer(results=[result], cache_time=1)
