from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Union
from pydantic import Field

class TokenExchangeRequest(BaseModel):
    id_token: str
    auth_code: str
# --- Helper Functions ---

class ToolCall(BaseModel):
    """Перечисление всех возможных инструментов для исполнителя."""
    CHECK_AVAILABILITY = "calendar.check_availability"
    FIND_EVENT = "calendar.find_event"
    CREATE_EVENT = "calendar.create_event"
    DELETE_EVENT = "calendar.delete_event"
    UPDATE_EVENT = "calendar.update_event"
    FIND_FREE_SLOTS = "calendar.find_free_slots"

    ASK_USER_FOR_MISSING_INFO = "user.ask_for_missing_info"
    PROPOSE_OPTIONS = "user.propose_options"
    CONFIRM_ACTION = "user.confirm_action"
    INFORM_USER = "user.inform_user"

class ActionStep(BaseModel):
    """Шаг действия, который будет выполнен исполнителем."""
    step_id: str = Field(..., description="Уникальный идентификатор шага действия, отсчет от 1")
    tool: ToolCall = Field(..., description="Инструмент, который будет вызван для выполнения шага")
    params: Dict[str, Any] = Field(
        ...,
        description="Параметры, которые будут переданы в инструмент. Ключи и значения зависят от конкретного инструмента.",
    )

class ConditionalStep(BaseModel):
    """Условный шаг, который будет выполнен исполнителем."""
    condition: str = Field(..., description="Условие для проверки, может использовать результаты предыдущих шагов. Пример: '{result_of_step1.status == \"busy\"'")
    then_branch: List['PlanStep'] = Field(
        ...,
        description="Список шагов, которые будут выполнены, если условие истинно.")
    else_branch: List['PlanStep'] = Field(default_factory=list, description='План, который нужно выполнить если условие ложно')

PlanStep = Union[ActionStep, ConditionalStep]

