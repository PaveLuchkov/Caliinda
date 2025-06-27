# tests/test_calendar_api.py
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from pytest_mock import MockerFixture

from src.users.models import User
from src.core.dependencies import get_current_user

# Тестовые данные
TEST_USER_GOOGLE_ID = "test-google-id-123"
TEST_USER_EMAIL = "test@example.com"
TEST_REFRESH_TOKEN = "fake-refresh-token"

def test_get_events_range_success(
    client: TestClient, db_session: Session, mocker: MockerFixture
):
    # --- ARRANGE (Подготовка) ---

    # 1. Создаем пользователя в чистой БД, которая живет на протяжении всего теста
    test_user = User(
        google_id=TEST_USER_GOOGLE_ID,
        email=TEST_USER_EMAIL,
        refresh_token=TEST_REFRESH_TOKEN,
    )
    db_session.add(test_user)
    db_session.commit()

    # 2. Мокаем зависимость get_current_user
    # Важно: эта подмена будет жить только во время этого теста
    def override_get_current_user() -> User:
        # Наш тестовый пользователь, которого мы только что создали
        return db_session.query(User).filter(User.google_id == TEST_USER_GOOGLE_ID).one()

    client.app.dependency_overrides[get_current_user] = override_get_current_user

    # 3. Мокаем Google Calendar API
    mock_calendar_service_class = mocker.patch("src.calendar.service.GoogleCalendarService")
    fake_events = [{"id": "event1", "summary": "Test Event 1"}]
    mock_calendar_service_class.return_value.get_events.return_value = fake_events

    # --- ACT (Действие) ---
    response = client.get(
        "/calendar/events/range?startDate=2023-10-27&endDate=2023-10-29",
        headers={"Authorization": "Bearer fake-id-token"},
    )

    # --- ASSERT (Проверка) ---
    assert response.status_code == 200
    assert response.json()[0]['summary'] == "Test Event 1"

    # --- CLEANUP (Очистка) ---
    client.app.dependency_overrides.clear()