import os
import logging
from google.adk.tools.google_api_tool import calendar_tool_set

from src.auth.google_token import get_access_token_from_refresh
import src.shared.config as cfg
from src.tools.tools_auth import configure_calendar_tools

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

calendar_tool_set.configure_auth(
    client_id=cfg.GOOGLE_CLIENT_ID, client_secret=cfg.GOOGLE_CLIENT_SECRET
)

logger.info(f"calendar_tool_set configured with app's client_id/secret.")

access_token = get_access_token_from_refresh(
    refresh_token=cfg.HARDCODED_REFRESH_TOKEN,
    client_id=cfg.GOOGLE_CLIENT_ID,
    client_secret=cfg.GOOGLE_CLIENT_SECRET,
    token_uri=cfg.TOKEN_URI,
    scopes=cfg.SCOPES
)
if not access_token:
    logger.error("Не удалось получить access_token. Дальнейшая работа с аутентифицированными инструментами невозможна.")
    # Здесь можно решить, как приложение должно себя вести:
    # - завершить работу
    # - работать без аутентифицированных инструментов
    # - попытаться инициировать новый OAuth flow (если это предусмотрено)
    # Для примера, просто создадим пустой словарь инструментов
    all_configured_calendar_tools = {}
else:
    #Определяем список всех инструментов календаря
    all_possible_calendar_tool_names = [
        "calendar_events_list",
        "calendar_events_insert",
        "calendar_events_update",
        "calendar_events_delete",
    ]
    all_configured_calendar_tools = configure_calendar_tools(
        tool_names=all_possible_calendar_tool_names,
        access_token=access_token,
        client_id=cfg.GOOGLE_CLIENT_ID,
        client_secret=cfg.GOOGLE_CLIENT_SECRET,
        scopes=cfg.SCOPES
    )


#  --- Tools ---
event_list = all_configured_calendar_tools["calendar_events_list"]
insert = all_configured_calendar_tools["calendar_events_insert"]
edit = all_configured_calendar_tools["calendar_events_update"]
delete = all_configured_calendar_tools["calendar_events_delete"]