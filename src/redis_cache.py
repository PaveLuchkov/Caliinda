# redis_cache.py
import redis
import json
import os
from typing import List, Dict, Optional
from dotenv import load_dotenv
import logging 
import src.config as config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

try:
    redis_client = redis.Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        password=config.REDIS_PASSWORD,
        db=config.REDIS_DB,
        decode_responses=False # Будем хранить байты (JSON строки)
    )
    redis_client.ping() # Проверяем соединение при старте
    logger.info(f"Successfully connected to Redis at {config.REDIS_HOST}:{config.REDIS_PORT} (DB: {config.REDIS_DB}) for history.")
except redis.exceptions.ConnectionError as e:
    logger.error(f"Failed to connect to Redis for history: {e}", exc_info=True)
    redis_client = None # Устанавливаем в None, чтобы можно было проверить

def _get_history_key(user_google_id: str) -> str:
    """Генерирует ключ для хранения истории пользователя."""
    return f"history:{user_google_id}"

def get_message_history(user_google_id: str) -> List[Dict[str, str]]:
    """Получает историю сообщений пользователя из Redis."""
    if not redis_client:
        logger.warning("Redis client not available. Returning empty history.")
        return []
    key = _get_history_key(user_google_id)
    try:
        # Получаем последние MAX_HISTORY_LENGTH элементов
        history_bytes_list = redis_client.lrange(key, -config.MAX_HISTORY_LENGTH, -1)
        history = [json.loads(msg_bytes.decode('utf-8')) for msg_bytes in history_bytes_list]
        logger.debug(f"Retrieved history for {user_google_id}: {len(history)} messages.")
        return history
    except Exception as e:
        logger.error(f"Error retrieving history for {user_google_id} from Redis: {e}", exc_info=True)
        return []

def add_message_to_history(user_google_id: str, message: Dict[str, str]):
    """Добавляет сообщение в историю пользователя в Redis и обрезает её."""
    if not redis_client:
        logger.warning("Redis client not available. Skipping history update.")
        return
    key = _get_history_key(user_google_id)
    try:
        message_json_bytes = json.dumps(message, ensure_ascii=False).encode('utf-8')
        # Добавляем в конец списка
        redis_client.rpush(key, message_json_bytes)
        # Обрезаем список, оставляя только последние MAX_HISTORY_LENGTH элементов
        redis_client.ltrim(key, -config.MAX_HISTORY_LENGTH, -1)
        # Устанавливаем/обновляем время жизни ключа
        redis_client.expire(key, config.HISTORY_TTL_SECONDS)
        logger.debug(f"Added message to history for {user_google_id}. New length: {redis_client.llen(key)}")
    except Exception as e:
        logger.error(f"Error adding message to history for {user_google_id} in Redis: {e}", exc_info=True)

def clear_message_history(user_google_id: str):
    """Очищает историю сообщений пользователя."""
    if not redis_client:
        logger.warning("Redis client not available. Skipping history clear.")
        return
    key = _get_history_key(user_google_id)
    try:
        deleted_count = redis_client.delete(key)
        logger.info(f"Cleared history for {user_google_id}. Deleted keys: {deleted_count}")
    except Exception as e:
        logger.error(f"Error clearing history for {user_google_id} in Redis: {e}", exc_info=True)