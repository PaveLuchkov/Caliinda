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
    def __init__(self, id: str, summary: str, start_time: str, end_time: str,
                 is_all_day: bool,
                 description: Optional[str] = None,
                 location: Optional[str] = None,
                 # --- НОВЫЕ ПАРАМЕТРЫ В __init__ ---
                 recurring_event_id: Optional[str] = None,
                 original_start_time: Optional[str] = None):
        self.id = id
        self.summary = summary
        # Используем camelCase для атрибутов, если это твой стиль для словаря to_dict
        # Но если CalendarEventResponse ожидает startTime, endTime, isAllDay, то оставляем так.
        # Судя по твоему to_dict, ты используешь startTime, endTime, isAllDay.
        self.startTime = start_time
        self.endTime = end_time
        self.isAllDay = is_all_day
        self.description = description
        self.location = location
        # --- СОХРАНЯЕМ КАК АТРИБУТЫ ЭКЗЕМПЛЯРА ---
        self.recurringEventId = recurring_event_id
        self.originalStartTime = original_start_time

    def to_dict(self) -> Dict[str, Any]: # Явно указываем тип возвращаемого значения
        data = {
            "id": self.id,
            "summary": self.summary,
            "startTime": self.startTime, # Убедись, что это startTime, а не self.start_time
            "endTime": self.endTime,   # Аналогично
            "isAllDay": self.isAllDay,
            "description": self.description,
            "location": self.location,
            "recurringEventId": self.recurringEventId,
            "originalStartTime": self.originalStartTime
        }
        # Убираем ключи со значением None, если это требуется (FastAPI часто делает это сам для Optional полей)
        return {k: v for k, v in data.items() if v is not None}

    def __repr__(self):
        return (f"SimpleCalendarEvent(id='{self.id}', summary='{self.summary}', "
                f"start='{self.startTime}', end='{self.endTime}', isAllDay={self.isAllDay}, "
                f"recurringEventId='{self.recurringEventId}', originalStartTime='{self.originalStartTime}')")

def get_events_for_date(creds: Credentials, target_date: datetime.date) -> list[SimpleCalendarEvent]:
    """
    Fetches events from the primary Google Calendar for a specific date.
    Includes the 'isAllDay' flag.
    """
    events_list = []
    try:
        service = build('calendar', 'v3', credentials=creds, cache_discovery=False) # Учти cache_discovery
        logger.info(f"Fetching events for date: {target_date.isoformat()}")

        time_min_dt = datetime.datetime.combine(target_date, datetime.time.min, tzinfo=datetime.timezone.utc)
        time_max_dt = datetime.datetime.combine(target_date + datetime.timedelta(days=1), datetime.time.min, tzinfo=datetime.timezone.utc)
        time_min = time_min_dt.isoformat()
        time_max = time_max_dt.isoformat()

        logger.debug(f"Querying Google Calendar API with timeMin={time_min}, timeMax={time_max}")

        # Используем пагинацию, если событий может быть много
        all_items = []
        page_token = None
        while True:
             try:
                events_result = service.events().list(
                    calendarId='primary',
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime',
                    pageToken=page_token
                ).execute()

                items = events_result.get('items', [])
                all_items.extend(items)
                page_token = events_result.get('nextPageToken')
                if not page_token:
                    break
                logger.debug("Fetching next page...")
             except HttpError as page_error:
                 logger.error(f"Google Calendar API error while fetching page: {page_error}")
                 raise page_error


        if not all_items:
            logger.info(f"No events found for {target_date.isoformat()}.")
            return []

        logger.info(f"Found {len(all_items)} events for {target_date.isoformat()}.")

        for event_item in all_items:
            start_info = event_item.get('start', {})
            end_info = event_item.get('end', {})

            # --- ОПРЕДЕЛЕНИЕ is_all_day ---
            is_all_day_event = 'date' in start_info and 'dateTime' not in start_info
            logger.info(f"Event: {event_item.get('summary')}, ID: {event_item.get('id')}, start_info: {start_info}, is_all_day_event: {is_all_day_event}")
            # --------------------------------
            recurring_event_id_val = event_item.get('recurringEventId') # Используем другое имя переменной
            original_start_time_data = event_item.get('originalStartTime')
            original_start_time_str_val = None # Используем другое имя переменной
            if original_start_time_data:
                original_start_time_str_val = original_start_time_data.get('dateTime') or \
                                            original_start_time_data.get('date')
                
            start_time_str = start_info.get('dateTime', start_info.get('date'))
            end_time_str = end_info.get('dateTime', end_info.get('date'))

            if not start_time_str:
                logger.warning(f"Skipping event without start time: {event_item.get('summary')} (ID: {event_item.get('id')})")
                continue

            # Обработка отсутствующего времени конца
            if not end_time_str:
                if is_all_day_event:
                    try:
                         start_date_obj = datetime.date.fromisoformat(start_time_str)
                         end_date_obj = start_date_obj + datetime.timedelta(days=1)
                         end_time_str = end_date_obj.isoformat()
                         logger.warning(f"All-day event without end date: {event_item.get('summary')} (ID: {event_item.get('id')}). Calculated end date.")
                    except ValueError:
                         logger.error(f"Could not parse start date '{start_time_str}' for all-day event {event_item.get('id')} to calculate end date. Using start date.")
                         end_time_str = start_time_str
                else:
                    end_time_str = start_time_str
                    logger.warning(f"Timed event without end time: {event_item.get('summary')} (ID: {event_item.get('id')}). Using start time as end time.")

            # Создаем объект с флагом is_all_day
            simple_event = SimpleCalendarEvent(
                id=event_item.get('id'),
                summary=event_item.get('summary', 'Без названия'),
                start_time=start_time_str,
                end_time=end_time_str,
                is_all_day=is_all_day_event, # <--- ПЕРЕДАЕМ ФЛАГ
                description=event_item.get('description'),
                location=event_item.get('location'),
                recurring_event_id=recurring_event_id_val,    # Имя аргумента в __init__
                original_start_time=original_start_time_str_val # Имя аргумента в __init__
            )
            events_list.append(simple_event)

        return events_list

    except HttpError as error:
        logger.error(f"An API error occurred fetching events for {target_date}: {error}", exc_info=True)
        raise error
    except Exception as e:
        logger.error(f"Unexpected error fetching events for {target_date}: {e}", exc_info=True)
        raise e
    

