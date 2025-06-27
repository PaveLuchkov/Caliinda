# tests/conftest.py
import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Явно добавляем путь к проекту
import sys
import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from main import app
from src.core.database import Base
from src.core.dependencies import get_db

# --- КЛЮЧЕВОЕ МЕСТО ---
# Явно импортируем все модели SQLAlchemy здесь.
# Это гарантирует, что Base.metadata знает о всех таблицах
# перед тем, как мы вызовем Base.metadata.create_all().
from src.users.models import User # <-- Это самое важное

# --- Настройка тестовой базы данных ---
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False} # Обязательно для SQLite
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Переопределяем зависимость get_db для использования тестовой БД
def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db


# --- Новая, более надежная структура фикстур ---

@pytest.fixture(scope="function")
def setup_database() -> Generator[None, None, None]:
    """
    Фикстура, отвечающая только за создание и удаление таблиц.
    """
    # Убедимся, что метаданные не пусты
    assert len(Base.metadata.tables) > 0, "Модели SQLAlchemy не были импортированы, Base.metadata пуст!"
    
    Base.metadata.create_all(bind=engine)  # Создаем таблицы
    yield
    Base.metadata.drop_all(bind=engine)   # Удаляем таблицы после теста

@pytest.fixture(scope="function")
def db_session(setup_database: None) -> Generator[Session, None, None]:
    """
    Фикстура, которая зависит от setup_database и предоставляет сессию.
    Гарантирует, что таблицы уже созданы.
    """
    db = TestingSessionLocal()
    yield db
    db.close()

@pytest.fixture(scope="function")
def client(setup_database: None) -> Generator[TestClient, None, None]:
    """
    Фикстура для TestClient. Также зависит от setup_database.
    """
    yield TestClient(app)