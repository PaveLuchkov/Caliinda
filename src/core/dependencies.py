# src/core/dependencies.py
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from google.oauth2 import credentials
from google.auth.transport import requests as google_requests

from src.core.database import get_db_session
from src.core.config import settings
from src.users import models as user_models
from src.users import crud as users_crud
from src.auth.service import AuthService
from src.calendar.service import GoogleCalendarService

# Зависимость для получения сессии БД
from typing import Generator

def get_db() -> Generator[Session, None, None]:
    with get_db_session() as db:
        yield db

# Улучшенная зависимость для получения текущего пользователя
async def get_current_user(
    authorization: str = Header(...), db: Session = Depends(get_db)
) -> user_models.User:
    scheme, _, token = authorization.partition(' ')
    if not scheme or scheme.lower() != 'bearer' or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization scheme")
    
    auth_service = AuthService(db) # Используем наш новый сервис
    try:
        id_info = await auth_service.verify_google_id_token(token)
        user_google_id = id_info.get('sub')
        
        user = users_crud.get_user_by_google_id(db, user_google_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not registered")
        
        return user
    except HTTPException as e:
        raise e

# Супер-полезная зависимость, которая "собирает" сервис календаря для эндпоинта
def get_calendar_service(
    current_user: user_models.User = Depends(get_current_user)
) -> GoogleCalendarService:
    if not current_user.refresh_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Google Calendar access not configured or token revoked. Please sign in again."
        )
    
    try:
        creds = credentials.Credentials.from_authorized_user_info(
            info={
                "refresh_token": current_user.refresh_token,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "token_uri": "https://oauth2.googleapis.com/token",
            },
            scopes=settings.SCOPES
        )
        
        if creds.expired and creds.refresh_token:
            creds.refresh(google_requests.Request())
            # TODO: Здесь можно сохранить обновленный access_token в БД, если нужно
        
        return GoogleCalendarService(creds)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create calendar service: {e}")