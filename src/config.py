# config.py
import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла в переменные окружения ОС
load_dotenv()

# Параметры БД
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "auth_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD") # Обязательно должен быть в .env

# Формируем URL для SQLAlchemy (без SSL для локального Docker)
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Google Секреты
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# Scopes (остаются как были)
SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'openid',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/userinfo.email'
]


REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_DB = int(os.getenv("REDIS_DB_HISTORY", 0)) # Отдельная БД для истории
HISTORY_TTL_SECONDS = int(os.getenv("HISTORY_TTL_SECONDS", 10)) # Время жизни истории (30 минут)
MAX_HISTORY_LENGTH = int(os.getenv("MAX_HISTORY_LENGTH", 15)) # Макс. кол-во сообщений в истории


# Проверка наличия обязательных переменных
if not all([DB_PASSWORD, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET]):
    raise ValueError("One or more essential environment variables (DB_PASSWORD, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET) are missing. Check your .env file.")