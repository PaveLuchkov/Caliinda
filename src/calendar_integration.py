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

# --- Приватная функция для создания ОДНОГО события ---
def _create_single_calendar_event(event_body: Dict[str, Any], service: Resource) -> Optional[Dict]:
    """
    Internal function to insert a single event into the primary calendar.

    Args:
        event_body: The dictionary representing the event structure for the API.
        service: The authorized Google Calendar API service instance.

    Returns:
        The created event object from the API, or None if insertion failed.
    """
    try:
        logger.info(f"Attempting to insert event: {event_body.get('summary', 'N/A')}")
        logger.debug(f"Event Body: {event_body}")

        created_event = service.events().insert(
            calendarId="primary",
            body=event_body
        ).execute()

        event_link = created_event.get('htmlLink')
        logger.info(f"Event created successfully: ID={created_event.get('id')}, Link={event_link}")
        return created_event

    except HttpError as http_err:
        logger.error(f"Google Calendar API HTTP Error: {http_err.resp.status} - {http_err.content}")
        # Можно проанализировать http_err.resp.status для разных реакций (напр., 400 - плохой запрос, 403 - права)
        return None # Возвращаем None при ошибке API
    except Exception as e:
        logger.error(f"Unexpected error during single event creation: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None # Возвращаем None при других ошибках

# --- Публичная функция для обработки ответа LLM и создания событий ---
def process_and_create_calendar_events(
        
    llm_response_data: Dict[str, Any],
    user_credentials: Credentials
) -> List[Dict]:
    """
    Processes the LLM response, validates event data, and creates one or more
    Google Calendar events using the provided user credentials.

    Args:
        llm_response_data: The dictionary returned by the LLM containing the 'event' list.
                           Assumes 'clarification_needed' is false.
        user_credentials: An instance of google.oauth2.credentials.Credentials for the user.

    Returns:
        A list of created event objects from the Google Calendar API.
        Returns an empty list if no events were created or if input was invalid.
    """
    created_events_list: List[Dict] = []
    creds = user_credentials

    # --- 1. Обновление Учетных Данных ---
    try:
        if creds.expired and creds.refresh_token:
            logger.info("Credentials expired, attempting refresh.")
            creds.refresh(Request())
            logger.info("Credentials refreshed successfully.")
            # TODO: Рассмотреть сохранение обновленных creds (если возможно)
        elif not creds.valid:
             # Пробуем использовать, даже если не 'valid', но есть токен/refresh_token
            if not creds.token and not creds.refresh_token:
                 logger.error("Credentials lack both token and refresh token.")
                 raise ValueError("User credentials lack a valid token or refresh token.")
            logger.warning("Credentials marked as invalid, but attempting API call.")

    except Exception as refresh_error:
        logger.error(f"Failed to refresh credentials: {refresh_error}")
        # Если не можем обновить, нет смысла продолжать
        # Бросаем исключение, чтобы в FastAPI вернуть 401 или 500
        raise Exception(f"Failed to refresh credentials, cannot create event: {refresh_error}")

    # --- 2. Построение API Сервиса ---
    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception as build_err:
        logger.error(f"Failed to build Google Calendar service: {build_err}")
        raise Exception(f"Failed to build Google Calendar service: {build_err}")

    # --- 3. Извлечение и Обработка Списка Событий ---
    event_list: List[Dict] = llm_response_data.get("event", [])
    if not event_list:
        logger.warning("LLM response contained no events in the 'event' list.")
        return created_events_list # Возвращаем пустой список

    logger.info(f"Processing {len(event_list)} potential event(s) from LLM response.")

    for index, event_detail in enumerate(event_list):
        logger.info(f"Processing event detail #{index+1}")
        logger.debug(f"Event detail data: {event_detail}")

        # --- 4. Валидация данных для одного события ---
        summary = event_detail.get("summary")
        start_info = event_detail.get("start")
        end_info = event_detail.get("end")
        start_dt = start_info.get("dateTime") if start_info else None
        end_dt = end_info.get("dateTime") if end_info else None
        # Часовой пояс берем из start, если есть, иначе используем дефолтный (хотя LLM должна вставлять)
        timezone = start_info.get("timeZone") if start_info else "Asia/Yekaterinburg" # TODO: Сделать динамическим

        if not all([summary, start_dt, end_dt]):
            logger.warning(f"Skipping event #{index+1} due to missing mandatory fields (summary, start.dateTime, or end.dateTime). Data: {event_detail}")
            continue # Пропускаем это событие, переходим к следующему

        # --- 5. Формирование Тела Запроса для API ---
        event_body: Dict[str, Any] = {
            "summary": summary,
            "start": {
                "dateTime": start_dt,
                "timeZone": timezone,
            },
            "end": {
                "dateTime": end_dt,
                "timeZone": timezone, # Должен совпадать со start
            },
            # Опционально: добавить другие поля, если LLM их вернет
            # "description": event_detail.get("description"),
        }

        # Добавляем повторение, если оно есть
        recurrence = event_detail.get("recurrence")
        # Проверяем, что recurrence это список и он не пустой, и содержит не null элементы
        if isinstance(recurrence, list) and recurrence and recurrence[0] is not None:
            event_body["recurrence"] = recurrence
            logger.info(f"Adding recurrence rule(s) for event #{index+1}")

        # --- 6. Вызов функции создания одного события ---
        created_event = _create_single_calendar_event(event_body, service)

        if created_event:
            created_events_list.append(created_event)
        else:
            logger.warning(f"Failed to create event #{index+1} based on detail: {event_detail}")
            # Не прерываем цикл, пытаемся создать остальные события

    logger.info(f"Finished processing. Created {len(created_events_list)} event(s).")
    return created_events_list


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