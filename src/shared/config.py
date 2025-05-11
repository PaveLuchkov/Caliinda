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
    'https://www.googleapis.com/auth/calendar',
    'openid',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/userinfo.email'
]
MODEL_OR = "openrouter/google/gemini-2.0-flash-001"
MODEL = "gemini-2.0-flash"
# Google ID: 113750652546884584889, Email: arrtalcompany@gmail.com, Full Name: Pasha, Refresh Token: 1//0ciww42VH1Ph9CgYIARAAGAwSNwF-L9IrPLobJ5vzzrx5mJfo9kcJkucYn3kPNl1AZhHde9e9CV42FfNRGazw0iKo-fZD85cl2sE, Created At: 2025-05-08 17:34:19.299923+00:00, Updated At: 2025-05-08 17:34:19.299923+00:00
# --- ЗАХАРДКОЖЕННЫЕ ДАННЫЕ ДЛЯ ТЕСТА ---
TEST_USER_GOOGLE_ID = "113750652546884584889"
TEST_USER_EMAIL = "arrtalcompany@gmail.com"
HARDCODED_REFRESH_TOKEN = "1//0ciww42VH1Ph9CgYIARAAGAwSNwF-L9IrPLobJ5vzzrx5mJfo9kcJkucYn3kPNl1AZhHde9e9CV42FfNRGazw0iKo-fZD85cl2sE"
TOKEN_URI = "https://oauth2.googleapis.com/token"