# llm_handler.py
import json
import traceback
from openai import OpenAI
import os
from dotenv import load_dotenv
from typing import Optional, Dict, List
import logging
import jinja2
from pathlib import Path 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    logger.warning(f".env file not found at {dotenv_path}")

# --- Jinja2 Setup ---
PROMPT_DIR = Path(__file__).parent / "prompts"
if not PROMPT_DIR.exists():
    PROMPT_DIR = Path(".") / "prompts"

if PROMPT_DIR.exists() and PROMPT_DIR.is_dir():
    logger.info(f"Jinja2 templates directory found: {PROMPT_DIR.resolve()}")
    template_loader = jinja2.FileSystemLoader(searchpath=str(PROMPT_DIR.resolve()))
    template_env = jinja2.Environment(loader=template_loader, trim_blocks=True, lstrip_blocks=True, autoescape=False)
else:
    logger.error(f"Jinja2 templates directory NOT found or not a directory at expected locations: {PROMPT_DIR} or ./prompts.")
    template_env = None

def render_prompt(template_name: str, context: Dict) -> Optional[str]:
    """Загружает шаблон Jinja2 и рендерит его с переданным контекстом."""
    if not template_env:
        logger.error("Jinja2 environment not initialized. Cannot load template.")
        return None
    try:
        template = template_env.get_template(template_name)
        return template.render(**context)
    except jinja2.TemplateNotFound:
        logger.error(f"Prompt template '{template_name}' not found in {PROMPT_DIR}")
        return None
    except Exception as e:
        logger.error(f"Error loading/rendering prompt template '{template_name}': {e}", exc_info=True)
        return None

