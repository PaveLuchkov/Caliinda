import json
from datetime import datetime, timedelta # Добавили timedelta
import os
import re
import traceback # Для более детальных ошибок
from typing import Optional, Dict, List, Any # Добавили Any

# --- Jinja2 Setup ---
# Установите Jinja2: pip install Jinja2
try:
    import jinja2
    from pathlib import Path
    # Ищем директорию 'src' относительно текущего файла, если она существует
    # Если нет, используем директорию текущего файла, затем текущую рабочую директорию
    script_dir = Path(__file__).parent
    src_dir = script_dir if script_dir.name == 'src' else script_dir / 'src'

    if src_dir.exists() and src_dir.is_dir():
         PROMPT_DIR = src_dir
    elif script_dir.exists() and script_dir.is_dir():
         PROMPT_DIR = script_dir # Запасной вариант - папка со скриптом
    else:
         PROMPT_DIR = Path(".") # Крайний запасной вариант - текущая директория

    print(f"Jinja2: Попытка использовать директорию шаблонов: {PROMPT_DIR.resolve()}")

    if PROMPT_DIR.exists() and PROMPT_DIR.is_dir():
        template_loader = jinja2.FileSystemLoader(searchpath=str(PROMPT_DIR.resolve()))
        # Используем autoescape=False, т.к. мы генерируем текст, а не HTML/XML
        # Undefined=jinja2.StrictUndefined поможет выявить отсутствующие переменные в шаблонах
        template_env = jinja2.Environment(
            loader=template_loader,
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=False,
            undefined=jinja2.StrictUndefined
        )
        print(f"Jinja2: Окружение успешно создано для директории: {PROMPT_DIR.resolve()}")
    else:
        print(f"Jinja2: Директория шаблонов НЕ НАЙДЕНА в {PROMPT_DIR} или ее родительских папках.")
        template_env = None
except ImportError:
    print("Ошибка: Jinja2 не установлен. Пожалуйста, установите: pip install Jinja2")
    template_env = None
except Exception as e:
    print(f"Критическая ошибка инициализации Jinja2: {e}")
    traceback.print_exc()
    template_env = None
    exit(1) # Выход, без Jinja2 нет смысла продолжать


# --- Настройки ---
YOUR_LLM_API_KEY = os.getenv("OPENROUTER_API_KEY")
LLM_API_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
LLM_MODEL = "google/gemini-2.0-flash-001"
# LLM_MODEL = "anthropic/claude-3-haiku-20240307"
# LLM_MODEL = "openai/gpt-4o-mini"
USE_API = True # True - использовать API, False - ручной режим
TEMPER = "бро, говоришь с матами" # Вынесли темперамент в переменную

# --- Загрузка Шаблонов ---
system_prompt_template: Optional[jinja2.Template] = None # Будет объектом Jinja2
user_prompt_template: Optional[jinja2.Template] = None   # Будет объектом Jinja2

# Имена файлов шаблонов - убедитесь, что они совпадают с реальными файлами!
SYSTEM_TEMPLATE_FILENAME = "prompt_system.template" # Имя файла системного промпта
USER_TEMPLATE_FILENAME = "prompt_user.template" # Имя файла пользовательского промпта (для ручного режима)

try:
    if template_env:
        # Загружаем объекты шаблонов, рендерить будем позже
        system_prompt_template = template_env.get_template(SYSTEM_TEMPLATE_FILENAME)
        user_prompt_template = template_env.get_template(USER_TEMPLATE_FILENAME)
        print(f"Шаблоны '{SYSTEM_TEMPLATE_FILENAME}' и '{USER_TEMPLATE_FILENAME}' успешно загружены.")
    else:
         raise RuntimeError("Jinja2 environment not available.") # Вызовет переход в except ниже

except (jinja2.TemplateNotFound, RuntimeError) as e:
    print(f"Критическая ошибка: Не удалось загрузить шаблон(ы) ({e}).")
    print(f"Убедитесь, что файлы '{SYSTEM_TEMPLATE_FILENAME}' и '{USER_TEMPLATE_FILENAME}' существуют в директории '{PROMPT_DIR.resolve()}'.")
    # Можно добавить встроенные строки как fallback, если хотите
    # fallback_system = "You are a helpful assistant..."
    # fallback_user = "User input: {{ user_input }}"
    exit(1) # Выход, т.к. без шаблонов тест не имеет смысла
except jinja2.exceptions.TemplateSyntaxError as e:
    print(f"Критическая ошибка: Синтаксическая ошибка в шаблоне '{e.filename}' (строка {e.lineno}): {e.message}")
    exit(1)


