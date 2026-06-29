from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, ForeignKey
from sqlalchemy.sql import func
from database.base import Base
import uuid

class Whisper(Base):
    __tablename__ = "whispers"

    whisper_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sender_user_id = Column(Integer, nullable=False)
    sender_username = Column(String(255), nullable=True)
    sender_name = Column(String(255), nullable=True)
    is_anonymous = Column(Boolean, default=False)
    
    recipient_user_id = Column(Integer, nullable=True)
    recipient_username = Column(String(255), nullable=True)
    
    message = Column(Text(10000), nullable=False)
    media_file_id = Column(String(255), nullable=True)
    media_type = Column(String(50), nullable=True) # photo, video, document, sticker
    
    is_one_time = Column(Boolean, default=False)
    delete_after_reading = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    viewed = Column(Boolean, default=False)
    viewed_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