def get_events_for_range(creds: Credentials, start_date: datetime.date, end_date: datetime.date) -> List[SimpleCalendarEvent]:
    """
    Fetches events from the primary Google Calendar for a specific date range.
    Includes the 'isAllDay' flag.
    """
    events_list = []
    if start_date > end_date:
        logger.warning(f"Start date {start_date} is after end date {end_date}. Returning empty list.")
        return []

    try:
        service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
        logger.info(f"Fetching events for date range: {start_date.isoformat()} to {end_date.isoformat()}")

        time_min_dt = datetime.datetime.combine(start_date, datetime.time.min, tzinfo=datetime.timezone.utc)
        time_max_dt = datetime.datetime.combine(end_date + datetime.timedelta(days=1), datetime.time.min, tzinfo=datetime.timezone.utc)
        time_min_iso = time_min_dt.isoformat()
        time_max_iso = time_max_dt.isoformat()

        logger.debug(f"Querying Google Calendar API with timeMin={time_min_iso}, timeMax={time_max_iso}")

        all_items = []
        page_token = None
        while True:
            try:
                events_result = service.events().list(
                    calendarId='primary',
                    timeMin=time_min_iso,
                    timeMax=time_max_iso,
                    singleEvents=True,
                    orderBy='startTime',
                    pageToken=page_token
                ).execute()

                items = events_result.get('items', [])
                all_items.extend(items)
                page_token = events_result.get('nextPageToken')
                if not page_token:
                    break
                logger.debug(f"Fetching next page of events...")

            except HttpError as page_error:
                logger.error(f"Google Calendar API error while fetching page: {page_error}")
                raise page_error

        if not all_items:
            logger.info(f"No events found for range {start_date.isoformat()} to {end_date.isoformat()}.")
            return []

        logger.info(f"Found {len(all_items)} events for range {start_date.isoformat()} to {end_date.isoformat()}.")

        # --- НАЧАЛО ЦИКЛА ОБРАБОТКИ (ИДЕНТИЧНО get_events_for_date) ---
        for event_item in all_items: # Переименовал event в event_item, чтобы не конфликтовать с модулем event
            start_info = event_item.get('start', {})
            end_info = event_item.get('end', {})
            is_all_day_event = 'date' in start_info and 'dateTime' not in start_info
            # --- ИЗВЛЕКАЕМ НОВЫЕ ПОЛЯ ---
            recurring_event_id = event_item.get('recurringEventId')
            original_start_time_data = event_item.get('originalStartTime')
            original_start_time_str = None
            if original_start_time_data:
                original_start_time_str = original_start_time_data.get('dateTime') or \
                                        original_start_time_data.get('date')
            # --------------------------------

            start_time_str = start_info.get('dateTime', start_info.get('date'))
            end_time_str = end_info.get('dateTime', end_info.get('date'))

            if not start_time_str:
                logger.warning(f"Skipping event without start time: {event_item.get('summary')} (ID: {event_item.get('id')})")
                continue

            if not end_time_str:
                if is_all_day_event:
                    try:
                         start_date_obj = datetime.date.fromisoformat(start_time_str)
                         end_date_obj = start_date_obj + datetime.timedelta(days=1)
                         end_time_str = end_date_obj.isoformat()
                         logger.warning(f"All-day event without end date: {event_item.get('summary')} (ID: {event_item.get('id')}). Calculated end date.")
                    except ValueError:
                         logger.error(f"Could not parse start date '{start_time_str}' for all-day event {event_item.get('id')} to calculate end date. Using start date.")
                         end_time_str = start_time_str
                else:
                    end_time_str = start_time_str
                    logger.warning(f"Timed event without end time: {event_item.get('summary')} (ID: {event_item.get('id')}). Using start time as end time.")

            # Создаем объект с флагом is_all_day
            simple_event = SimpleCalendarEvent(
                id=event_item.get('id'),
                summary=event_item.get('summary', 'Без названия'),
                start_time=start_time_str,
                end_time=end_time_str,
                is_all_day=is_all_day_event,
                description=event_item.get('description'),
                location=event_item.get('location'),
                # --- ПЕРЕДАЕМ НОВЫЕ ПОЛЯ ---
                recurring_event_id=recurring_event_id,       # Правильное имя аргумента
                original_start_time=original_start_time_str  # Правильное имя аргумента
                # -------------------------
            )
            events_list.append(simple_event)
        # --- КОНЕЦ ЦИКЛА ОБРАБОТКИ ---

        return events_list

    except HttpError as error:
        logger.error(f"An API error occurred fetching range {start_date} to {end_date}: {error}", exc_info=True)
        raise error
    except Exception as e:
        logger.error(f"Unexpected error fetching events for range {start_date} to {end_date}: {e}", exc_info=True)
        raise e