class LLMHandler:
    def __init__(self):
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        if not self.api_key:
            logger.error("OPENROUTER_API_KEY not found in environment variables or .env file.")
            raise ValueError("API key for OpenRouter not configured.")

        # TODO: Сделать реферер и тайтл конфигурируемыми
        self.http_referer = os.getenv("LLM_HTTP_REFERER", "http://localhost/calendar-app")
        self.x_title = os.getenv("LLM_X_TITLE", "Voice Calendar Assistant")

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key
        )
        self.model = os.getenv("LLM_MODEL", "google/gemini-2.0-flash-001")

    def _call_llm(self, messages: List[Dict[str, str]], json_output: bool = True) -> Optional[Dict]:
        """Вспомогательный метод для вызова LLM с обработкой ошибок."""
        try:
            completion = self.client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": self.http_referer,
                    "X-Title": self.x_title,
                },
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"} if json_output else None
            )
            response_content = completion.choices[0].message.content
            logger.info(f"LLM Raw Response: {response_content}")
            if json_output:
                # Попытка исправить распространенные ошибки JSON перед парсингом
                cleaned_content = response_content.strip().strip('`').strip().rstrip(',')
                if cleaned_content.startswith('json'):
                     cleaned_content = cleaned_content[4:].strip()

                # Добавим try-except для парсинга JSON
                try:
                    return json.loads(cleaned_content)
                except json.JSONDecodeError as json_err:
                    logger.error(f"Failed to parse LLM JSON response: {json_err}")
                    logger.error(f"Problematic JSON string: {cleaned_content}")
                    return {"error": "LLM returned invalid JSON", "raw_response": cleaned_content}
            else:
                 return {"text_response": response_content}
        except Exception as e:
            logger.error(f"Error calling LLM: {str(e)}\n{traceback.format_exc()}")
            return {"error": f"LLM API call failed: {e}"}

    def clara(self, user_input: str, time: str, timezone: str, temper: str, history: List[Dict[str, str]], calendar_results: Optional[str] = None) -> Optional[Dict]:
        """
        Клара: Основная модель взаимодействия.
        :param user_input: Текст текущего запроса пользователя ИЛИ системный текст (например, после поиска по календарю).
        :param time: Текущее время ISO.
        :param timezone: Таймзона пользователя.
        :param history: История диалога.
        :param calendar_results: Результаты поиска по календарю (если были).
        :return: JSON с одним из ключей: message_to_user, calendar, prompt_to_llm или None/Dict с ошибкой.
        """
        logger.info(f"LLM Stage Clara: Processing input. Has calendar results: {'Yes' if calendar_results else 'No'}")

        # Собираем контекст для промпта
        context = {
            "UserDateTime": time,
            "user_timezone": timezone,
            "history": history,
            "user_input": user_input, # Передаем актуальный ввод (может быть и системным)
            "calendar_search_results": calendar_results, # Передаем результаты поиска, если они есть
            "temper": temper
            # TODO сделать это фишкой в приложении, характер Клары
        }

        # Генерируем промпт
        prompt_content = render_prompt("clara.txt", context)
        if not prompt_content:
            logger.error("Failed to render prompt for Clara.")
            # Не возвращаем None, а словарь с ошибкой для консистентности
            return {"error": "Failed to render prompt"}

        # Формируем сообщение для API (только промпт как user message)
        # История уже включена в сам prompt_content через render_prompt
        messages = [{"role": "user", "content": prompt_content}]

        # Вызываем LLM, ожидая JSON
        result = self._call_llm(messages, json_output=True)

        # Обработка результата вызова
        if not result:
            logger.error("No result from LLM call.")
            return {"error": "LLM call returned no result"} # Возвращаем ошибку

        if "error" in result:
            logger.error(f"LLM call resulted in an error: {result['error']}")
            return result # Передаем ошибку дальше

        # Валидация структуры ответа Clara
        valid_keys = ["message_to_user", "calendar", "prompt_to_llm"]
        present_keys = [key for key in valid_keys if key in result]

        if len(present_keys) != 1:
            logger.error(f"Invalid Clara response structure. Keys: {list(result.keys())}. Expected one of {valid_keys}.")
            return {"error": "Invalid response structure from LLM Clara", "raw_response": result}
        
        key = present_keys[0]
        value = result[key]

        # Валидация типов
        err = None
        if key == "message_to_user" and not isinstance(value, str): err = "message_to_user not string"
        elif key == "calendar" and not isinstance(value, str): err = "calendar not string"
        elif key == "prompt_to_llm" and not isinstance(value, dict):
            err = "prompt_to_llm value is not a JSON object (dict)"
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---
        if err:
            logger.error(f"Invalid Clara response value type/structure for key '{key}'. Error: {err}. Response: {result}")
            return {"error": f"Invalid response value for {key}", "raw_response": result}
        logger.info(f"LLM Clara response successful: Key='{key}'")
        return result
    
    def _call_formatter_llm(self, prompt_template: str, context: Dict) -> Optional[Dict]:
        """Вспомогательный метод для вызова LLM-форматтеров."""
        logger.info(f"Calling Formatter LLM using template: {prompt_template}")
        if not template_env: # Проверка инициализации Jinja2
             logger.error("Jinja2 environment not available for formatter.")
             return {"error": "Internal Server Error: Template engine offline."}

        prompt_content = render_prompt(prompt_template, context)
        if not prompt_content:
            return {"error": f"Failed to render prompt template {prompt_template}"}

        messages = [{"role": "user", "content": prompt_content}]
        # Используем тот же _call_llm, ожидая JSON
        # Убедись, что модель подходит для точного форматирования JSON
        result = self._call_llm(messages, json_output=True)

        if not result or "error" in result:
            error_msg = result.get("error", "Unknown formatter LLM error") if result else "Formatter LLM returned None"
            raw_resp = result.get("raw_response", "") if result else ""
            logger.error(f"Formatter LLM ({prompt_template}) Error: {error_msg}. Raw: {raw_resp}")
            # Не возвращаем raw_response наружу
            return {"error": f"Failed to format request: {error_msg}"}

        logger.info(f"Formatter LLM ({prompt_template}) response successful.")
        logger.debug(f"Formatted JSON: {result}")
        return result # Возвращаем готовый JSON для API

    def format_create_request(self, description_string: str, user_timezone: str, time: str) -> Optional[Dict]:
        """Вызывает LLM для форматирования тела запроса создания события."""
        context = {
            "description_string": description_string,
            "user_timezone": user_timezone,
            "UserDateTime": time
        }
        return self._call_formatter_llm("creed.txt", context)

    def format_update_request(self, description_string: str, user_timezone: str, time: str) -> Optional[Dict]:
        """Вызывает LLM для форматирования тела запроса обновления события."""
        context = {
            "description_string": description_string,
            "user_timezone": user_timezone,
            "UserDateTime": time
        }
        return self._call_formatter_llm("eduart.txt", context)