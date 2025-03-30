import os
from dotenv import load_dotenv
import argparse
from speech_to_text import recognize_speech
from llm_handler import LLMHandler
from calendar_integration import create_calendar_event
from typing import Optional, Dict

def load_environment():
    """Загружает переменные окружения"""
    dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
    if not os.path.exists(dotenv_path):
        raise FileNotFoundError("Не найден .env файл")
    load_dotenv(dotenv_path)

def validate_event_data(event_data: Optional[Dict]) -> Dict:
    """Проверяет и валидирует данные события"""
    if not event_data:
        raise ValueError("Не удалось разобрать запрос")
    
    required_fields = ['event_name', 'date', 'time']
    for field in required_fields:
        if field not in event_data:
            raise ValueError(f"Отсутствует обязательное поле: {field}")
    
    return event_data

def print_event_details(event_data: Dict):
    """Выводит детали события в консоль"""
    print("\n📅 Извлеченные данные события:")
    print(f"• Название: {event_data['event_name']}")
    print(f"• Дата: {event_data['date']}")
    print(f"• Время: {event_data['time']}")
    print(f"• Относительная дата: {event_data.get('is_relative', False)}")

def main():
    # Инициализация
    load_environment()
    llm_handler = LLMHandler()
    
    # Парсинг аргументов
    parser = argparse.ArgumentParser(description='Голосовой ассистент для календаря')
    parser.add_argument('--audio', 
                       type=str, 
                       help='Путь к аудиофайлу (WAV/OGG)', 
                       required=True)
    parser.add_argument('--test', 
                       action='store_true', 
                       help='Тестовый режим (без создания события)')
    args = parser.parse_args()

    try:
        # 1. Распознавание речи
        print("\n🔊 Распознавание речи...")
        recognized_text = recognize_speech(args.audio)
        print(f"\n📝 Распознанный текст: {recognized_text}")

        # 2. Обработка запроса LLM
        print("\n🧠 Анализ запроса...")
        event_data = llm_handler.parse_calendar_request(recognized_text)
        validated_data = validate_event_data(event_data)
        
        # 3. Вывод деталей
        print_event_details(validated_data)

        # 4. Создание события (если не тестовый режим)
        if not args.test:
            print("\n📅 Создание события в календаре...")
            create_calendar_event(validated_data)
            print("\n✅ Событие успешно создано!")
        else:
            print("\n⚠ Тестовый режим: событие не создано")

    except Exception as e:
        print(f"\n❌ Ошибка: {str(e)}")
        if os.getenv('DEBUG', 'False').lower() == 'true':
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()