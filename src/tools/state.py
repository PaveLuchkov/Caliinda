from datetime import datetime
from google.adk.agents.callback_context import CallbackContext
import logging
import json

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def initialize_session_state(callback_context: CallbackContext):
    """Инициализирует состояние сессии, если это необходимо."""
    state = callback_context.state

    # Проверяем, инициализировали ли мы уже эту сессию
    if "session_initialized" not in state:
        print("--- Callback: First run for this session. Initializing state. ---")
        
        # Добавляем начальные данные
        state["session_initialized"] = True
        state["user:timezone"] = "Asia/Yekaterinburg"
        state["user:prefered_calendar"] = "primary"
        state["user:weekday"] = datetime.now().strftime('%A')
        state["user:current_time"] = str(datetime.now().replace(microsecond=0))
        state["user:language"] = "Russian"
        state["user:glance_time"] = str(datetime.now().date())
        state["ai:temper"] = "Такой братанчик кент и друг"
        
        print(f"--- Callback: State initialized: {state.to_dict()} ---")

def update_tasks(callback_context: CallbackContext):
    """Инициализирует состояние сессии, если это необходимо."""
    state = callback_context.state

    request = state.get("tasks", "")
    request_list = json.loads(request)

    state["tasks"] = request_list

def update_search_results(callback_context: CallbackContext):
    state = callback_context.state
    outer_key="previous_searches"
    n=0

    if outer_key not in state:
        state[outer_key] = {}
    nested = state[outer_key]

    if not isinstance(nested, dict):
        raise ValueError(f"Expected a dict for key '{outer_key}', got {type(nested)}")
    
    existing_keys = [int(k) for k in nested.keys() if str(k).isdigit()]
    next_index = max(existing_keys) + 1 if existing_keys else 0

    # Добавляем новое значение по следующему индексу
    nested[str(next_index)] = state.get("search_result", "")
    state[outer_key] = nested

