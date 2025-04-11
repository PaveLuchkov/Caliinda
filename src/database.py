# database.py
from sqlalchemy import create_engine, Column, String, Text, DateTime, Index, func # Добавили func
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.sql import func as sql_func # Переименовали импорт func, чтобы не конфликтовать с Column func
from contextlib import contextmanager
import logging
import config # Импортируем наш конфиг

logger = logging.getLogger(__name__)

try:
    # Используем DATABASE_URL из конфига
    engine = create_engine(config.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    logger.info("Database engine created successfully for local DB.")
    # Проверка соединения (опционально, но полезно)
    with engine.connect() as connection:
         logger.info("Successfully connected to the local database.")
except Exception as e:
    logger.error(f"Failed to create database engine or connect: {e}", exc_info=True)
    raise

# --- Модель User (та же, что и раньше) ---
class User(Base):
    __tablename__ = "users"
    google_id = Column(String(255), primary_key=True)
    email = Column(String(255), unique=True, index=True)
    full_name = Column(String(255), nullable=True)
    refresh_token = Column(Text, nullable=True)
    # Используем sqlalchemy.sql.func для server_default и onupdate
    created_at = Column(DateTime(timezone=True), server_default=sql_func.now())
    # Используем func.now() или text('CURRENT_TIMESTAMP') для onupdate в PostgreSQL
    # onupdate=sql_func.now() работает для многих бэкендов, включая PG 10+
    updated_at = Column(DateTime(timezone=True), server_default=sql_func.now(), onupdate=sql_func.now())

# --- Функция для получения сессии БД (та же) ---
@contextmanager
def get_db_session(): # Переименовал для ясности, что это сессия
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Функции для работы с пользователями (те же) ---
from typing import Optional # Добавим импорт Optional

def get_user_by_google_id(db_session, google_id: str) -> Optional[User]:
    return db_session.query(User).filter(User.google_id == google_id).first()

def upsert_user_token(db_session, google_id: str, email: str, full_name: Optional[str], refresh_token: str):
    user = get_user_by_google_id(db_session, google_id)
    if user:
        logger.info(f"Updating refresh token for user: {email} (ID: {google_id})")
        user.refresh_token = refresh_token
        user.email = email
        if full_name:
            user.full_name = full_name
        # updated_at обновится автоматически через onupdate=func.now()
    else:
        logger.info(f"Creating new user and storing refresh token for: {email} (ID: {google_id})")
        user = User(
            google_id=google_id,
            email=email,
            full_name=full_name,
            refresh_token=refresh_token
        )
        db_session.add(user)
    try:
        db_session.commit()
        db_session.refresh(user) # Обновить объект user данными из БД (включая default timestamps)
        logger.info(f"User token upserted successfully for {email}")
        return user
    except Exception as e:
        logger.error(f"Database commit failed during upsert for user {email}: {e}", exc_info=True)
        db_session.rollback() # Откатить транзакцию при ошибке
        raise # Перебросить исключение, чтобы FastAPI мог его обработать

def get_refresh_token(db_session, google_id: str) -> Optional[str]:
    user = get_user_by_google_id(db_session, google_id)
    # Добавим логгирование для отладки
    if user:
        logger.debug(f"Refresh token found for user {google_id}")
        return user.refresh_token
    else:
        logger.debug(f"User {google_id} not found in DB.")
        return None

# НЕ НУЖНО создавать таблицы здесь при каждом запуске
# Base.metadata.create_all(bind=engine) # Лучше создать таблицы один раз через psql