# --- Мок Данные Календаря ---
# ИСПРАВЛЕНО: Убран лишний внешний список
mock_calendar_data: List[Dict[str, Any]] = [
    # ... ваши мок-данные ...
    {
        "id": "event1_april27_morning",
        "summary": "Утренний Стендап",
        "start": "2025-04-27T09:00:00",
        "end": "2025-04-27T09:30:00",
        "description": "Командная синхронизация задач на день",
        "attendees": ["teamlead@example.com", "developer@example.com"],
        "location": "Конференц-зал 1"
    },
    {
        "id": "event2_april27_lunch",
        "summary": "Бизнес-ланч с партнёрами",
        "start": "2025-04-27T12:30:00",
        "end": "2025-04-27T14:00:00",
        "description": "Обсудить условия нового контракта",
        "attendees": ["partner1@example.com", "partner2@example.com"],
        "location": "Ресторан 'Итальянский Дворик'"
    },
    {
        "id": "event3_april27_evening",
        "summary": "Тренировка по теннису",
        "start": "2025-04-27T18:00:00",
        "end": "2025-04-27T19:30:00",
        "location": "Спортивный комплекс 'Олимп'"
    },
    {
        "id": "event4_april28_morning",
        "summary": "Планёрка с проектной командой",
        "start": "2025-04-28T10:00:00",
        "end": "2025-04-28T11:00:00",
        "description": "Определение задач на спринт",
        "attendees": ["pm@example.com", "developer1@example.com", "qa@example.com"],
        "location": "Онлайн (Zoom)"
    },
    {
        "id": "event5_april28_midday",
        "summary": "Демо новой версии продукта",
        "start": "2025-04-28T13:00:00",
        "end": "2025-04-28T14:30:00",
        "description": "Презентация для клиентов",
        "attendees": ["client1@example.com", "client2@example.com"],
        "location": "Офис, переговорная 2"
    },
    {
        "id": "event6_april28_evening",
        "summary": "Вечерний поход в кино",
        "start": "2025-04-28T20:00:00",
        "end": "2025-04-28T22:30:00",
        "description": "Просмотр нового фильма Marvel",
        "location": "Кинотеатр 'Синема Парк'"
    },
    {
        "id": "event7_april29_morning",
        "summary": "Визит к стоматологу",
        "start": "2025-04-29T08:30:00",
        "end": "2025-04-29T09:30:00",
        "location": "Клиника 'Здоровье Улыбки'"
    },
    {
        "id": "event8_april29_afternoon",
        "summary": "Воркшоп по UX-дизайну",
        "start": "2025-04-29T13:00:00",
        "end": "2025-04-29T16:00:00",
        "description": "Погружение в принципы проектирования пользовательского опыта",
        "attendees": ["uxlead@example.com", "designer@example.com", "productmanager@example.com"],
        "location": "Коворкинг 'Точка роста'"
    },
    {
        "id": "event9_april29_evening",
        "summary": "Ужин с друзьями",
        "start": "2025-04-29T19:00:00",
        "end": "2025-04-29T21:00:00",
        "description": "Неформальная встреча в уютном месте",
        "location": "Кафе 'Уютное'"
    }
]


# --- Функции парсинга и симуляции календаря ---
def parse_calendar_query(query_string: str) -> tuple[Optional[str], Optional[str], List[str]]:
    """Парсит строку запроса календаря на timeMin, timeMax и ключевые слова."""
    time_min_match = re.search(r'timeMin:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', query_string)
    time_max_match = re.search(r'timeMax:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', query_string)
    time_min = time_min_match.group(1) if time_min_match else None
    time_max = time_max_match.group(1) if time_max_match else None

    # Удаляем части timeMin/timeMax из строки, чтобы получить ключевые слова
    text_part = query_string
    if time_min:
        text_part = text_part.replace(time_min_match.group(0), '', 1)
    if time_max:
        text_part = text_part.replace(time_max_match.group(0), '', 1)

    # Очищаем оставшуюся строку от лишних символов и разделяем на слова
    text_part = re.sub(r'^\s*,?\s*|\s*,?\s*$', '', text_part.strip()).strip() # Убираем висящие запятые и пробелы
    keywords = []
    if text_part:
         keywords = [kw for kw in text_part.lower().split() if kw] # Разделяем и убираем пустые строки

    return time_min, time_max, keywords

