# src/users/crud.py
from sqlalchemy.orm import Session
from typing import Optional
import logging
from .models import User

logger = logging.getLogger(__name__)

def get_user_by_google_id(db: Session, google_id: str) -> Optional[User]:
    return db.query(User).filter(User.google_id == google_id).first()

def upsert_user_token(db: Session, *, google_id: str, email: str, full_name: Optional[str], refresh_token: str) -> User:
    user = get_user_by_google_id(db, google_id)
    if user:
        logger.info(f"Updating refresh token for user: {email}")
        user.refresh_token = refresh_token
        user.email = email
        if full_name:
            user.full_name = full_name
    else:
        logger.info(f"Creating new user: {email}")
        user = User(
            google_id=google_id,
            email=email,
            full_name=full_name,
            refresh_token=refresh_token
        )
        db.add(user)
    
    try:
        db.commit()
        db.refresh(user)
        return user
    except Exception as e:
        logger.error(f"Database commit failed during upsert for user {email}: {e}", exc_info=True)
        db.rollback()
        raise

def get_refresh_token(db: Session, google_id: str) -> Optional[str]:
    user = get_user_by_google_id(db, google_id)
    return user.refresh_token if user else None