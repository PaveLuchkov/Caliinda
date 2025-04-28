import json
from datetime import datetime
import os # Для API ключа

# --- Настройки ---
YOUR_LLM_API_KEY = os.getenv("OPENROUTER_API_KEY") # Или ваш ключ к другой LLM
LLM_API_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions" # Пример для OpenAI
LLM_MODEL = "google/gemini-2.0-flash-001" # Или другая модель
USE_API = True # Поставьте True, если используете API, False для ручного ввода

# --- Загрузка Промпта ---
# Лучше вынести промпт в отдельный файл prompt.template
try:
    with open("src/prompt.template", "r", encoding="utf-8") as f:
        prompt_template = f.read()
except FileNotFoundError:
    print("Ошибка: Файл prompt.template не найден. Использую встроенный.")
    # Ваш промпт здесь как запасной вариант
    
# --- Мок Данные Календаря ---
# (Вставьте mock_calendar_data и функцию simulate_calendar_lookup сюда)
mock_calendar_data = [
    {
        "id": "event1_today_morning",
        "summary": "Утренний Стендап",
        "start": "2023-11-15T09:00:00", # Замените на актуальные даты для тестов
        "end": "2023-11-15T09:30:00"
    },
    {
        "id": "event2_today_afternoon",
        "summary": "Встреча с Дизайнером",
        "start": "2023-11-15T14:00:00",
        "end": "2023-11-15T15:30:00",
        "description": "Обсудить новый макет",
        "attendees": ["designer@example.com"]
    },
    {
        "id": "event3_tomorrow",
        "summary": "Поход к Врачу",
        "start": "2023-11-16T11:00:00",
        "end": "2023-11-16T12:00:00",
        "location": "Клиника 'Здоровье'"
    },
    {
        "id": "event4_conflict_check",
        "summary": "Существующее событие",
        "start": "2023-11-16T15:00:00", # Используем для теста конфликта
        "end": "2023-11-16T16:00:00"
    }
]

import re
from datetime import datetime, timedelta

def parse_calendar_query(query_string):
    """Парсит строку запроса на timeMin и timeMax."""
    time_min_match = re.search(r'timeMin:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', query_string)
    time_max_match = re.search(r'timeMax:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', query_string)
    
    time_min = time_min_match.group(1) if time_min_match else None
    time_max = time_max_match.group(1) if time_max_match else None
    
    keywords = []
    text_part = re.sub(r'time(Min|Max):\s*\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2},?\s*', '', query_string).strip()
    if text_part:
         # Убираем возможные остатки типа ", " или просто " "
         text_part = re.sub(r'^,\s*', '', text_part).strip()
         if text_part:
             keywords = text_part.lower().split()
         
    return time_min, time_max, keywords

def simulate_calendar_lookup(query_string, mock_data):
    """Симулирует поиск в календаре по строке запроса."""
    time_min_str, time_max_str, keywords = parse_calendar_query(query_string)
    
    print(f"\n[Симулятор Календаря] Получен запрос: '{query_string}'")
    print(f"[Симулятор Календаря] Распарсено: timeMin={time_min_str}, timeMax={time_max_str}, keywords={keywords}")
    
    results = []
    
    try:
        time_min_dt = datetime.fromisoformat(time_min_str) if time_min_str else None
        time_max_dt = datetime.fromisoformat(time_max_str) if time_max_str else None
    except ValueError:
        print(f"[Симулятор Календаря] Ошибка парсинга даты в запросе.")
        return "..." 

    # Логика поиска: сначала по времени, потом фильтрация по словам ИЛИ только по словам, если нет времени
    
    filtered_by_time = []
    if time_min_dt and time_max_dt:
         for event in mock_data:
            try:
                event_start_dt = datetime.fromisoformat(event['start'])
                event_end_dt = datetime.fromisoformat(event['end'])
                # (StartA < EndB) and (EndA > StartB)
                if event_start_dt < time_max_dt and event_end_dt > time_min_dt:
                    filtered_by_time.append(event)
            except ValueError:
                print(f"[Симулятор Календаря] Ошибка парсинга даты в мок-данных: {event}")
                continue
    elif not keywords: # Если нет ни времени, ни слов - ничего не ищем
         print("[Симулятор Календаря] Запрос без диапазона времени и без ключевых слов.")
         return "..."
    else: # Если нет времени, но есть слова - ищем по всей базе
        filtered_by_time = mock_data


    # Теперь фильтруем (или не фильтруем, если слов нет) по ключевым словам
    if keywords:
        for event in filtered_by_time:
             summary_lower = event.get('summary', '').lower()
             description_lower = event.get('description', '').lower()
             location_lower = event.get('location', '').lower()
             # Проверяем, что *все* ключевые слова есть где-то в полях события
             # ИЛИ можно сделать чтобы *хотя бы одно* слово было (any вместо all) - зависит от желаемой логики
             # if any(kw in summary_lower or kw in description_lower or kw in location_lower for kw in keywords): 
             # Используем all для более строгого поиска:
             all_keywords_found = True
             for kw in keywords:
                 if not (kw in summary_lower or kw in description_lower or kw in location_lower):
                      all_keywords_found = False
                      break
             if all_keywords_found:
                results.append(event)

    else: # Если ключевых слов не было, то результат - это все, что подошло по времени
        results = filtered_by_time

    if not results:
        print("[Симулятор Календаря] Событий не найдено.")
        return "..."
    else:
        output_lines = []
        for event in results:
            line = f"EventID: {event['id']}; Summary: {event.get('summary', 'N/A')}; Time: {event['start']} - {event['end']}"
            if event.get('description'):
                line += f"; Description: {event.get('description')}"
            if event.get('location'):
                line += f"; Location: {event.get('location')}"
            if event.get('attendees'):
                 line += f"; Attendees: {','.join(event.get('attendees'))}"
            output_lines.append(line)
        result_str = "\n".join(output_lines)
        print(f"[Симулятор Календаря] Найденные события:\n{result_str}")
        return result_str
