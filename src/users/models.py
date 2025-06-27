# src/users/models.py
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func
from src.core.database import Base

class User(Base):
    __tablename__ = "users"
    google_id = Column(String(255), primary_key=True)
    email = Column(String(255), unique=True, index=True)
    full_name = Column(String(255), nullable=True)
    refresh_token = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())