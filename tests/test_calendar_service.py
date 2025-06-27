from pytest_mock import MockerFixture
from src.calendar.service import GoogleCalendarService

# --- Тест для приватного метода парсинга ---
def test_parse_event_item(mocker: MockerFixture):
    """
    Проверяем, что логика парсинга работает правильно для разных типов событий.
    """
    # Arrange: Создаем экземпляр сервиса с фейковыми credentials
    mock_creds = mocker.MagicMock()
    service = GoogleCalendarService(creds=mock_creds)

    # Arrange: Готовим "сырые" данные, как будто они пришли от Google API
    timed_event_item = {
        'id': 'timed123',
        'summary': 'Timed Event',
        'start': {'dateTime': '2023-01-01T10:00:00Z', 'timeZone': 'UTC'},
        'end': {'dateTime': '2023-01-01T11:00:00Z', 'timeZone': 'UTC'}
    }
    all_day_event_item = {
        'id': 'allday123',
        'summary': 'All Day Event',
        'start': {'date': '2023-01-02'},
        'end': {'date': '2023-01-03'}
    }

    # Act: Вызываем тестируемый метод
    parsed_timed_event = service._parse_event_item(timed_event_item, master_events_cache={})
    parsed_all_day_event = service._parse_event_item(all_day_event_item, master_events_cache={})

    # Assert: Проверяем результаты
    assert parsed_timed_event is not None
    assert parsed_timed_event.summary == 'Timed Event'
    assert parsed_timed_event.isAllDay is False
    assert parsed_timed_event.startTime == '2023-01-01T10:00:00Z'

    assert parsed_all_day_event is not None
    assert parsed_all_day_event.summary == 'All Day Event'
    assert parsed_all_day_event.isAllDay is True
    assert parsed_all_day_event.startTime == '2023-01-02'