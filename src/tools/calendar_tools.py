import os
import logging
import asyncio
from src.auth.google_token import get_access_token_from_refresh
import src.shared.config as cfg
from src.tools.tools_auth import configure_calendar_tools
from google.adk.tools.google_api_tool import GoogleApiTool

logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO) # Если уже настроено глобально, можно убрать

# УДАЛЯЕМ ЭТОТ ЛОГ, ОН ОТНОСИЛСЯ К СТАРОМУ calendar_tool_set
# logger.info(f"calendar_tool_set configured with app's client_id/secret.")

# Глобальный кэш для сконфигурированных инструментов
_tools_cache: dict[str, GoogleApiTool] = {}
_tools_cache_lock = asyncio.Lock()

async def _ensure_tools_configured_if_needed():
    """
    Вспомогательная асинхронная функция.
    Конфигурирует все необходимые инструменты, если кэш пуст.
    Вызывается под блокировкой _tools_cache_lock.
    """
    global _tools_cache # работаем с глобальным кэшем
    
    # Эта проверка дублируется в get_calendar_tool, но здесь она нужна,
    # чтобы не делать лишнюю работу, если другая корутина уже заполнила кэш,
    # пока текущая ждала блокировку.
    if _tools_cache:
        return

    logger.info("Кэш инструментов пуст или запрошенный инструмент отсутствует, выполняю конфигурацию...")
    access_token = get_access_token_from_refresh(
        refresh_token=cfg.HARDCODED_REFRESH_TOKEN,
        client_id=cfg.GOOGLE_CLIENT_ID,
        client_secret=cfg.GOOGLE_CLIENT_SECRET,
        token_uri=cfg.TOKEN_URI,
        scopes=cfg.SCOPES
    )
    if not access_token:
        logger.error("Не удалось получить access_token для конфигурации инструментов.")
        # В реальном приложении здесь лучше выбросить исключение,
        # чтобы вызывающий код мог его обработать.
        # raise Exception("Failed to get access token for tools configuration")
        return # Если не выбрасываем исключение, кэш останется пустым

    # Список ВСЕХ инструментов календаря, которые могут понадобиться приложению
    all_possible_calendar_tool_names = [
        "calendar_events_list",
        "calendar_events_insert",
        # Добавь сюда другие инструменты, если они тебе нужны глобально
        # "calendar_events_get",
        # "calendar_events_update",
    ]
    
    try:
        configured_tools_dict = await configure_calendar_tools( # <--- ВЫЗОВ С AWAIT
            tool_names=all_possible_calendar_tool_names,
            access_token=access_token,
            client_id=cfg.GOOGLE_CLIENT_ID,
            client_secret=cfg.GOOGLE_CLIENT_SECRET,
            scopes=cfg.SCOPES
        )
        if configured_tools_dict: # Проверяем, что словарь не пустой
            _tools_cache.update(configured_tools_dict)
            logger.info(f"Инструменты сконфигурированы и закэшированы: {list(_tools_cache.keys())}")
        else:
            logger.warning("configure_calendar_tools вернул пустой результат, кэш не обновлен.")
    except Exception as e:
        logger.error(f"Ошибка при конфигурации инструментов в _ensure_tools_configured_if_needed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Можно очистить кэш или пометить его как невалидный, если была ошибка
        _tools_cache.clear()


async def get_calendar_tool(tool_name: str) -> GoogleApiTool | None:
    """
    Асинхронно возвращает сконфигурированный инструмент календаря по имени.
    При первом вызове (или если кэш пуст) конфигурирует все необходимые инструменты.
    """
    # Сначала проверяем без блокировки для быстрого пути, если инструмент уже в кэше
    # Это оптимизация, чтобы не все запросы ждали lock.
    # Но для корректности заполнения кэша lock все равно нужен.
    if tool_name in _tools_cache:
        return _tools_cache[tool_name]

    async with _tools_cache_lock:
        # Повторная проверка внутри lock, на случай если другая корутина заполнила кэш,
        # пока эта ждала своей очереди на lock.
        if tool_name not in _tools_cache:
            # Если нужного инструмента нет, или кэш вообще пуст, вызываем конфигурацию.
            await _ensure_tools_configured_if_needed() 
        
        tool = _tools_cache.get(tool_name)
        if not tool:
            logger.warning(f"Инструмент '{tool_name}' не найден в кэше даже после попытки конфигурации. "
                           f"Проверьте, есть ли он в 'all_possible_calendar_tool_names' "
                           f"и нет ли ошибок при его парсинге в 'configure_calendar_tools'. "
                           f"Текущие ключи в кэше: {list(_tools_cache.keys())}")
        return tool