# -----------------------------

def call_llm_api(full_prompt, history_for_api, last_user_input_for_api): # <- Добавили аргументы
    """Вызывает LLM API (пример для OpenAI)."""
    if not USE_API:
        print("\n--- ПРОМПТ ДЛЯ LLM ---")
        print(full_prompt)
        print("--- КОНЕЦ ПРОМПТА ---")
        llm_response_json = input("Скопируйте промпт выше, вставьте в LLM, и введите сюда JSON-ответ модели:\n> ")
        return llm_response_json.strip()

    import requests # Потребуется установить: pip install requests

    headers = {
        "Authorization": f"Bearer {YOUR_LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    # Формируем запрос для Chat Completion API
    # Важно: передаем весь промпт как одну system-инструкцию или user-сообщение
    # Но лучше следовать структуре Chat API: system prompt + user messages
    # В нашем случае, промпт уже включает историю, так что можно отправить его как user message.
    # Либо можно распарсить history из шаблона и передать правильно.
    # Здесь упрощенный вариант - весь шаблон как одно сообщение. Модели обычно справляются.
    
    # Попробуем распарсить history для более корректного формата Chat API
    history_entries = []
    history_section_match = re.search(r'Conversation History:\s*```\s*(.*?)\s*```', full_prompt, re.DOTALL)
    last_user_input_match = re.search(r'Current User Request: `(.*?)`', full_prompt, re.DOTALL)
    
    system_prompt_part = full_prompt.split('Conversation History:')[0].strip() # Все до истории
    
    if history_section_match:
        history_text = history_section_match.group(1).strip()
        for line in history_text.splitlines():
             if line.strip():
                role, content = line.split(":", 1)
                history_entries.append({"role": role.lower().strip(), "content": content.strip()})

    if last_user_input_match:
         last_user_input = last_user_input_match.group(1).strip()
         # Добавляем последнее сообщение пользователя в конец истории
         history_entries.append({"role": "user", "content": last_user_input})

    messages = [{"role": "system", "content": system_prompt_part}] + history_entries
    
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": 0.5, # Можно настроить
        "max_tokens": 300,  # Можно настроить
        "response_format": {"type": "json_object"} # Требуем JSON (если модель поддерживает)
    }

    print("\n[API] Отправка запроса к LLM...")
    # print(json.dumps(payload, indent=2, ensure_ascii=False)) # Раскомментировать для отладки запроса

    try:
        response = requests.post(LLM_API_ENDPOINT, headers=headers, json=payload, timeout=60)
        response.raise_for_status() # Вызовет исключение для HTTP ошибок 4xx/5xx
        
        response_data = response.json()
        # print("[API] Ответ получен:") # Раскомментировать для отладки
        # print(json.dumps(response_data, indent=2, ensure_ascii=False)) # Раскомментировать для отладки
        
        llm_output = response_data['choices'][0]['message']['content']
        print("[API] Ответ LLM получен.")
        return llm_output.strip()

    except requests.exceptions.RequestException as e:
        print(f"[API Ошибка] Не удалось получить ответ от LLM: {e}")
        if hasattr(e, 'response') and e.response is not None:
             print(f"[API Ошибка] Тело ответа: {e.response.text}")
        return None
    except (KeyError, IndexError) as e:
        print(f"[API Ошибка] Неожиданный формат ответа от LLM: {e}")
        print(f"[API Ошибка] Полный ответ: {response_data}")
        return None


