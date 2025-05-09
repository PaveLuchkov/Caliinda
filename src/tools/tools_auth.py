
from google.adk.tools.google_api_tool import calendar_tool_set
from google.adk.auth import AuthCredentialTypes, OAuth2Auth # Важные классы
from google.adk.auth import (
    AuthCredential,
    AuthCredentialTypes,
    OAuth2Auth,
)
from google.adk.tools.google_api_tool import GoogleApiTool # Для тайпхинтинга

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def configure_calendar_tools(
    tool_names: List[str], 
    access_token: str,
    client_id: str, # Добавлен для AuthCredential
    client_secret: str, # Добавлен для AuthCredential
    scopes: List[str] # Добавлен для AuthCredential
) -> Dict[str, GoogleApiTool]:
    """
    Получает и конфигурирует указанные инструменты Google Calendar с access_token.

    Args:
        tool_names: Список имен инструментов (например, ["calendar_events_list", "calendar_events_insert"]).
        access_token: Пользовательский access_token.
        client_id: OAuth Client ID.
        client_secret: OAuth Client Secret.
        scopes: Список скоупов, связанных с access_token.

    Returns:
        Словарь, где ключ - имя инструмента, значение - сконфигурированный экземпляр GoogleApiTool.
        Возвращает пустой словарь, если access_token не предоставлен.
    """
    if not access_token:
        logger.error("Access token не предоставлен, инструменты не могут быть сконфигурированы.")
        return {}

    configured_tools: Dict[str, GoogleApiTool] = {}

    # Создаем AuthCredential с access_token (один раз)
    user_auth_credential = AuthCredential(
        auth_type=AuthCredentialTypes.OPEN_ID_CONNECT,
        oauth2=OAuth2Auth(
            client_id=client_id, 
            client_secret=client_secret, 
            access_token=access_token,
            scopes=scopes,
        )
    )
    logger.info(f"User AuthCredential for tool configuration created.")

    for tool_name in tool_names:
        tool_instance = calendar_tool_set.get_tool(tool_name)
        if not tool_instance:
            logger.warning(f"Не удалось получить инструмент с именем: {tool_name}")
            continue

        if hasattr(tool_instance, 'rest_api_tool') and tool_instance.rest_api_tool:
            # Передаем копию, чтобы каждый инструмент имел свой экземпляр credential,
            # хотя они и будут идентичны по содержанию.
            tool_instance.rest_api_tool.auth_credential = user_auth_credential.model_copy(deep=True)
            configured_tools[tool_name] = tool_instance
            logger.info(f"Tool '{tool_name}' configured with user access token.")
        else:
            logger.warning(f"Tool {tool_name} не имеет ожидаемого rest_api_tool атрибута.")
            
    return configured_tools