def simulate_calendar_lookup(query_string: str, mock_data: List[Dict[str, Any]]) -> str:
    """Симулирует поиск событий в календаре на основе запроса."""
    time_min_str, time_max_str, keywords = parse_calendar_query(query_string)
    print(f"\n[Симулятор Календаря] Получен запрос: '{query_string}'")
    print(f"[Симулятор Календаря] Распарсено: timeMin={time_min_str}, timeMax={time_max_str}, keywords={keywords}")

    results: List[Dict[str, Any]] = []
    time_min_dt: Optional[datetime] = None
    time_max_dt: Optional[datetime] = None

    try:
        if time_min_str:
            time_min_dt = datetime.fromisoformat(time_min_str)
        if time_max_str:
            time_max_dt = datetime.fromisoformat(time_max_str)
    except ValueError as e:
        print(f"[Симулятор Календаря] Ошибка парсинга даты в запросе: {e}. Запрос игнорируется.")
        return "..." # Возвращаем пустой результат при неверном формате дат

    filtered_events: List[Dict[str, Any]] = []

    # 1. Фильтрация по времени (если задано)
    if time_min_dt and time_max_dt:
        for event in mock_data:
            try:
                event_start_dt = datetime.fromisoformat(event['start'])
                event_end_dt = datetime.fromisoformat(event['end'])
                # Проверка на пересечение интервалов: (StartA < EndB) and (EndA > StartB)
                if event_start_dt < time_max_dt and event_end_dt > time_min_dt:
                    filtered_events.append(event)
            except (ValueError, KeyError, TypeError) as e:
                print(f"[Симулятор Календаря] Предупреждение: Пропуск события из-за ошибки формата или ключа: {event.get('id', 'N/A')}, ошибка: {e}")
                continue # Пропускаем события с неверным форматом/отсутствующими ключами
    # ИСПРАВЛЕНО: Логика для случая без времени и ключевых слов
    elif not time_min_dt and not time_max_dt and not keywords:
        # Если нет ни времени, ни слов, вернем события на сегодня (как пример)
        print("[Симулятор Календаря] Запрос без диапазона времени и ключевых слов. Поиск событий на сегодня.")
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        for event in mock_data:
            try:
                event_start_dt = datetime.fromisoformat(event['start'])
                if today_start <= event_start_dt < today_end:
                    filtered_events.append(event)
            except (ValueError, KeyError, TypeError): continue
        if not filtered_events:
            print("[Симулятор Календаря] На сегодня событий не найдено.")
            # Можно вернуть "...", а можно вернуть все события, если сегодня пусто
            # return "..."
            # Или вернуть все, если на сегодня пусто? Зависит от желаемого поведения.
            # Давайте вернем "..." чтобы не перегружать LLM если календарь большой
            return "..."

    else:
        # Если задано только одно время или только ключевые слова, или и то и другое
        # но не полный диапазон timeMin/timeMax, то фильтруем сначала все данные
        filtered_events = mock_data # Начинаем со всех данных, если нет диапазона

    # 2. Фильтрация по ключевым словам (если заданы)
    if keywords:
        keyword_filtered_results = []
        for event in filtered_events: # Фильтруем из уже отфильтрованных по времени (если было)
             # Собираем текст для поиска из релевантных полей
             text_fields = [
                 str(event.get('summary', '')).lower(),
                 str(event.get('description', '')).lower(),
                 str(event.get('location', '')).lower()
             ]
             # Добавляем участников, если они есть
             attendees = event.get('attendees')
             if isinstance(attendees, list):
                 text_fields.extend([str(a).lower() for a in attendees])

             text_to_search = " ".join(text_fields)

             # Проверяем, что ВСЕ ключевые слова присутствуют в тексте
             if all(kw in text_to_search for kw in keywords):
                keyword_filtered_results.append(event)
        results = keyword_filtered_results # Результат - отфильтрованные по словам
    else:
        results = filtered_events # Если слов не было, результат - отфильтрованные по времени (или все)

    # 3. Формирование строки ответа
    if not results:
        print("[Симулятор Календаря] Событий, удовлетворяющих запросу, не найдено.")
        return "..." # Стандартный ответ "ничего не найдено"
    else:
        output_lines = []
        # Сортируем результаты по времени начала для лучшей читаемости
        results.sort(key=lambda x: x.get('start', ''))
        for event in results:
            line_parts = [
                f"EventID: {event['id']}",
                f"Summary: {event.get('summary', 'N/A')}",
                f"Time: {event.get('start', 'N/A')} - {event.get('end', 'N/A')}"
            ]
            if event.get('description'): line_parts.append(f"Description: {event.get('description')}")
            if event.get('location'): line_parts.append(f"Location: {event.get('location')}")
            if event.get('attendees'): line_parts.append(f"Attendees: {','.join(event.get('attendees', []))}")
            output_lines.append("; ".join(line_parts))

        result_str = "\n".join(output_lines)
        print(f"[Симулятор Календаря] Найденные события ({len(results)}):\n{result_str}")
        return result_str

