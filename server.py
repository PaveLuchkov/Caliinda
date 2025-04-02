from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from llm_handler import LLMHandler
from calendar_integration import create_calendar_event
import tempfile
import os
from google.oauth2 import id_token
from google.auth.transport import requests

app = FastAPI()

# Настройка CORS для работы с Android
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

llm = LLMHandler()

@app.post("/process_audio")
async def process_audio(audio: UploadFile, google_token: str):
    print(f"Received token: {google_token}")
    print(f"Received audio: {audio.filename}, size: {audio.size}")
    try:
        CLIENT_ID = "835523232919-o0ilepmg8ev25bu3ve78kdg0smuqp9i8.apps.googleusercontent.com"
        id_info = id_token.verify_oauth2_token(google_token, requests.Request(), CLIENT_ID)
        if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise HTTPException(400, "Invalid token issuer")
        
        # 1. Сохраняем аудио во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            content = await audio.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        # 2. Распознаем речь (ваш существующий код)
        from speech_to_text import recognize_speech
        text = recognize_speech(tmp_path)
        os.unlink(tmp_path)  # Удаляем временный файл
        
        # 3. Обрабатываем LLM
        event_data = llm.parse_calendar_request(text)
        if not event_data:
            raise HTTPException(400, "Не удалось обработать запрос")
        
        # 4. Создаем событие
        create_calendar_event(event_data, google_token)  # Модифицируем вашу функцию
        
        return {
            "status": "success",
            "event": event_data,
            "recognized_text": text
        }
        
    except Exception as e:
        raise HTTPException(500, str(e))