from fastapi import FastAPI, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from llm_handler import LLMHandler
from calendar_integration import create_calendar_event
import tempfile
import os
from google.oauth2 import id_token
from google.auth.transport import requests

app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

llm = LLMHandler()
CLIENT_ID = "835523232919-o0ilepmg8ev25bu3ve78kdg0smuqp9i8.apps.googleusercontent.com"

@app.post("/process_audio")
async def process_audio(audio: UploadFile, google_token: str = Form(...)):
    try:
        # 1. Проверка Google токена
        id_info = id_token.verify_oauth2_token(google_token, requests.Request(), CLIENT_ID)
        if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise HTTPException(400, detail="Invalid token issuer")

        # 2. Сохранение аудио во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            content = await audio.read()
            if not content:
                raise HTTPException(400, detail="Empty file")
            tmp.write(content)
            tmp_path = tmp.name

        # 3. Распознавание речи (замените на ваш реальный код)
        from speech_to_text import recognize_speech  # Или ваша реализация
        text = recognize_speech(tmp_path)
        os.unlink(tmp_path)  # Удаляем временный файл

        # 4. Обработка через LLM
        event_data = llm.parse_calendar_request(text)  # Анализ текста команд
        if not event_data:
            raise HTTPException(400, detail="Не удалось распознать событие")

        # 5. Создание события в календаре
        create_calendar_event(event_data, google_token)

        return {
            "status": "success",
            "event": event_data,
            "recognized_text": text
        }

    except ValueError as e:
        raise HTTPException(400, detail=f"Ошибка токена: {str(e)}")
    except Exception as e:
        raise HTTPException(500, detail=f"Ошибка сервера: {str(e)}")