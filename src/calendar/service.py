# src/calendar/service.py
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
import logging
from googleapiclient.discovery import build
from typing import Dict, List, Any, Optional, Tuple
import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


from .schemas import CreateEventRequest, UpdateEventRequest, UpdateEventMode, DeleteEventMode

class SimpleCalendarEvent:
    def __init__(self, id: str, summary: str, start_time: str, end_time: str,
                 is_all_day: bool,
                 description: Optional[str] = None,
                 location: Optional[str] = None,
                 recurring_event_id: Optional[str] = None,
                 original_start_time: Optional[str] = None,
                 recurrence: Optional[List[str]] = None):
        self.id = id
        self.summary = summary
        self.startTime = start_time
        self.endTime = end_time
        self.isAllDay = is_all_day
        self.description = description
        self.location = location
        self.recurringEventId = recurring_event_id
        self.originalStartTime = original_start_time
        self.recurrence_list = recurrence

    def to_dict(self) -> Dict[str, Any]: # Явно указываем тип возвращаемого значения
        main_rrule = None
        if self.recurrence_list:
            for rule_str in self.recurrence_list:
                if rule_str.startswith("RRULE:"):
                    main_rrule = rule_str # Берем первую найденную RRULE
                    break
        data = {
            "id": self.id,
            "summary": self.summary,
            "startTime": self.startTime,
            "endTime": self.endTime,
            "isAllDay": self.isAllDay,
            "description": self.description,
            "location": self.location,
            "recurringEventId": self.recurringEventId,
            "originalStartTime": self.originalStartTime,
            "recurrenceRule": main_rrule
        }
        return {k: v for k, v in data.items() if v is not None}

    def __repr__(self):
        return (f"SimpleCalendarEvent(id='{self.id}', summary='{self.summary}', "
                f"start='{self.startTime}', end='{self.endTime}', isAllDay={self.isAllDay}, "
                f"recurringEventId='{self.recurringEventId}', originalStartTime='{self.originalStartTime}')"
                f", recurrence={self.recurrence})")

    
