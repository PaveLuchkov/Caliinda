from pydantic import BaseModel
from typing import List, Dict, Any, Union, Optional
from enum import Enum
from pydantic import Field
from datetime import datetime

class TokenExchangeRequest(BaseModel):
    id_token: str
    auth_code: str
# --- Helper Functions ---

class LookupStatus(str, Enum):
    """Определяет все возможные статусы ответа от Lookup_Agent."""
    CONFLICT_FOUND = "conflict_found"
    SLOT_IS_CLEAR = "slot_is_clear"
    EVENTS_FOUND = "events_found"
    NO_EVENTS_FOUND = "no_events_found"


# 2. Модель для одного события в календаре
class EventData(BaseModel):
    """Представляет одно событие, найденное в календаре."""
    title: str
    start: datetime
    end: datetime
    eventId: str
    recurrence: Optional[str] = None # Поле необязательное, будет None, если отсутствует


# 3. Главная модель для всего вывода от Lookup_Agent
class LookupOutput(BaseModel):
    """
    Основная схема ответа от Calendar_Lookup_Agent.
    Гарантирует, что ответ всегда будет иметь статус и список данных (даже если он пустой).
    """
    status: LookupStatus
    data: List[EventData] = Field(default_factory=list)