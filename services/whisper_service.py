from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timezone
from database.models import Whisper

class WhisperService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_whisper(self, **kwargs) -> Whisper:
        whisper = Whisper(**kwargs)
        self.db.add(whisper)
        await self.db.commit()
        await self.db.refresh(whisper)
        return whisper

    async def get_whisper_secure(self, whisper_id: str, user_id: int) -> Whisper | None:
        """
        Securely fetches whisper. Validates expiration, ownership, and one-time view.
        """
        stmt = select(Whisper).where(Whisper.whisper_id == whisper_id)
        result = await self.db.execute(stmt)
        whisper = result.scalar_one_or_none()

        if not whisper:
            return None

        # Check expiration
        if whisper.expires_at and whisper.expires_at < datetime.now(timezone.utc):
            return None

        # Check recipient authorization (User ID takes precedence)
        if whisper.recipient_user_id and whisper.recipient_user_id != user_id:
            return None

        # Handle one-time view logic
        if whisper.is_one_time and whisper.viewed:
            return None

        # Mark as viewed if accessed for the first time
        if not whisper.viewed:
            whisper.viewed = True
            whisper.viewed_at = datetime.now(timezone.utc)
            
            if whisper.delete_after_reading:
                await self.db.delete(whisper)
                await self.db.commit()
                return whisper # Return the ghost object to trigger UI deletion
            
            await self.db.commit()
            await self.db.refresh(whisper)

        return whisper
