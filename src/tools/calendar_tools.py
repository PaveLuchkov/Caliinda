import os
import logging

from google.adk.tools.google_api_tool import calendar_tool_set
from google.adk.auth import AuthCredentialTypes, OAuth2Auth # Важные классы
from google.adk.auth import (
    AuthConfig,
    AuthCredential,
    AuthCredentialTypes,
    OAuth2Auth,
)

from src.auth.google_token import get_access_token_from_refresh
import src.shared.config as cfg


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Use the specific configure method for this toolset type
calendar_tool_set.configure_auth(
    client_id=cfg.GOOGLE_CLIENT_ID, client_secret=cfg.GOOGLE_CLIENT_SECRET
)
logger.info(f"calendar_tool_set configured with app's client_id/secret.")

tools_to_configure = [
    calendar_tool_set.get_tool("calendar_events_list"),
    calendar_tool_set.get_tool("calendar_events_insert"),
    # Добавь сюда другие инструменты из calendar_tool_set, если они нужны
]

for tool in tools_to_configure:
    if not tool:
        logger.error(f"Не удалось получить один из инструментов. Проверь имена.")
        # Реши, как обрабатывать: выходить или пропускать
        exit("Ошибка получения инструмента.")
logger.info(f"Получены инструменты: {[t.name for t in tools_to_configure]}")


access_token = get_access_token_from_refresh(
    refresh_token=cfg.HARDCODED_REFRESH_TOKEN, # Получаем из БД
    client_id=cfg.GOOGLE_CLIENT_ID,
    client_secret=cfg.GOOGLE_CLIENT_SECRET,
    token_uri=cfg.TOKEN_URI,
    scopes=cfg.SCOPES # Скоупы, соответствующие refresh_token'у
)
if access_token:
    user_auth_credential_with_access_token = AuthCredential(
        auth_type=AuthCredentialTypes.OPEN_ID_CONNECT, # Соответствует схеме инструмента
        oauth2=OAuth2Auth(
            client_id=cfg.GOOGLE_CLIENT_ID,
            client_secret=cfg.GOOGLE_CLIENT_SECRET,
            access_token=access_token,
            scopes=cfg.SCOPES,
        )
    )
    for tool_instance in tools_to_configure:
        if hasattr(tool_instance, 'rest_api_tool') and tool_instance.rest_api_tool:
            tool_instance.rest_api_tool.auth_credential = user_auth_credential_with_access_token.model_copy(deep=True) # Передаем копию
            logger.info(f"Set user_auth_credential_with_access_token on tool: {tool_instance.name}")
        else:
            logger.warning(f"Tool {tool_instance.name} не имеет ожидаемого rest_api_tool атрибута.")

    # 6. Собираем список инструментов для агента
    agent_tools = tools_to_configure
else:
    logger.error("Failed to get access token. Agent cannot proceed with authenticated tools.")
    agent_tools = [] # Или как-то иначе обработать ситуацию, когда нет токена