class GoogleCalendarService:
    """
    Сервисный слой для инкапсуляции всей бизнес-логики, связанной
    с Google Calendar API.
    """

    def __init__(self, creds: Credentials, user_email: str):
        """
        Инициализирует сервис с учетными данными Google.

        Args:
            creds: Объект Credentials для аутентификации запросов.
        
        Raises:
            ValueError: если creds не предоставлены.
        """
        if not creds:
            raise ValueError("Credentials are required to initialize GoogleCalendarService")
        if not user_email:
            raise ValueError("User email is required for logging and context")
        self.creds = creds
        self.user_email = user_email
        # Создаем сервисный объект один раз при инициализации
        # cache_discovery=False рекомендуется для долгоживущих приложений, чтобы избежать
        # проблем с устаревшим кэшем API.
        try:
            self.service: Resource = build('calendar', 'v3', credentials=self.creds, cache_discovery=False)
        except Exception as e:
            logger.error(f"Failed to build Google Calendar service for user {self.user_email}: {e}")
            raise
    
    # --- CRUD МЕТОДЫ ---

    def get_events(self, start_date: datetime.date, end_date: datetime.date) -> List[Dict[str, Any]]:
        """
        Получает список событий календаря за указанный диапазон дат.

        Args:
            start_date: Начальная дата диапазона.
            end_date: Конечная дата диапазона.

        Returns:
            Список словарей, представляющих события календаря.
        
        Raises:
            HttpError: В случае ошибки от Google Calendar API.
        """
        if start_date > end_date:
            logger.warning(f"Start date {start_date} is after end date {end_date}. Returning empty list.")
            return []

        time_min = datetime.datetime.combine(start_date, datetime.time.min, tzinfo=datetime.timezone.utc).isoformat()
        time_max = datetime.datetime.combine(end_date + datetime.timedelta(days=1), datetime.time.min, tzinfo=datetime.timezone.utc).isoformat()

        logger.info(f"Querying Google Calendar API with timeMin={time_min}, timeMax={time_max}")
        
        all_items = []
        page_token = None
        while True:
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True, # Важно для раскрытия повторяющихся событий
                orderBy='startTime',
                pageToken=page_token
            ).execute()

            items = events_result.get('items', [])
            all_items.extend(items)
            
            page_token = events_result.get('nextPageToken')
            if not page_token:
                break
            logger.debug("Fetching next page of events...")

        if not all_items:
            logger.info(f"No events found for range {start_date.isoformat()} to {end_date.isoformat()}.")
            return []

        logger.info(f"Found {len(all_items)} total event instances.")
        
        # Кэш для мастер-событий, чтобы не запрашивать одно и то же событие несколько раз
        master_events_cache: Dict[str, Dict[Any, Any]] = {}
        parsed_events = []
        for item in all_items:
            try:
                parsed_event = self._parse_event_item(item, master_events_cache)
                if parsed_event:
                    parsed_events.append(parsed_event.to_dict())
            except Exception as e:
                logger.error(f"Failed to parse event item {item.get('id')}: {e}", exc_info=True)
        
        return parsed_events

    def create_event(self, event_data: CreateEventRequest) -> Dict[str, Any]:
        """
        Создает новое событие в календаре.

        Args:
            event_data: Pydantic модель с данными для создания события.

        Returns:
            Словарь, представляющий созданное событие от Google API.

        Raises:
            HttpError: В случае ошибки от Google Calendar API.
        """
        event_body = {
            'summary': event_data.summary,
            'description': event_data.description,
            'location': event_data.location,
            'recurrence': event_data.recurrence,
            'start': {},
            'end': {}
        }

        if event_data.isAllDay:
            event_body['start']['date'] = event_data.startTime
            event_body['end']['date'] = event_data.endTime
        else:
            event_body['start']['dateTime'] = event_data.startTime
            event_body['start']['timeZone'] = event_data.timeZoneId
            event_body['end']['dateTime'] = event_data.endTime
            event_body['end']['timeZone'] = event_data.timeZoneId
        
        # Очищаем тело запроса от полей с None, чтобы не отправлять их в API
        event_body_cleaned = {k: v for k, v in event_body.items() if v is not None}

        logger.info(f"Inserting new event: {event_body_cleaned}")
        created_event = self.service.events().insert(
            calendarId='primary',
            body=event_body_cleaned
        ).execute()
        
        logger.info(f"Event created successfully. Event ID: {created_event.get('id')}")
        return created_event

    def _prepare_time_patch(self, event_data: UpdateEventRequest, current_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Финальная, исправленная версия.
        Совмещает чистоту нового подхода с ключевой деталью из старого кода:
        явное обнуление полей при смене типа события.
        """
        time_fields_in_request = event_data.model_dump(exclude_unset=True)
        if not any(field in time_fields_in_request for field in {'startTime', 'endTime', 'isAllDay', 'timeZoneId'}):
            return {}

        # ... (код для определения is_becoming_all_day, start_value, end_value, new_timezone остается тот же) ...
        current_start = current_event.get('start', {})
        current_end = current_event.get('end', {})
        is_currently_all_day = 'date' in current_start
        is_becoming_all_day = event_data.isAllDay if event_data.isAllDay is not None else is_currently_all_day
        
        start_value = event_data.startTime or current_start.get('dateTime') or current_start.get('date')
        end_value = event_data.endTime or current_end.get('dateTime') or current_end.get('date')
        new_timezone = event_data.timeZoneId or current_start.get('timeZone')

        if not start_value:
            return {}

        time_patch = {}

        if is_becoming_all_day:
            # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ ---
            # Формируем start/end объекты, явно обнуляя ненужные поля
            start_patch_obj = {'dateTime': None, 'timeZone': None}
            end_patch_obj = {'dateTime': None, 'timeZone': None}

            try:
                start_date_obj = datetime.date.fromisoformat(start_value[:10])
                start_patch_obj['date'] = start_date_obj.isoformat()

                end_date_str = end_value[:10] if end_value else None
                end_date_obj = date.fromisoformat(end_date_str) if end_date_str else start_date_obj + datetime.timedelta(days=1)

                if end_date_obj <= start_date_obj:
                    end_date_obj = start_date_obj + datetime.timedelta(days=1)
                
                end_patch_obj['date'] = end_date_obj.isoformat()

                time_patch['start'] = start_patch_obj
                time_patch['end'] = end_patch_obj
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid date format for start or end time: {e}")

        else: # Для событий с точным временем
            # --- СИММЕТРИЧНОЕ ИЗМЕНЕНИЕ ---
            # При переходе на timed-событие, нужно явно обнулить 'date'
            start_patch_obj = {'date': None}
            end_patch_obj = {'date': None}

            if not new_timezone:
                raise ValueError("Timezone is required for non-all-day events.")

            start_patch_obj['dateTime'] = start_value
            start_patch_obj['timeZone'] = new_timezone
            if end_value:
                end_patch_obj['dateTime'] = end_value
                end_patch_obj['timeZone'] = new_timezone
            
            time_patch['start'] = start_patch_obj
            if 'dateTime' in end_patch_obj: # Добавляем end только если есть что обновлять
                time_patch['end'] = end_patch_obj
                
        return time_patch

    def update_event(self, event_id: str, event_data: UpdateEventRequest, update_mode: UpdateEventMode) -> Tuple[Dict[str, Any], List[str]]:
        """
        Обновляет существующее событие.

        Returns:
            Кортеж из (словарь обновленного события, список обновленных полей).
        """
        try:
            current_event = self.service.events().get(calendarId='primary', eventId=event_id).execute()
        except HttpError as e:
            logger.error(f"Cannot fetch event {event_id} to update: {e}")
            raise

        # 1. Формируем тело для patch-запроса, начиная с простых полей
        # Мы не мутируем исходный словарь, а создаем новый.
        patch_body = event_data.model_dump(
            exclude_unset=True, 
            exclude_none=True,
            # Исключаем поля, которые требуют специальной обработки
            exclude={'startTime', 'endTime', 'isAllDay', 'timeZoneId'} 
        )

        # 2. Обрабатываем время и добавляем в тело запроса
        time_patch = self._prepare_time_patch(event_data, current_event)
        patch_body.update(time_patch)

        # 3. Логика для повторяющихся событий
        target_event_id = event_id
        if update_mode == UpdateEventMode.ALL_IN_SERIES:
            if recurring_id := current_event.get('recurringEventId'):
                logger.info(f"Update targets the entire series. Master ID: {recurring_id}")
                target_event_id = recurring_id
        elif update_mode == UpdateEventMode.THIS_AND_FOLLOWING:
            logger.error(f"Update mode {update_mode} is not yet supported.")
            raise NotImplementedError("Update mode 'this_and_following' is not yet supported.")

        # 4. Проверяем, есть ли что обновлять, ПОСЛЕ всех манипуляций
        if not patch_body:
            logger.warning(f"Update request for event {event_id} had no fields to update.")
            # Возвращаем текущее событие и пустой список полей
            return current_event, []

        logger.info(f"Patching event {target_event_id} with body: {patch_body}")
        
        updated_event = self.service.events().patch(
            calendarId='primary',
            eventId=target_event_id,
            body=patch_body
        ).execute()

        logger.info(f"Event {updated_event.get('id')} updated successfully.")
        
        # Теперь мы возвращаем и событие, и список ключей, которые мы обновили
        return updated_event, list(patch_body.keys())


    def delete_event(self, event_id: str, mode: DeleteEventMode) -> None:
        """
        Удаляет событие из календаря.

        Args:
            event_id: ID события для удаления.
            mode: Режим удаления (один экземпляр или вся серия).

        Raises:
            HttpError: В случае ошибки от Google Calendar API.
        """
        logger.info(f"Request to delete event {event_id} with mode: {mode}")

        if mode == DeleteEventMode.INSTANCE_ONLY:
            # Отмена одного экземпляра - это PATCH-запрос, меняющий статус
            logger.info(f"Cancelling single instance of event {event_id}")
            self.service.events().patch(
                calendarId='primary',
                eventId=event_id,
                body={'status': 'cancelled'}
            ).execute()
            logger.info(f"Instance {event_id} cancelled.")
        else: # DEFAULT режим
            # Удаление одиночного события или всей серии
            logger.info(f"Deleting event/series {event_id}")
            self.service.events().delete(
                calendarId='primary',
                eventId=event_id
            ).execute()
            logger.info(f"Event/series {event_id} deleted.")

    def _parse_event_item(self, event_item: dict, master_events_cache: dict) -> Optional[SimpleCalendarEvent]:
        """
        Приватный метод для парсинга одного элемента из ответа Google API
        в наш внутренний объект SimpleCalendarEvent.
        """
        start_info = event_item.get('start', {})
        end_info = event_item.get('end', {})
        
        start_time = start_info.get('dateTime') or start_info.get('date')
        if not start_time:
            logger.warning(f"Skipping event without start time: {event_item.get('id')}")
            return None

        is_all_day = 'date' in start_info
        end_time = end_info.get('dateTime') or end_info.get('date')
        if not end_time:
            if is_all_day:
                # Для all-day событий без end.date, конец - это начало следующего дня
                end_time = (datetime.date.fromisoformat(start_time) + datetime.timedelta(days=1)).isoformat()
            else:
                end_time = start_time # Для событий со временем, если нет конца, считаем его мгновенным

        recurring_event_id = event_item.get('recurringEventId')
        master_recurrence = event_item.get('recurrence')

        # Если это экземпляр серии и у него нет своих правил, ищем правила в мастер-событии
        if recurring_event_id and not master_recurrence:
            if recurring_event_id in master_events_cache:
                master_recurrence = master_events_cache[recurring_event_id].get('recurrence')
            else:
                try:
                    master_event = self.service.events().get(calendarId='primary', eventId=recurring_event_id).execute()
                    master_events_cache[recurring_event_id] = master_event
                    master_recurrence = master_event.get('recurrence')
                except HttpError as e:
                    logger.error(f"Could not fetch master event {recurring_event_id} for instance {event_item.get('id')}: {e}")
        
        original_start = event_item.get('originalStartTime', {})
        original_start_time_str = original_start.get('dateTime') or original_start.get('date')

        return SimpleCalendarEvent(
            id=event_item.get('id'),
            summary=event_item.get('summary', 'Без названия'),
            start_time=start_time,
            end_time=end_time,
            is_all_day=is_all_day,
            description=event_item.get('description'),
            location=event_item.get('location'),
            recurring_event_id=recurring_event_id,
            original_start_time=original_start_time_str,
            recurrence=master_recurrence
        )