# --- Функция Вызова LLM ---
def call_llm_api(
    system_template: jinja2.Template, # Передаем шаблон
    system_render_context: Dict[str, Any], # Контекст для рендеринга системного промпта
    user_prompt_display_context: Dict[str, Any], # Контекст для показа user_prompt (ручной режим)
    history: List[Dict[str, str]], # История для API
    current_user_input_for_api: str, # Текущий ввод для API
    calendar_results_for_api: Optional[str] = None # Результаты календаря для API
) -> Optional[str]:
    """
    Вызывает LLM API с отрендеренным системным промптом и формирует сообщения API.
    :param system_template: Объект шаблона Jinja2 для системного промпта.
    :param system_render_context: Словарь с данными для рендеринга system_template.
    :param user_prompt_display_context: Словарь с данными для рендеринга user_prompt_template (для показа).
    :param history: Текущая история диалога для API.
    :param current_user_input_for_api: Текущий ввод пользователя для добавления в messages API.
    :param calendar_results_for_api: Результаты поиска календаря для добавления как system message в API.
    :return: Строка с JSON-ответом LLM или None при ошибке.
    """
    global user_prompt_template # Используем глобальный шаблон пользователя (для ручного режима)

    # Рендерим системный промпт ПЕРЕД вызовом
    try:
        system_content = system_template.render(**system_render_context)
    except jinja2.exceptions.UndefinedError as e:
        print(f"[Ошибка Рендеринга] Отсутствует переменная в системном шаблоне: {e}")
        return None
    except Exception as e:
        print(f"[Ошибка Рендеринга] Не удалось отрендерить системный шаблон: {e}")
        traceback.print_exc()
        return None

    if not USE_API:
        # --- Ручной режим ---
        print("\n--- СООБЩЕНИЕ ДЛЯ LLM (РУЧНОЙ РЕЖИМ) ---")
        print("--- SYSTEM PROMPT ---")
        print(system_content) # Показываем отрендеренный системный промпт
        print("\n--- USER MESSAGE (с историей и вводом) ---")
        # Попытка отрендерить пользовательский промпт для показа
        if user_prompt_template:
            try:
                 # Передаем тот же контекст, который используется для API
                 rendered_user_for_display = user_prompt_template.render(**user_prompt_display_context)
                 print(rendered_user_for_display)
            except Exception as render_err:
                 print(f"(Ошибка рендеринга пользовательского шаблона для показа: {render_err})")
                 print(f"Контекст: {user_prompt_display_context}")
        else:
            print("(Шаблон пользовательского промпта не загружен)")
            print(f"История: {history}")
            if calendar_results_for_api: print(f"Результаты календаря:\n{calendar_results_for_api}")
            print(f"Ввод пользователя: {current_user_input_for_api}")


        print("--- КОНЕЦ СООБЩЕНИЯ ---")
        llm_response_json = input("Скопируйте идею выше, вставьте в LLM (учитывая роли system/user), и введите сюда JSON-ответ модели:\n> ")
        return llm_response_json.strip()

    # --- Режим API ---
    # Импортируем requests только здесь, если нужен только для API режима
    try:
        import requests
    except ImportError:
        print("[Ошибка] Библиотека 'requests' не установлена. Пожалуйста, установите: pip install requests")
        return None


    if not YOUR_LLM_API_KEY:
        print("[API Ошибка] Ключ OPENROUTER_API_KEY не найден в переменных окружения.")
        return None

    headers = {
        "Authorization": f"Bearer {YOUR_LLM_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("LLM_HTTP_REFERER", "http://localhost/calendar-test"),
        "X-Title": os.getenv("LLM_X_TITLE", "Calendar Test Harness"),
    }

    # Формируем `messages` для API
    messages = [{"role": "system", "content": system_content}] # Начинаем с системного промпта

    # Добавляем историю (пропускаем системные сообщения из истории, т.к. основной промпт уже есть)
    for msg in history:
        role = msg.get("role", "user").lower()
        content = msg.get("content", "")
        # Простая валидация и добавление
        if role in ["user", "assistant"] and content:
            messages.append({"role": role, "content": content})
        # elif role == "system":
        #     print(f"[API DEBUG] Пропуск системного сообщения из истории: {content[:100]}...")

    # Добавляем результаты поиска календаря как system сообщение (если есть)
    # Это важно делать ПОСЛЕ истории и ПЕРЕД текущим вводом пользователя (или после него, в зависимости от модели)
    # Поместим ПОСЛЕ истории, ПЕРЕД новым запросом пользователя, как контекст для этого запроса.
    if calendar_results_for_api:
        messages.append({
            "role": "system", # Или "tool"? Зависит от модели. System обычно работает.
            "content": f"Calendar Search Results:\n```\n{calendar_results_for_api}\n```"
        })

    # Добавляем текущий ввод пользователя (если он не пустой)
    if current_user_input_for_api:
        messages.append({"role": "user", "content": current_user_input_for_api})
    elif not calendar_results_for_api:
        # Не отправляем запрос без пользовательского ввода и без результатов календаря
        print("[API Предупреждение] Попытка вызова API без нового ввода пользователя и без результатов календаря.")
        # return None # Или можно отправить, если модель должна реагировать на пустой ввод? Зависит от задачи.
        # Пока разрешим, может быть нужно для инициации диалога или обработки результатов календаря без доп. ввода.
        pass


    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": 0.5,
        "max_tokens": 500,
        "response_format": {"type": "json_object"} # Запрос JSON ответа
    }

    print("\n[API] Отправка запроса к LLM...")
    # Раскомментируйте для детальной отладки запроса
    # print(f"[API] Эндпоинт: {LLM_API_ENDPOINT}")
    # print(f"[API] Заголовки: {headers}")
    # print(f"[API] Payload Messages:\n{json.dumps(payload['messages'], indent=2, ensure_ascii=False)}")

    try:
        response = requests.post(LLM_API_ENDPOINT, headers=headers, json=payload, timeout=90) # Увеличенный таймаут

        print(f"[API] Статус код ответа: {response.status_code}")
        response.raise_for_status() # Вызовет HTTPError для плохих статусов (4xx, 5xx)

        response_data = response.json()
        # print(f"[API DEBUG] Полный ответ сервера:\n{json.dumps(response_data, indent=2, ensure_ascii=False)}")

        if 'choices' in response_data and len(response_data['choices']) > 0:
             message_content = response_data['choices'][0].get('message', {}).get('content')
             if message_content:
                 # Базовая очистка: убираем внешние пробелы и возможные ```json ... ``` обертки
                 llm_output_cleaned = message_content.strip()
                 if llm_output_cleaned.startswith('```json'):
                     llm_output_cleaned = llm_output_cleaned[7:]
                 if llm_output_cleaned.startswith('json'):
                      llm_output_cleaned = llm_output_cleaned[4:]
                 if llm_output_cleaned.endswith('```'):
                     llm_output_cleaned = llm_output_cleaned[:-3]
                 llm_output_cleaned = llm_output_cleaned.strip()

                 # Закомментированная опасная замена кавычек - использовать только в крайнем случае
                 # try:
                 #     json.loads(llm_output_cleaned)
                 # except json.JSONDecodeError:
                 #     print("[API DEBUG] Ответ не JSON, попытка исправить одинарные кавычки...")
                 #     llm_output_cleaned = llm_output_cleaned.replace("'", '"') # ОПАСНО!

                 # Возвращаем очищенную СТРОКУ
                 return llm_output_cleaned
             else:
                 print("[API Ошибка] В ответе есть 'choices', но отсутствует 'content' в 'message'.")
                 print(json.dumps(response_data, indent=2, ensure_ascii=False))
                 return None
        else:
             print("[API Ошибка] Неожиданный формат ответа (отсутствуют 'choices' или они пусты):")
             print(json.dumps(response_data, indent=2, ensure_ascii=False))
             return None

    except requests.exceptions.HTTPError as e:
        print(f"[API Ошибка] HTTP Ошибка: {e}")
        # Попытка извлечь детали ошибки из тела ответа, если они есть
        error_details = "Нет деталей в ответе."
        if e.response is not None:
            try:
                error_data = e.response.json()
                error_details = json.dumps(error_data, indent=2, ensure_ascii=False)
            except json.JSONDecodeError:
                error_details = e.response.text
        print(f"[API Ошибка] Тело ответа:\n{error_details}")
        return None
    except requests.exceptions.Timeout:
        print(f"[API Ошибка] Таймаут запроса ({payload.get('timeout', 90)} сек). Сервер не ответил вовремя.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"[API Ошибка] Ошибка соединения/запроса: {e}")
        return None
    except json.JSONDecodeError as e: # Ошибка парсинга JSON *ответа сервера*, не самого контента LLM
        print(f"[API Ошибка] Не удалось распарсить JSON *ответа сервера*: {e}")
        if 'response' in locals() and response is not None: print(f"[API Ошибка] Тело ответа (не JSON):\n{response.text}")
        return None
    except (KeyError, IndexError, TypeError) as e:
        print(f"[API Ошибка] Неожиданный формат JSON *ответа сервера* или ошибка доступа к ключу/индексу: {e}")
        if 'response_data' in locals():
            print(f"[API Ошибка] Полный JSON ответ:\n{json.dumps(response_data, indent=2, ensure_ascii=False)}")
        elif 'response' in locals():
             print(f"[API Ошибка] Тело ответа (возможно, не JSON):\n{response.text}")
        traceback.print_exc() # Для отладки неожиданных ошибок структуры
        return None
    except Exception as e: # Другие неожиданные ошибки
        print(f"[API Ошибка] Непредвиденная ошибка при вызове API: {e}")
        traceback.print_exc()
        return None

# --- Основной Цикл ---
conversation_history: List[Dict[str, str]] = []

# Проверяем, что шаблоны загружены перед циклом
if not system_prompt_template:
    print("Критическая ошибка: Системный шаблон не был загружен. Выход.")
    exit(1)
# user_prompt_template используется только для ручного режима, его отсутствие не критично для API

print("\n--- Начало диалога ---")
print("Введите 'выход' для завершения.")

while True:
    try: # Общий блок try для перехвата ошибок внутри цикла итерации
        user_input = input("\nВаш запрос:\n> ")
        if user_input.lower() in ['выход', 'exit', 'quit']:
            print("Завершение работы.")
            break
        if not user_input.strip():
            print("Пустой ввод, пожалуйста, введите запрос.")
            continue

        current_time = datetime.now()
        current_time_iso = current_time.strftime('%Y-%m-%dT%H:%M:%S')
        # Попытка получить таймзону (может вернуть локальное смещение или имя)
        try:
            user_timezone = current_time.astimezone().tzname()
            if user_timezone is None: # На некоторых системах может вернуть None
                user_timezone = str(current_time.astimezone().tzinfo)
        except Exception:
            user_timezone = "Unknown" # Запасной вариант

        # --- Подготовка контекстов ---
        # Контекст для рендеринга СИСТЕМНОГО промпта (передается в API)
        system_render_context = {
            "temper": TEMPER,
            "CurrentTime": current_time_iso,
            "UserTimeZone": user_timezone
            # Можно добавить другие глобальные переменные сюда
        }

        # Контекст для отображения ПОЛЬЗОВАТЕЛЬСКОГО промпта (только для ручного режима)
        user_prompt_display_context = {
            "UserDateTime": current_time_iso, # Используем одно имя для консистентности
            "user_timezone": user_timezone,
            "history": conversation_history,
            "user_input": user_input,
            "calendar_search_results": None # Изначально нет результатов
        }


        print(f"DEBUG: Контекст для системного промпта: {system_render_context}")

        # --- Первый вызов LLM ---
        print("DEBUG: Вызов LLM (первый)...")
        llm_response_json_str = call_llm_api(
            system_template=system_prompt_template,
            system_render_context=system_render_context,
            user_prompt_display_context=user_prompt_display_context, # Для ручного режима
            history=conversation_history,
            current_user_input_for_api=user_input,
            calendar_results_for_api=None # Нет результатов календаря на первом шаге
        )

        if not llm_response_json_str:
            print("Не удалось получить ответ от LLM (API вернуло None или пустую строку). Попробуйте снова.")
            # Не добавляем ничего в историю, если ответа нет
            continue

        # --- Парсинг и Валидация ответа ---
        llm_output: Optional[Dict[str, Any]] = None
        try:
            # Парсим строку JSON, которую вернул call_llm_api
            llm_output = json.loads(llm_response_json_str)

            print(f"DEBUG: Распарсенный ПЕРВЫЙ ответ LLM (тип {type(llm_output)}): {llm_output}")

            # Базовая валидация структуры
            if not isinstance(llm_output, dict):
                raise TypeError(f"Ожидался JSON-объект (словарь), получен тип {type(llm_output)}")
            if len(llm_output) != 1:
                raise ValueError(f"JSON должен содержать ровно один ключ ('message_to_user', 'calendar' или 'prompt_to_llm'), получено: {list(llm_output.keys())}")

            # --- Валидация пройдена -> добавляем user input и assistant response в историю ---
            conversation_history.append({"role": "user", "content": user_input})
            # Сохраняем именно СТРОКУ JSON как ответ ассистента
            conversation_history.append({"role": "assistant", "content": llm_response_json_str})

            # --- Обработка ВАЛИДНОГО ответа ---
            if "message_to_user" in llm_output:
                message = llm_output["message_to_user"]
                if not isinstance(message, str):
                     print(f"Предупреждение: 'message_to_user' содержит не строку: {type(message)}. Отображаем как есть.")
                print(f"\n🤖 Ответ ассистента:\n{message}")
                # Цикл завершен, ждем следующий ввод пользователя

            elif "calendar" in llm_output:
                calendar_query = llm_output["calendar"]
                if not isinstance(calendar_query, str):
                    print(f"\n❌ Ошибка: Ключ 'calendar' содержит не строку: {type(calendar_query)}. Невозможно выполнить запрос.")
                    # Откатываем последнее сообщение ассистента из истории
                    if conversation_history and conversation_history[-1]["role"] == "assistant":
                        conversation_history.pop()
                    # Откатываем и сообщение пользователя, т.к. оно привело к невалидному ответу
                    if conversation_history and conversation_history[-1]["role"] == "user":
                        conversation_history.pop()
                    continue # Переходим к следующему запросу пользователя

                print(f"\n⚙️ LLM запросила календарь: {calendar_query}")

                calendar_results: Optional[str] = None
                try:
                    # Вызываем симулятор календаря
                    calendar_results = simulate_calendar_lookup(calendar_query, mock_calendar_data)
                except Exception as sim_e:
                    print(f"\n❌ Критическая ошибка симулятора календаря: {sim_e}")
                    traceback.print_exc()
                    # Откатываем историю, чтобы не засорять ее запросом, который не удалось обработать
                    if conversation_history and conversation_history[-1]["role"] == "assistant":
                        conversation_history.pop()
                    if conversation_history and conversation_history[-1]["role"] == "user":
                        conversation_history.pop()
                    print("Попробуйте переформулировать запрос.")
                    continue # Пропускаем остаток итерации

                # calendar_results будет строкой ("..." или реальные данные)
                # Добавляем результаты календаря в историю как system сообщение для СЛЕДУЮЩЕГО вызова LLM
                # Важно: Не добавляем в историю для API *здесь*, а передаем в следующий вызов call_llm_api
                # Но для консистентности и отладки, можем добавить и в локальную историю
                # Решено: Будем передавать в call_llm_api параметром, он сам добавит в messages
                # calendar_system_message = {"role": "system", "content": f"Calendar Search Results:\n```\n{calendar_results}\n```"}
                # conversation_history.append(calendar_system_message) # Решили не добавлять сюда явно

                print("\n🔄 Повторный вызов LLM с результатами календаря...")

                # Обновляем контекст для показа (ручной режим)
                user_prompt_display_context_updated = user_prompt_display_context.copy()
                # История для показа должна включать и запрос календаря, и результаты (которые будут добавлены как system)
                # Поэтому передаем текущую историю + результаты отдельно
                user_prompt_display_context_updated["calendar_search_results"] = calendar_results

                # --- Второй вызов LLM ---
                # Системный промпт тот же, контекст для него тот же
                # История теперь включает user -> assistant (calendar request)
                # Передаем calendar_results для добавления как system message
                # Передаем тот же user_input, т.к. LLM должна обработать исходный запрос В СВЕТЕ результатов календаря
                llm_response_json_str_updated = call_llm_api(
                     system_template=system_prompt_template,
                     system_render_context=system_render_context,
                     user_prompt_display_context=user_prompt_display_context_updated, # Для ручного режима
                     history=conversation_history, # Передаем историю ДО добавления system message
                     current_user_input_for_api=user_input, # Повторяем исходный запрос
                     calendar_results_for_api=calendar_results # Передаем результаты для добавления в messages
                )

                # ИСПРАВЛЕНО: Перемещаем DEBUG-сообщение ПЕРЕД проверкой
                print(f"DEBUG: Получена СТРОКА ВТОРОГО ответа LLM: '{llm_response_json_str_updated}'")

                if not llm_response_json_str_updated:
                     print("Не удалось получить второй ответ от LLM после поиска в календаре.")
                     # Откатываем последнее сообщение ассистента (запрос календаря) из истории,
                     # так как следующий шаг не удался. Пользовательское остается.
                     if conversation_history and conversation_history[-1]['role'] == 'assistant':
                         print("DEBUG: Откат сообщения ассистента (запрос календаря) из истории.")
                         conversation_history.pop()
                     continue # Переходим к следующему запросу пользователя

                # --- Парсинг и Валидация ВТОРОГО ответа ---
                llm_output_updated: Optional[Dict[str, Any]] = None
                try:
                    llm_output_updated = json.loads(llm_response_json_str_updated)
                    print(f"DEBUG: Распарсенный ВТОРОЙ ответ LLM (тип {type(llm_output_updated)}): {llm_output_updated}")

                    if not isinstance(llm_output_updated, dict):
                         raise TypeError(f"Ожидался JSON-объект (словарь) во втором ответе, получен тип {type(llm_output_updated)}")
                    if len(llm_output_updated) != 1:
                         raise ValueError(f"Повторный JSON должен содержать ровно один ключ, получено: {list(llm_output_updated.keys())}")

                    # --- Валидация базовой структуры второго ответа пройдена -> Добавляем ответ в историю ---
                    # Добавляем второй ответ ассистента (первый запрос календаря или второй запрос) в историю
                    conversation_history.append({"role": "assistant", "content": llm_response_json_str_updated})

                    # --- Обработка ВАЛИДНОГО ВТОРОГО ответа ---
                    if "message_to_user" in llm_output_updated:
                        message = llm_output_updated["message_to_user"]
                        if not isinstance(message, str): print(f"Предупреждение: 'message_to_user' (2) содержит не строку: {type(message)}.")
                        print(f"\n🤖 Ответ ассистента (после календаря):\n{message}")
                        # Это финальный ответ для этой итерации

                    elif "prompt_to_llm" in llm_output_updated:
                        actions = llm_output_updated["prompt_to_llm"]
                        if not isinstance(actions, dict):
                             print(f"\n❌ Ошибка: 'prompt_to_llm' содержит не объект JSON: {type(actions)}.")
                             # Откатываем последний assistant ответ
                             if conversation_history and conversation_history[-1]['role'] == 'assistant': conversation_history.pop()
                        else:
                             print("\n✅ LLM сгенерировала финальные действия:")
                             print(json.dumps(actions, indent=2, ensure_ascii=False))
                             # TODO: Здесь можно добавить вызов реального API календаря
                             # Это финальный ответ для этой итерации

                    # --- ИЗМЕНЕНИЕ ЗДЕСЬ: Обработка ПОВТОРНОГО запроса календаря ---
                    elif "calendar" in llm_output_updated:
                         # LLM снова запросила календарь. Дадим ей еще одну попытку.
                         print("\n⚠️ LLM снова запросила календарь (Попытка 2). Выполняем запрос...")
                         calendar_query_2 = llm_output_updated["calendar"] # Получаем второй запрос

                         # Валидация второго запроса календаря
                         if not isinstance(calendar_query_2, str):
                             print(f"\n❌ Ошибка: Повторный ключ 'calendar' содержит не строку: {type(calendar_query_2)}. Невозможно выполнить запрос.")
                             # Откатываем последнее сообщение ассистента (второй запрос календаря)
                             if conversation_history and conversation_history[-1]['role'] == 'assistant': conversation_history.pop()
                             continue # Прерываем эту ветку, переходим к следующему вводу пользователя

                         print(f"   Запрос №2: {calendar_query_2}")

                         # --- Вызов симулятора №2 ---
                         calendar_results_2: Optional[str] = None
                         try:
                             calendar_results_2 = simulate_calendar_lookup(calendar_query_2, mock_calendar_data)
                         except Exception as sim_e_2:
                             print(f"\n❌ Критическая ошибка симулятора календаря (попытка 2): {sim_e_2}")
                             traceback.print_exc()
                             # Откатываем последний assistant ответ (второй запрос календаря)
                             if conversation_history and conversation_history[-1]['role'] == 'assistant': conversation_history.pop()
                             print("Попробуйте переформулировать запрос.")
                             continue # Прерываем эту ветку

                         print("\n🔄 Третий вызов LLM с результатами второго поиска...")

                         # Обновляем контекст для показа (ручной режим) результатами ВТОРОГО поиска
                         user_prompt_display_context_final = user_prompt_display_context_updated.copy()
                         user_prompt_display_context_final["calendar_search_results"] = calendar_results_2 # Результаты второго поиска

                         # --- Третий вызов LLM ---
                         # История теперь включает: user -> assistant(req1) -> assistant(req2)
                         llm_response_json_str_final = call_llm_api(
                              system_template=system_prompt_template,
                              system_render_context=system_render_context,
                              user_prompt_display_context=user_prompt_display_context_final, # Контекст для показа с новыми результатами
                              history=conversation_history, # История включает оба запроса календаря
                              current_user_input_for_api=user_input, # Исходный запрос пользователя все еще актуален
                              calendar_results_for_api=calendar_results_2 # Результаты ВТОРОГО поиска
                         )

                         print(f"DEBUG: Получена СТРОКА ТРЕТЬЕГО ответа LLM: '{llm_response_json_str_final}'")

                         if not llm_response_json_str_final:
                              print("Не удалось получить третий ответ от LLM после второго поиска в календаре.")
                              # Откатываем последнее сообщение ассистента (второй запрос календаря)
                              if conversation_history and conversation_history[-1]['role'] == 'assistant':
                                   print("DEBUG: Откат сообщения ассистента (второй запрос календаря) из истории.")
                                   conversation_history.pop()
                              continue # Прерываем эту ветку

                         # --- Парсинг и Валидация ТРЕТЬЕГО ответа ---
                         llm_output_final: Optional[Dict[str, Any]] = None
                         try:
                             llm_output_final = json.loads(llm_response_json_str_final)
                             print(f"DEBUG: Распарсенный ТРЕТИЙ ответ LLM (тип {type(llm_output_final)}): {llm_output_final}")

                             if not isinstance(llm_output_final, dict):
                                  raise TypeError(f"Ожидался JSON-объект (словарь) в третьем ответе, получен тип {type(llm_output_final)}")
                             if len(llm_output_final) != 1:
                                  raise ValueError(f"Третий JSON должен содержать ровно один ключ, получено: {list(llm_output_final.keys())}")

                             # --- Валидация третьего ответа пройдена -> Добавляем в историю ---
                             conversation_history.append({"role": "assistant", "content": llm_response_json_str_final})

                             # --- Обработка ВАЛИДНОГО ТРЕТЬЕГО ответа ---
                             if "message_to_user" in llm_output_final:
                                 message = llm_output_final["message_to_user"]
                                 if not isinstance(message, str): print(f"Предупреждение: 'message_to_user' (3) содержит не строку: {type(message)}.")
                                 print(f"\n🤖 Ответ ассистента (после второго поиска):\n{message}")
                                 # Финальный ответ
                             elif "prompt_to_llm" in llm_output_final:
                                 actions = llm_output_final["prompt_to_llm"]
                                 if not isinstance(actions, dict):
                                      print(f"\n❌ Ошибка: 'prompt_to_llm' (3) содержит не объект JSON: {type(actions)}.")
                                      if conversation_history and conversation_history[-1]['role'] == 'assistant': conversation_history.pop()
                                 else:
                                      print("\n✅ LLM сгенерировала финальные действия (после второго поиска):")
                                      print(json.dumps(actions, indent=2, ensure_ascii=False))
                                      # TODO: Вызов API календаря
                                      # Финальный ответ
                             elif "calendar" in llm_output_final:
                                  # LLM запросила календарь ТРЕТИЙ раз. Останавливаемся.
                                  print("\n❌ LLM снова запросила календарь (попытка 3). Достигнут лимит попыток.")
                                  print(f"   Запрос: {llm_output_final['calendar']}")
                                  # Откатываем последний (третий) ответ ассистента
                                  if conversation_history and conversation_history[-1]['role'] == 'assistant': conversation_history.pop()
                                  # Переходим к следующему вводу пользователя
                             else:
                                 # Неизвестный ключ в третьем ответе
                                 invalid_key = list(llm_output_final.keys())[0]
                                 print(f"\n❌ Неизвестный ключ в ТРЕТЬЕМ ответе LLM: '{invalid_key}'. Ответ: {llm_output_final}")
                                 if conversation_history and conversation_history[-1]['role'] == 'assistant': conversation_history.pop()
                                 # Переходим к следующему вводу пользователя

                         except (json.JSONDecodeError, ValueError, TypeError) as e_final:
                              # Ошибка парсинга/структуры ТРЕТЬЕГО ответа
                              print(f"\n❌ Ошибка парсинга или структуры ТРЕТЬЕГО JSON ответа LLM: {e_final}")
                              if llm_output_final is not None: print(f"   Получено (распарсенное значение): {llm_output_final}")
                              print(f"   Получено (сырая строка): '{llm_response_json_str_final}'")
                              # Откатываем последний (третий) ответ ассистента, если он был добавлен
                              if conversation_history and conversation_history[-1]['role'] == 'assistant':
                                   if conversation_history[-1]['content'] == llm_response_json_str_final:
                                       print("DEBUG: Откат последнего сообщения assistant из истории из-за ошибки парсинга третьего ответа.")
                                       conversation_history.pop()
                              # Переходим к следующему вводу пользователя

                    # --- Конец обработки второго ответа ---
                    else:
                        # Неизвестный ключ во ВТОРОМ ответе
                        invalid_key = list(llm_output_updated.keys())[0]
                        print(f"\n❌ Неизвестный ключ во ВТОРОМ ответе LLM: '{invalid_key}'. Ответ: {llm_output_updated}")
                        # Откатываем второй ответ ассистента
                        if conversation_history and conversation_history[-1]['role'] == 'assistant':
                            conversation_history.pop() # Удаляем только что добавленный элемент

                except (json.JSONDecodeError, ValueError, TypeError) as e_upd:
                     # Ошибка парсинга/структуры ВТОРОГО ответа
                     print(f"\n❌ Ошибка парсинга или структуры ВТОРОГО JSON ответа LLM: {e_upd}")
                     if llm_output_updated is not None: print(f"   Получено (распарсенное значение): {llm_output_updated}")
                     print(f"   Получено (сырая строка): '{llm_response_json_str_updated}'")
                     # Откатываем последнее сообщение ассистента (второй ответ), если оно было добавлено
                     if conversation_history and conversation_history[-1]['role'] == 'assistant':
                         if conversation_history[-1]['content'] == llm_response_json_str_updated:
                            print("DEBUG: Откат последнего сообщения assistant из истории из-за ошибки парсинга/структуры второго ответа.")
                            conversation_history.pop()
                     # Не откатываем system сообщение или предыдущий assistant (первый запрос календаря)

            elif "prompt_to_llm" in llm_output:
                actions = llm_output["prompt_to_llm"]
                if not isinstance(actions, dict):
                    print(f"\n❌ Ошибка: 'prompt_to_llm' содержит не объект JSON: {type(actions)}.")
                    # Откатываем историю
                    if conversation_history and conversation_history[-1]["role"] == "assistant": conversation_history.pop()
                    if conversation_history and conversation_history[-1]["role"] == "user": conversation_history.pop()
                else:
                    print("\n✅ LLM сгенерировала финальные действия (без поиска в календаре):")
                    print(json.dumps(actions, indent=2, ensure_ascii=False))
                    # Здесь можно добавить вызов реального API календаря

            else:
                # Неизвестный ключ в первом ответе
                invalid_key = list(llm_output.keys())[0]
                print(f"\n❌ Неизвестный или неожиданный ключ в ПЕРВОМ JSON от LLM: '{invalid_key}'. Ответ: {llm_output}")
                # Удаляем некорректные записи из истории (assistant и user)
                if conversation_history and conversation_history[-1]['role'] == 'assistant': conversation_history.pop()
                if conversation_history and conversation_history[-1]['role'] == 'user': conversation_history.pop()


        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"\n❌ Ошибка парсинга или структуры ПЕРВОГО JSON ответа LLM: {e}")
            if llm_output is not None: print(f"   Получено (распарсенное значение): {llm_output}")
            print(f"   Получено (сырая строка): '{llm_response_json_str}'")
            # Не добавляем в историю user и assistant, так как ответ ассистента невалиден

    except KeyboardInterrupt:
        print("\nПрерывание пользователем (Ctrl+C). Завершение работы.")
        break
    except Exception as e: # Ловим другие возможные ошибки в основном цикле
        print(f"\n❌ Непредвиденная ошибка в основном цикле: {e}")
        traceback.print_exc()
        # Опционально: можно попытаться очистить последние записи истории, если ошибка произошла после их добавления
        # Но безопаснее просто сообщить об ошибке и продолжить (или завершить)
        print("Произошла ошибка, попробуйте снова или перезапустите скрипт.")