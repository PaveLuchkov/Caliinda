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