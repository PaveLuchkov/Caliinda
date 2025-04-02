import json
from openai import OpenAI
import os
from dotenv import load_dotenv
from typing import Optional, Dict
from datetime import datetime

# Загрузка .env файла
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

class LLMHandler:
    def __init__(self):
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key
        )
        self.today = datetime.now().strftime("%Y-%m-%d")
    
    def parse_calendar_request(self, user_text: str) -> Optional[Dict]:
        """
        Анализирует текстовый запрос и извлекает структурированные данные о событии
        
        :param user_text: Текст пользователя (например, "Создай встречу завтра в 15:00")
        :return: Словарь с данными события или None в случае ошибки
        """
        prompt = self._build_prompt(user_text)
        
        try:
            completion = self.client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "http://localhost/calendar-app",
                    "X-Title": "Voice Calendar Assistant",
                },
                model="google/gemini-2.0-flash-001",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            return self._parse_response(completion)
            
        except Exception as e:
            print(f"LLM Error: {str(e)}")
            return None
    
    def _build_prompt(self, user_text: str) -> str:
        """Формирует промпт для LLM"""
        return f"""
        Сегодня {self.today}.
        Пользователь сказал: "{user_text}".
        Извлеки JSON с полями:
        - "event_name" (название встречи, кракто, понятно, календарное название, с первым эмодзи),
        - "date" (дата в формате YYYY-MM-DD),
        - "time" (время в формате HH:MM),
        - "duration" (продолжительность в минутах или null, если не указано),
        - "is_relative" (True, если указано "завтра", "через 2 дня" и т.д.).

        Пример вывода для "Напомни мне про встречу с клиентом завтра в 14:30":
        {{
            "event_name": "Встреча с клиентом",
            "date": "2024-03-31",
            "time": "14:30",
            "duration": null,
            "is_relative": true
        }}

        Пример вывода для "Совещание в пятницу на 90 минут в 10:00":
        {{
            "event_name": "Совещание",
            "date": "2024-04-05",
            "time": "10:00",
            "duration": 90,
            "is_relative": false
        }}
        """
    
    def _parse_response(self, completion) -> dict:
        """Парсит ответ от LLM"""
        result = json.loads(completion.choices[0].message.content)
        
        # Валидация обязательных полей
        required_fields = ['event_name', 'date', 'time', 'duration']
        if not all(field in result for field in required_fields):
            raise ValueError("Не все обязательные поля присутствуют в ответе")
        
        return result

# Пример использования (для тестирования)
if __name__ == "__main__":
    handler = LLMHandler()
    test_input = "Напомни про совещание с отделом маркетинга послезавтра в 11:00"
    
    event_data = handler.parse_calendar_request(test_input)
    if event_data:
        print("Извлеченные данные события:")
        print(f"Название: {event_data.get('event_name')}")
        print(f"Дата: {event_data.get('date')}")
        print(f"Время: {event_data.get('time')}")
        print(f"Относительная дата: {event_data.get('is_relative', False)}")
    else:
        print("Не удалось обработать запрос")