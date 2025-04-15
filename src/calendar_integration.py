# calendar_integration.py
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource # Добавили Resource для type hint
from googleapiclient.errors import HttpError # Для обработки ошибок API
from google.auth.transport.requests import Request
import traceback
import logging
from typing import Dict, List, Any, Optional # Обновили типы
import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Определим модель ответа (хотя FastAPI будет использовать свою)
# Это полезно для ясности того, что мы хотим получить
class SimpleCalendarEvent:
    def __init__(self, id: str, summary: str, start_time: str, end_time: str, description: str = None, location: str = None):
        self.id = id
        self.summary = summary
        self.startTime = start_time # Используем camelCase как в Android модели
        self.endTime = end_time
        self.description = description
        self.location = location

    def to_dict(self):
        return {
            "id": self.id,
            "summary": self.summary,
            "startTime": self.startTime,
            "endTime": self.endTime,
            "description": self.description,
            "location": self.location,
        }


def get_events_for_date(creds: Credentials, target_date: datetime.date) -> list[SimpleCalendarEvent]:
    """
    Fetches events from the primary Google Calendar for a specific date.

    Args:
        creds: Google OAuth2 credentials object.
        target_date: The date for which to fetch events.

    Returns:
        A list of SimpleCalendarEvent objects.

    Raises:
        HttpError: If the Google API call fails.
        Exception: For other unexpected errors.
    """
    events_list = []
    try:
        service = build('calendar', 'v3', credentials=creds)
        logger.info(f"Fetching events for date: {target_date.isoformat()}")

        # Определяем начало и конец дня в UTC
        # Google Calendar API ожидает время в формате RFC3339
        # Мы запрашиваем события, которые НАЧИНАЮТСЯ в этот день (с 00:00 UTC до 23:59:59 UTC)
        # Либо события на весь день (all-day events)
        # Google API хорошо обрабатывает часовые пояса, если они указаны в startTime/endTime
        # Указываем UTC, чтобы получить согласованный диапазон
        time_min_dt = datetime.datetime.combine(target_date, datetime.time.min, tzinfo=datetime.timezone.utc)
        # Конец дня - это начало следующего дня
        time_max_dt = datetime.datetime.combine(target_date + datetime.timedelta(days=1), datetime.time.min, tzinfo=datetime.timezone.utc)

        time_min = time_min_dt.isoformat()
        time_max = time_max_dt.isoformat() # Не включается верхняя граница

        logger.debug(f"Querying Google Calendar API with timeMin={time_min}, timeMax={time_max}")

        events_result = service.events().list(
            calendarId='primary', # Основной календарь пользователя
            timeMin=time_min,
            timeMax=time_max,
            # maxResults=50, # Ограничиваем количество на всякий случай
            singleEvents=True, # Разворачивает повторяющиеся события в отдельные экземпляры
            orderBy='startTime' # Сортируем по времени начала
        ).execute()

        items = events_result.get('items', [])

        if not items:
            logger.info(f"No events found for {target_date.isoformat()}.")
            return []

        logger.info(f"Found {len(items)} events for {target_date.isoformat()}.")

        for event in items:
            # Время начала/конца может быть 'dateTime' (с временем) или 'date' (весь день)
            start_info = event.get('start', {})
            end_info = event.get('end', {})

            # Google возвращает либо 'dateTime' (ISO 8601 со временем и зоной), либо 'date' (YYYY-MM-DD)
            start_time_str = start_info.get('dateTime', start_info.get('date'))
            end_time_str = end_info.get('dateTime', end_info.get('date'))

            # Пропускаем события без времени начала (маловероятно, но возможно)
            if not start_time_str:
                logger.warning(f"Skipping event without start time: {event.get('summary')}")
                continue
            # Если нет времени окончания, используем время начала (для безопасности)
            if not end_time_str:
                end_time_str = start_time_str

            simple_event = SimpleCalendarEvent(
                id=event.get('id'),
                summary=event.get('summary', 'Без названия'), # Предоставляем значение по умолчанию
                start_time=start_time_str,
                end_time=end_time_str,
                description=event.get('description'),
                location=event.get('location')
            )
            events_list.append(simple_event)

        return events_list

    except HttpError as error:
        logger.error(f"An API error occurred: {error}")
        # Перебрасываем ошибку, чтобы FastAPI мог ее обработать
        raise error
    except Exception as e:
        logger.error(f"Unexpected error fetching events: {e}", exc_info=True)
        # Перебрасываем для обработки в FastAPI
        raise e