def format_prompt(template, history, user_input, current_time_iso, temper="helpful and efficient assistant"):
    """Форматирует промпт с использованием Jinja2-подобного синтаксиса."""
    
    # Базовая замена без Jinja2 для простоты
    formatted_template = template.replace("{{temper}}", temper)
    formatted_template = formatted_template.replace("{{UserDateTime}}", current_time_iso)
    formatted_template = formatted_template.replace("{{user_input}}", user_input) # Заменяем оба вхождения

    # Формируем историю
    history_str = ""
    for msg in history:
        history_str += f"{msg['role']}: {msg['content']}\n"
        
    # Ищем место для вставки истории (между ```)
    start_marker = "{% for msg in history %}"
    end_marker = "{% endfor %}"
    start_index = formatted_template.find(start_marker)
    end_index = formatted_template.find(end_marker)

    if start_index != -1 and end_index != -1:
         # Заменяем блок истории на отформатированную строку
         formatted_template = formatted_template[:start_index] + history_str.strip() + formatted_template[end_index + len(end_marker):]
    else:
         # Если маркеры не найдены (мало ли), просто добавим в конец (менее идеально)
         formatted_template += "\nConversation History:\n```\n" + history_str.strip() + "\n```"

    return formatted_template

# --- Основной Цикл ---
conversation_history = []
current_temper = "дружелюбный и эффективный" 

