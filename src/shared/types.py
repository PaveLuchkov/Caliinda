from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Union, Literal
from enum import Enum
from pydantic import Field

class TokenExchangeRequest(BaseModel):
    id_token: str
    auth_code: str
# --- Helper Functions ---

class FundumentalTools(BaseModel):
    """Перечисление всех возможных инструментов для исполнителя."""
    LIST_EVENTS = "calendar.list_events"
    CREATE_EVENT = "calendar.create_event"
    DELETE_EVENT = "calendar.delete_event"
    UPDATE_EVENT = "calendar.update_event"
#// TODO нужно добавить другие вызовы для сценария планирования
    CHAT = "chat.chat"




class ConditionalStep(BaseModel):
    """Условный шаг, который будет выполнен исполнителем."""
    condition: str = Field(..., description="Условие для проверки, может использовать результаты предыдущих шагов. Пример: '{result_of_step1.status == \"busy\"'")
    then_branch: List['PlanStep'] = Field(
        ...,
        description="Список шагов, которые будут выполнены, если условие истинно.")
    else_branch: List['PlanStep'] = Field(default_factory=list, description='План, который нужно выполнить если условие ложно')

PlanStep = Union[ActionStep, ConditionalStep]
# TODO Проверить в агенте рабоатет ли такая pydantic конструкция




# --- Компоненты для описания Входных данных ---

class Intent(str, Enum):
    """Намерения, которые распознал Аналитик."""
    CREATE_EVENT = "create_event"
    CANCEL_EVENT = "cancel_event"
    MODIFY_EVENT = "modify_event"
    FIND_EVENT = "find_event"
    PROVIDE_INFO = "provide_info" # Когда пользователь отвечает на уточняющий вопрос
    UNKNOWN = "unknown"

class InterpretedUserRequest(BaseModel):
    """Структурированный результат работы Аналитика-Переводчика."""
    original_text: str
    intent: Intent
    entities: Dict[str, Any] = Field(default_factory=dict, description="Распознанные сущности: {'title': 'Встреча', 'date': 'tomorrow', ...}")
    missing_info: List[str] = Field(default_factory=list, description="Какой информации не хватает для выполнения намерения")
# --- Финальная ЕДИНСТВЕННАЯ модель входа для Стратега ---

class StrategistInput(BaseModel):
    """
    Полное 'состояние мира', передаваемое Стратегу для планирования.
    Это единственная схема, которую получает агент.
    """
    # Что хочет пользователь ПРЯМО СЕЙЧАС
    user_request: InterpretedUserRequest = Field(..., description="Результат работы Аналитика по последнему запросу пользователя")