
from google.adk.tools.google_api_tool import CalendarToolset
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


async def configure_calendar_tools(
    tool_names: List[str],
    access_token: str,
    client_id: str,
    client_secret: str,
    scopes: List[str]
) -> Dict[str, GoogleApiTool]: # Возвращаемый тип остается прежним
    """
    Асинхронно получает и конфигурирует указанные инструменты Google Calendar с access_token.
    """
    if not access_token:
        logger.error("Access token не предоставлен, инструменты не могут быть сконфигурированы.")
        return {}

    configured_tools: Dict[str, GoogleApiTool] = {}
    available_tools: Dict[str, GoogleApiTool] = {} # Инициализируем здесь

    try:
        calendar_tool_provider = CalendarToolset(
            client_id=client_id,
            client_secret=client_secret,
            tool_filter=tool_names
        )
        logger.info(f"CalendarToolset initialized with tool_filter: {tool_names}")

        # !!! ВЫЗЫВАЕМ get_tools() С AWAIT !!!
        # get_tools() теперь возвращает словарь инструментов
        tools_result = await calendar_tool_provider.get_tools()

        if not tools_result:
            logger.warning("await calendar_tool_provider.get_tools() вернул пустой результат или None.")
            return {}
        
        # Проверяем, что это действительно словарь
        if not isinstance(tools_result, dict):
            logger.error(f"await calendar_tool_provider.get_tools() вернул не словарь, а {type(tools_result)}. Значение: {tools_result}")
            return {}

        available_tools = tools_result # Присваиваем результат
        logger.info(f"Tools returned by get_tools(): {list(available_tools.keys())}")

    except Exception as e:
        logger.error(f"Failed to initialize CalendarToolset or get tools: {e}")
        import traceback
        logger.error(traceback.format_exc()) # Логируем полный трейсбек для диагностики
        return {}

    # Создаем AuthCredential (один раз)
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

    # Теперь итерируемся по tool_names, которые ты изначально хотел,
    # и берем соответствующие инструменты из available_tools
    for tool_name in tool_names:
        if tool_name not in available_tools:
            logger.warning(f"Инструмент '{tool_name}' не найден в словаре, возвращенном get_tools(). Пропускаем. Доступные ключи: {list(available_tools.keys())}")
            continue

        tool_instance = available_tools[tool_name]

        if hasattr(tool_instance, 'rest_api_tool') and tool_instance.rest_api_tool:
            tool_instance.rest_api_tool.auth_credential = user_auth_credential.model_copy(deep=True)
            configured_tools[tool_name] = tool_instance
            logger.info(f"Tool '{tool_name}' configured with user access token.")
        else:
            logger.warning(f"Tool '{tool_name}' (тип: {type(tool_instance)}) не имеет ожидаемого rest_api_tool атрибута или rest_api_tool is None.")
            
    return configured_tools