while True:
    user_input = input("\nВаш запрос (или 'выход' для завершения):\n> ")
    if user_input.lower() == 'выход':
        break

    current_time = datetime.now()
    current_time_iso = current_time.strftime('%Y-%m-%dT%H:%M:%S') 

    # Формируем промпт
    full_prompt = format_prompt(prompt_template, conversation_history, user_input, current_time_iso, current_temper)
    
    # Готовим данные для API 
    history_for_api_call = [msg for msg in conversation_history] 
    last_user_input_for_api_call = user_input

    # Получаем ответ от LLM
    llm_response_json_str = call_llm_api(full_prompt, history_for_api_call, last_user_input_for_api_call) 

    if not llm_response_json_str:
        print("Не удалось получить ответ от LLM (API вернуло None или пустую строку). Попробуйте снова.")
        continue

    # Этап 3: Парсим и ВАЛИДИРУЕМ ответ LLM
    llm_output = None # Инициализируем на случай ошибки парсинга
    try:
        print(f"DEBUG: Строка ответа LLM перед парсингом: '{llm_response_json_str}'") # Отладка: показать сырой ответ
        llm_output = json.loads(llm_response_json_str)
        
        # --- ВАЛИДАЦИЯ СТРУКТУРЫ ---
        print(f"DEBUG: Распарсенный ответ LLM (тип {type(llm_output)}): {llm_output}") # Отладка: показать распарсенный ответ и его тип

        # 1. Проверяем, что это СЛОВАРЬ
        if not isinstance(llm_output, dict):
            # Если это не словарь (например, список), вызываем ошибку структуры
            raise TypeError(f"Ожидался JSON-объект (словарь), получен тип {type(llm_output)}")

        # 2. Проверяем, что в словаре РОВНО ОДИН ключ
        if len(llm_output) != 1:
            raise ValueError(f"JSON должен содержать ровно один ключ, получено: {list(llm_output.keys())}")
        
        # --- Валидация пройдена ---

        # Добавляем запрос пользователя и ВАЛИДНЫЙ ответ LLM в историю
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": llm_response_json_str}) 

        # Этап 4: Обрабатываем ВАЛИДНЫЙ ответ
        if "message_to_user" in llm_output:
            message = llm_output["message_to_user"]
            print(f"\n🤖 Ответ ассистента:\n{message}")

        elif "calendar" in llm_output:
            calendar_query = llm_output["calendar"]
            print(f"\n⚙️ LLM запросила календарь: {calendar_query}")
            
            # Симуляция календаря и повторный вызов LLM
            calendar_results = simulate_calendar_lookup(calendar_query, mock_calendar_data)
            system_message = {"role": "system", "content": calendar_results}
            conversation_history.append(system_message)
            print(f"Добавлено в историю как system:\n{calendar_results}")

            print("\n🔄 Повторный вызов LLM с результатами календаря...")
            history_for_api_call_updated = [msg for msg in conversation_history]
            last_user_input_for_api_call_updated = user_input 
            full_prompt_updated = format_prompt(prompt_template, conversation_history, user_input, current_time_iso, current_temper)
            llm_response_json_str_updated = call_llm_api(full_prompt_updated, history_for_api_call_updated, last_user_input_for_api_call_updated)

            if not llm_response_json_str_updated:
                 print("Не удалось получить второй ответ от LLM.")
                 if conversation_history and conversation_history[-1]['role'] == 'system':
                     conversation_history.pop() # Откатить system message
                 continue

            # Парсим и ВАЛИДИРУЕМ ВТОРОЙ ответ
            llm_output_updated = None
            try:
                print(f"DEBUG: Строка ВТОРОГО ответа LLM перед парсингом: '{llm_response_json_str_updated}'")
                llm_output_updated = json.loads(llm_response_json_str_updated)
                print(f"DEBUG: Распарсенный ВТОРОЙ ответ LLM (тип {type(llm_output_updated)}): {llm_output_updated}")

                if not isinstance(llm_output_updated, dict):
                     raise TypeError(f"Ожидался JSON-объект (словарь) во втором ответе, получен тип {type(llm_output_updated)}")
                if len(llm_output_updated) != 1:
                     raise ValueError(f"Повторный JSON должен содержать ровно один ключ, получено: {list(llm_output_updated.keys())}")

                # Заменяем предыдущий assistant ответ на новый
                if len(conversation_history) >= 2 and conversation_history[-2]['role'] == 'assistant':
                     conversation_history[-2]['content'] = llm_response_json_str_updated
                else: # На всякий случай, если что-то пошло не так с историей
                     conversation_history.append({"role": "assistant", "content": llm_response_json_str_updated})

                # Обрабатываем ВАЛИДНЫЙ ВТОРОЙ ответ
                if "message_to_user" in llm_output_updated:
                    message = llm_output_updated["message_to_user"]
                    print(f"\n🤖 Ответ ассистента (после календаря):\n{message}")
                elif "prompt_to_llm" in llm_output_updated:
                    actions = llm_output_updated["prompt_to_llm"]
                    print("\n✅ LLM сгенерировала финальные действия:")
                    print(json.dumps(actions, indent=2, ensure_ascii=False))
                elif "calendar" in llm_output_updated:
                     print("\n⚠️ LLM снова запросила календарь после получения результатов. Проверьте логику промпта.")
                     print(f"   Запрос: {llm_output_updated['calendar']}")
                else:
                    invalid_key = list(llm_output_updated.keys())[0]
                    print(f"\n❌ Неизвестный ключ во ВТОРОМ ответе LLM: '{invalid_key}'")
                    print(f"   Полный ответ: {llm_output_updated}")

            # Ошибки парсинга/структуры ВТОРОГО ответа
            except (json.JSONDecodeError, ValueError, TypeError) as e_upd:
                 print(f"\n❌ Ошибка парсинга или структуры ВТОРОГО JSON ответа LLM: {e_upd}")
                 # Выводим и распарсенное значение (если есть) и сырую строку
                 if llm_output_updated is not None:
                     print(f"   Получено (распарсенное значение): {llm_output_updated}")
                 print(f"   Получено (сырая строка): '{llm_response_json_str_updated}'")
                 # Откатываем system message
                 if conversation_history and conversation_history[-1]['role'] == 'system':
                      conversation_history.pop()

        elif "prompt_to_llm" in llm_output:
            actions = llm_output["prompt_to_llm"]
            print("\n✅ LLM сгенерировала финальные действия:")
            print(json.dumps(actions, indent=2, ensure_ascii=False))

        else:
            # Сюда попадаем, если это словарь с одним ключом, но ключ НЕ message_to_user, calendar или prompt_to_llm
            invalid_key = list(llm_output.keys())[0] # Теперь безопасно
            print(f"\n❌ Неизвестный или неожиданный ключ в JSON от LLM: '{invalid_key}'")
            print(f"   Полный ответ: {llm_output}") # Показываем словарь
            # Удаляем некорректные записи из истории
            if conversation_history and conversation_history[-1]['role'] == 'assistant':
                conversation_history.pop()
            if conversation_history and conversation_history[-1]['role'] == 'user':
                conversation_history.pop()

    # Ошибки парсинга/структуры ПЕРВОГО ответа
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        print(f"\n❌ Ошибка парсинга или структуры JSON ответа LLM: {e}")
        # Выводим и распарсенное значение (если есть) и сырую строку
        if llm_output is not None: # Если json.loads() успел что-то вернуть до ошибки типа/структуры
             print(f"   Получено (распарсенное значение): {llm_output}")
        print(f"   Получено (сырая строка): '{llm_response_json_str}'")
        # Не добавляем ничего в историю
        pass