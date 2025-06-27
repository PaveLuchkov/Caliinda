# src/calendar/schemas.py
import logging

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CalendarEventResponse(BaseModel):
    id: str
    summary: str
    startTime: str
    endTime: str
    isAllDay: bool
    description: Optional[str] = None
    location: Optional[str] = None
    recurringEventId: Optional[str] = None
    originalStartTime: Optional[str] = None
    recurrenceRule: Optional[str] = None

    class Config:
        from_attributes = True

class CreateEventRequest(BaseModel):
    summary: str = Field(..., min_length=1, description="Event title")
    startTime: str = Field(..., description="Start time in ISO 8601 format (date or datetime)")
    endTime: str = Field(..., description="End time in ISO 8601 format (date or datetime)")
    isAllDay: bool = Field(..., description="Flag indicating if the event is all-day")
    # --- ДОБАВЛЕНО поле timeZoneId ---
    timeZoneId: Optional[str] = Field(
        None,
        description="Time zone ID (e.g., 'Asia/Yekaterinburg') required for non-all-day events"
    )
    description: Optional[str] = Field(None, description="Optional event description")
    location: Optional[str] = Field(None, description="Optional event location")
    recurrence: Optional[List[str]] = Field(
        None,
        description="Recurrence rules in RFC 5545 format (e.g., ['RRULE:FREQ=DAILY;COUNT=5'])"
    )

    # Валидатор можно оставить или улучшить для парсинга дат/времени
    @field_validator('endTime')
    @classmethod
    def end_time_after_start_time(cls, v, info):
        start_time = info.data.get('startTime')
        # TODO: Добавить парсинг и сравнение, если нужна строгая валидация
        # try:
        #     start_dt = datetime.datetime.fromisoformat(start_time)
        #     end_dt = datetime.datetime.fromisoformat(v)
        #     if end_dt <= start_dt:
        #         raise ValueError("End time must be after start time")
        # except (TypeError, ValueError):
        #      logger.warning(f"Could not perform strict datetime validation for startTime='{start_time}', endTime='{v}'")
        #      pass # Пока пропускаем, если не можем распарсить
        if start_time and v < start_time: # Простое строковое сравнение (ненадежно)
            logger.warning(f"Validation warning: endTime '{v}' might be before startTime '{start_time}'. Allowing for now.")
        return v
    
class UpdateEventRequest(BaseModel):
    summary: Optional[str] = Field(None, min_length=1, description="Event title")
    startTime: Optional[str] = Field(None, description="New start time in ISO 8601 format (date or datetime)")
    endTime: Optional[str] = Field(None, description="New end time in ISO 8601 format (date or datetime)")
    isAllDay: Optional[bool] = Field(None, description="Flag indicating if the event is all-day")
    timeZoneId: Optional[str] = Field(None, description="Time zone ID for non-all-day events") # Важно, если меняется время
    description: Optional[str] = Field(None, description="Optional event description")
    location: Optional[str] = Field(None, description="Optional event location")
    # Редактирование правил повторения - сложная тема, пока можно ее опустить или сделать очень базовой
    recurrence: Optional[List[str]] = Field(None, description="New recurrence rules")
    # attendees: Optional[List[str]] = Field(None, description="List of attendee emails") # Если поддерживаешь

class UpdateEventMode(str, Enum):
    SINGLE_INSTANCE = "single_instance"       # Редактировать только этот экземпляр
    ALL_IN_SERIES = "all_in_series"         # Редактировать всю серию (мастер-событие)
    THIS_AND_FOLLOWING = "this_and_following" # Редактировать этот и последующие (самый сложный)

# Модель ответа можно сделать похожей на CreateEventResponse или просто успешный статус
class UpdateEventResponse(BaseModel):
    status: str = "success"
    message: str = "Event updated successfully" 
    eventId: str # ID обновленного события (может измениться, если создается исключение)
    updatedFields: List[str] # Какие поля были фактически обновлены (опционально, для отладки)

# Модель ответа при успешном создании события
class CreateEventResponse(BaseModel):
    status: str = "success"
    message: str = "Event created successfully"
    eventId: Optional[str] = Field(None, description="ID of the created Google Calendar event")

class DeleteEventMode(str, Enum):
    DEFAULT = "default"
    INSTANCE_ONLY = "instance_only"
    # ALL_SERIES = "all_series" # Можно использовать DEFAULT для этого