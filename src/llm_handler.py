# llm_handler.py
import json
import traceback
from openai import OpenAI
import os
from dotenv import load_dotenv
from typing import Optional, Dict, List, Any # Добавили List, Any
from datetime import datetime, timedelta # Добавили timedelta
import logging # Добавили logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка .env файла
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    logger.warning(f".env file not found at {dotenv_path}")


# TODO: добавление "запаса по времени" (Leeway / Clock Skew Tolerance) при валидации токена на бэкенде




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
        # TODO: Сделать модель конфигурируемой
        self.model = os.getenv("LLM_MODEL", "google/gemini-flash-1.5") # Обновил модель на более новую

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
                cleaned_content = response_content.strip().strip('`').strip()
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
                 # Если не ожидаем JSON, просто возвращаем как текст (хотя сейчас все JSON)
                 return {"text_response": response_content} # Обернем в dict для консистентности
        except Exception as e:
            logger.error(f"Error calling LLM: {str(e)}\n{traceback.format_exc()}")
            return {"error": f"LLM API call failed: {e}"} # Возвращаем ошибку в словаре

    def classify_intent(self, user_text: str) -> Optional[Dict]:
        """
        Этап 1: Классифицирует намерение пользователя.
        :param user_text: Текст пользователя.
        :return: Словарь вида {"classification": "add/update/delete/info/other"} или None/ошибку.
        """
        logger.info(f"LLM Stage 1: Classifying intent for text: '{user_text}'")
        prompt = f"""
        Ты — классификатор запросов для календаря. Ответь ТОЛЬКО JSON:
        {{
            "classification": "add/update/delete/info/other"
        }}
        Сообщение пользователя: "{user_text}"

        Примеры:
        Пользователь: "Перенеси тренировку на вечер" → {{"classification": "update"}}
        Пользователь: "Хочу начать заниматься пением по четвергам и вторникам" → {{"classification": "add"}}
        Пользователь: "Убери все запланированные на завтра дела" → {{"classification": "delete"}}
        """
        messages = [{"role": "user", "content": prompt}]
        result = self._call_llm(messages, json_output=True)

        # Валидация ответа
        if result and isinstance(result, dict) and "classification" in result \
           and result["classification"] in ['add', 'update', 'delete', 'info', 'other']:
            logger.info(f"Intent classified as: {result['classification']}")
            return result
        elif result and "error" in result:
             logger.error(f"LLM classification failed: {result['error']}")
             return result # Возвращаем словарь с ошибкой
        else:
            logger.error(f"Invalid classification response format: {result}")
            return {"error": "Invalid classification response format from LLM", "raw_response": result}


    def extract_event_details(self, user_text: str, user_timezone: str = "Asia/Yekaterinburg", time: str = datetime.now().strftime("%Y-%m-%d")) -> Optional[Dict]:
        """
        Этап 2: Извлекает детали события из текста пользователя.
        :param user_text: Текст пользователя.
        :param user_timezone: Часовой пояс пользователя.
        :return: Словарь со структурой события или None/ошибку.
        """
        logger.info(f"LLM Stage 2: Extracting event details for text: '{user_text}'")
        prompt = f"""
        Ты — ассистент для добавления событий в Google Calendar. Время и дата пользователя {time}. Часовой пояс пользователя: {user_timezone}.
        Проанализируй сообщение пользователя и извлеки детали для создания события(-ий) в календаре.
        Сообщение пользователя: "{user_text}". Отвечай ТОЛЬКО JSON:

        {{
            \"event\": [{{
            \"summary\": \"string/null\",
            \"start\": {{
                \"dateTime\": \"ISO8601/null\",
                \"timeZone\": \"Asia/Yekaterinburg\"
            }},
            \"end\": {{
                \"dateTime\": \"ISO8601/null\",
                \"timeZone\": \"Asia/Yekaterinburg\"
            }},
            \"recurrence\": [\"RRULE-строка/null\"]
            }}],
            \"group_type\": \"single/repeating/multiple\",
            \"clarification_needed\": boolean,
            \"message\": \"string/null\"
        }}
        Правила:
        1. Обязательные поля Google Calendar API:
            - summary (название)
            - start.dateTime и end.dateTime (в ISO8601)
            - Для повторений: recurrence с массивом RRULE

        2. Преобразование данных:
            - Если пользователь указал 'длительность':
            end.dateTime = start.dateTime + duration
            - Для повторений: конвертируй в RRULE:
                    Правила для RRULE:
                    1. Все даты в UTC:
                        - Пример: 2025-07-07T23:59:59Z
                    2. Формат BYDAY: 
                        - Дни недели: MO,TU,WE,TH,FR,SA,SU
                    3. Интервалы:
                        - 'каждые 2 недели' → INTERVAL=2
                    4. Дефолтный UNTIL:
                        - Если пользователь не указал срок → добавляй 3 месяца от текущей даты
                        Примеры преобразований:
                        
                - 'По вт и чт' → 
                    \"RRULE:FREQ=WEEKLY;BYDAY=TU,TH;UNTIL=20250707T235959Z\"
                - 'Каждые 10 дней' → 
                    \"RRULE:FREQ=DAILY;INTERVAL=10;UNTIL=20250707T235959Z\""

        3. Логика группировки:
            - repeating: одинаковые summary + recurrence
            - multiple: разные summary или разное время

        4. Уточнения:
            - Если отсутствует время → предложи слоты (например, 9:00, 14:00, 19:00)
            - Для создания повторяющихся событий → начинай с ближайшей даты

        Примеры:

        Пользователь: 'Совещания по проекту X каждый вторник в 10:00 на 1 час'
        Ответ:
        {{
            \"event\": [
            {{
                \"summary\": \"Совещание по проекту X\",
                \"start\": {{ \"dateTime\": \"2025-03-04T10:00:00+03:00\" }},
                \"end\": {{ \"dateTime\": \"2025-03-04T11:00:00+03:00\" }},
                \"recurrence\": [\"RRULE:FREQ=WEEKLY;BYDAY=TU\"]
            }}
            ],
            \"group_type\": \"repeating\",
            \"clarification_needed\": false,
            \"message\": null
        }}

        Пользователь: 'Добавь тренировки в 19:00 по пн и чт'
        Ответ:
        {{
            \"event\": [
            {{
                \"summary\": \"Тренировка\",
                \"start\": {{ \"dateTime\": null }},
                \"end\": {{ \"dateTime\": null }},
                \"recurrence\": [\"RRULE:FREQ=WEEKLY;BYDAY=MO,TH\"]
            }}
            ],
            \"group_type\": \"repeating\",
            \"clarification_needed\": true,
            \"message\": \"Укажите продолжительность и стартовую дату. Например: 60 минут, с 15 апреля?\"
        }}

        Пользователь: 'Митап 25.03 в 18:30 и воркшоп 27.03 в 11:00'
        Ответ:
        {{
            \"event\": [
            {{
                \"summary\": \"Митап\",
                \"start\": {{ \"dateTime\": \"2025-03-25T18:30:00+03:00\" }},
                \"end\": {{ \"dateTime\": null }},
                \"recurrence\": null
            }},
            {{
                \"summary\": \"Воркшоп\",
                \"start\": {{ \"dateTime\": \"2025-03-27T11:00:00+03:00\" }},
                \"end\": {{ \"dateTime\": null }},
                \"recurrence\": null
            }}
            ],
            \"group_type\": \"multiple\",
            \"clarification_needed\": true,
            \"message\": \"Укажите продолжительность для каждого события. Например: 2 часа для митапа и 3 часа для воркшопа?\""
        }}
        }}
        """
        # Примечание: Вычисление дат типа (today+1day), (next_friday) нужно делать вне строки или передавать их как параметры.
        # Простой способ - передать сегодняшнюю дату и день недели. LLM должна справиться.

        messages = [{"role": "user", "content": prompt}]
        result = self._call_llm(messages, json_output=True)

        # TODO: Добавить более строгую валидацию структуры ответа (Pydantic модель?)
        if result and isinstance(result, dict) and "event" in result and "clarification_needed" in result:
             logger.info(f"Event details extracted: {result}")
             return result
        elif result and "error" in result:
            logger.error(f"LLM extraction failed: {result['error']}")
            return result
        else:
            logger.error(f"Invalid event extraction response format: {result}")
            return {"error": "Invalid event extraction response format from LLM", "raw_response": result}


    def clarify_event_details(self, initial_request: str, current_event_data: Dict, question_asked: str, user_answer: str, user_timezone: str = "Asia/Yekaterinburg", time: str = datetime.now().strftime("%Y-%m-%d")) -> Optional[Dict]:
        """
        Этап 3: Обновляет детали события на основе ответа пользователя на уточняющий вопрос.
        :param initial_request: Исходный запрос пользователя.
        :param current_event_data: Текущие извлеченные данные события (JSON из прошлого шага).
        :param question_asked: Вопрос, который был задан пользователю.
        :param user_answer: Ответ пользователя на вопрос.
        :param user_timezone: Часовой пояс пользователя.
        :return: Обновленный словарь со структурой события или None/ошибку.
        """
        logger.info(f"LLM Stage 3: Clarifying event details.")
        logger.info(f"Initial request: '{initial_request}'")
        logger.info(f"Current data: {current_event_data}")
        logger.info(f"Question asked: '{question_asked}'")
        logger.info(f"User answer: '{user_answer}'")

        # Сериализуем текущие данные для промпта
        current_data_str = json.dumps(current_event_data, indent=2, ensure_ascii=False)

        prompt = f"""
        Контекст:
        - Время и лень пользователя: {time}
        - Часовой пояс: {user_timezone}
        - Исходный запрос пользователя: "{initial_request}"
        - Текущие извлеченные данные о событии: {current_data_str}
        - Заданный пользователю вопрос: "{question_asked}"
        - Ответ пользователя: "{user_answer}"

        Задача: Обнови текущие данные о событии (`event` массив), используя ответ пользователя. Постарайся заполнить все недостающие обязательные поля (`summary`, `start.dateTime`, `end.dateTime`). Вычисли `end.dateTime`, если известны начало и длительность, или добавь 1 час к началу, если длительность неизвестна. Если после ответа пользователя все еще не хватает ОБЯЗАТЕЛЬНЫХ полей, снова установи `clarification_needed = true` и задай СЛЕДУЮЩИЙ по важности вопрос в `message`. Если все обязательные поля теперь заполнены, установи `clarification_needed = false` и `message = null`.

        Верни ТОЛЬКО обновленный JSON объект в ТОМ ЖЕ ФОРМАТЕ, что и `extract_event_details`:
        {{
          "event": [ {{ ... обновленные данные ... }} ],
          "group_type": "...", // Сохрани или обнови, если ответ повлиял
          "clarification_needed": boolean,
          "message": "string/null"
        }}
        1. Обязательные поля:
            - summary ≠ null
            - start.dateTime в формате ISO8601 (2025-04-05T19:00:00+05:00)
            - Для повторяющихся событий: recurrence ≠ null

        2. Автозаполнение:
            - Если указана длительность (например, '1 час') → вычисляй end.dateTime
            - Для повторений без UNTIL → добавляй дефолтный период (3 месяца)

        3. Логика уточнений:
            - Если start.dateTime без времени → clarification_needed=true
            - Если recurrence без конечной даты → предложи варианты ('Повторять до 04.07.2025?')
            - Для multiple событий → проверяй каждое отдельно

        4. Формат RRULE:
            Правила для RRULE:
            1. Все даты в UTC:
                - Пример: 2025-07-07T23:59:59Z
            2. Формат BYDAY: 
                - Дни недели: MO,TU,WE,TH,FR,SA,SU
            3. Интервалы:
                - 'каждые 2 недели' → INTERVAL=2
            4. Дефолтный UNTIL:
                - Если пользователь не указал срок → добавляй 3 месяца от текущей даты
                  Примеры преобразований:

        - 'По вт и чт' → 
            \"RRULE:FREQ=WEEKLY;BYDAY=TU,TH;UNTIL=20250707T235959Z\"
        - 'Каждые 10 дней' → 
            \"RRULE:FREQ=DAILY;INTERVAL=10;UNTIL=20250707T235959Z\""

        Пример: Если спросили "На какое время?" и пользователь ответил "на 3 часа дня", обнови `start.dateTime` и `end.dateTime`.
        """
        messages = [{"role": "user", "content": prompt}]
        result = self._call_llm(messages, json_output=True)

        # TODO: Добавить валидацию структуры ответа
        if result and isinstance(result, dict) and "event" in result and "clarification_needed" in result:
             logger.info(f"Event details clarified/updated: {result}")
             return result
        elif result and "error" in result:
            logger.error(f"LLM clarification failed: {result['error']}")
            return result
        else:
            logger.error(f"Invalid clarification response format: {result}")
            return {"error": "Invalid clarification response format from LLM", "raw_response": result}

