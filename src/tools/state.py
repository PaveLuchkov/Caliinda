from datetime import datetime
from google.adk.agents.callback_context import CallbackContext

def initialize_session_state(callback_context: CallbackContext):
    """Инициализирует состояние сессии, если это необходимо."""
    state = callback_context.state

    # Проверяем, инициализировали ли мы уже эту сессию
    if "session_initialized" not in state:
        print("--- Callback: First run for this session. Initializing state. ---")
        
        # Добавляем начальные данные
        state["session_initialized"] = True
        state["user_timezone"] = "Asia/Yekaterinburg"
        state["user_prefered_calendar"] = "primary"
        state["current_user_time"] = str(datetime.now().replace(microsecond=0))
        state["user_language"] = "Russian"
        state["current_date_user_look_at"] = str(datetime.now().date())
        state["temper_setting"] = "Такой братанчик кент и друг"
        
        print(f"--- Callback: State initialized: {state.to_dict()} ---")