# Пример использования (только для локального теста)
if __name__ == "__main__":
    handler = LLMHandler()
    test_input = "Хочу начать бегать по вторникам и четвергам"

    print("--- Stage 1: Classification ---")
    classification = handler.classify_intent(test_input)
    print(json.dumps(classification, indent=2, ensure_ascii=False))

    if classification and classification.get("classification") == "add":
        print("\n--- Stage 2: Extraction ---")
        extracted_data = handler.extract_event_details(test_input)
        print(json.dumps(extracted_data, indent=2, ensure_ascii=False))

        if extracted_data and extracted_data.get("clarification_needed"):
            print("\n--- Stage 3: Clarification ---")
            question = extracted_data.get("message")
            print(f"Question: {question}")
            user_answer = input("Your answer: ") # Для интерактивного теста
            # user_answer = "В 10 утра на час"
            print(f"User Answer: {user_answer}")
            clarified_data = handler.clarify_event_details(
                initial_request=test_input,
                current_event_data=extracted_data,
                question_asked=question,
                user_answer=user_answer
            )
            print("\nClarified Data:")
            print(json.dumps(clarified_data, indent=2, ensure_ascii=False))

            # Второй раунд уточнения, если нужно
            if clarified_data and clarified_data.get("clarification_needed"):
                 print("\n--- Stage 3: Clarification (Round 2) ---")
                 question2 = clarified_data.get("message")
                 print(f"Question: {question2}")
                 user_answer2 = "К терапевту"
                 print(f"User Answer: {user_answer2}")
                 final_data = handler.clarify_event_details(
                     initial_request=test_input, # Можно передавать всю историю? Пока нет.
                     current_event_data=clarified_data,
                     question_asked=question2,
                     user_answer=user_answer2
                 )
                 print("\nFinal Data:")
                 print(json.dumps(final_data, indent=2, ensure_ascii=False))