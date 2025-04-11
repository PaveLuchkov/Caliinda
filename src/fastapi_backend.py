# fastapi_backend.py
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import tempfile
import os
import logging
from typing import Dict, List, Optional
import traceback

# Google Auth Libraries
from google.oauth2 import id_token, credentials
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow

# --- Импорт локальных модулей ---
import config # Наш файл конфигурации
from src.database import get_db_session # Функция для получения сессии БД
import src.database as db_utils # Функции для работы с БД (get_user_by_google_id, etc.)
from sqlalchemy.orm import Session # Тип для сессии БД
from src.llm_handler import LLMHandler
from src.calendar_integration import process_and_create_calendar_events
from src.speech_to_text import recognize_speech

# --- Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Audio Calendar Assistant API (Local Dev)")

# --- CORS Configuration (оставляем как есть) ---
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Initialize Handlers ---
llm = LLMHandler()

# --- Helper Functions ---

async def verify_google_id_token(token: str) -> dict:
    """Verifies Google ID Token and returns payload."""
    try:
        # Используем CLIENT_ID из конфига
        id_info = id_token.verify_oauth2_token(
            token, google_requests.Request(), config.GOOGLE_CLIENT_ID
        )
        if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')
        logger.info(f"ID Token verified for user: {id_info.get('email')}")
        return id_info
    except ValueError as e:
        logger.error(f"ID Token verification failed: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid Google ID Token: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during token verification: {e}")
        raise HTTPException(status_code=500, detail="Token verification error")

# --- ЗАВИСИМОСТЬ для получения сессии БД ---
def get_db():
    with get_db_session() as db: # Используем context manager из database.py
        yield db

# --- Переписываем get_credentials_from_refresh_token ---
def get_credentials_from_db_token(user_google_id: str, db: Session) -> Optional[credentials.Credentials]:
    """Retrieves refresh token from DB and builds Credentials object."""
    logger.debug(f"Attempting to get refresh token for user {user_google_id} from DB.")
    refresh_token = db_utils.get_refresh_token(db, user_google_id) # Получаем из БД
    if not refresh_token:
        logger.warning(f"No refresh token found in DB for user ID: {user_google_id}")
        return None

    try:
        # Используем client_id и client_secret из конфига
        creds = credentials.Credentials.from_authorized_user_info(
            info={
                "refresh_token": refresh_token,
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET, # Берем из конфига
                "token_uri": "https://oauth2.googleapis.com/token",
            },
            scopes=config.SCOPES # Используем scopes из конфига
        )
        # Не обязательно явно ставить refresh_token, from_authorized_user_info это делает
        # if not creds.refresh_token:
        #      creds.refresh_token = refresh_token

        logger.info(f"Credentials object created for user ID: {user_google_id} using DB token.")
        return creds
    except Exception as e:
        logger.error(f"Failed to create Credentials object from DB refresh token: {e}", exc_info=True)
        return None

# --- Request Models (остаются как есть) ---
class TokenExchangeRequest(BaseModel):
    id_token: str
    auth_code: str

# --- API Endpoints ---

@app.post("/auth/google/exchange", tags=["Authentication"])
async def auth_google_exchange(payload: TokenExchangeRequest, db: Session = Depends(get_db)): # Добавляем Depends(get_db)
    logger.info("Received request for /auth/google/exchange")
    try:
        # 1. Верификация ID токена
        id_info = await verify_google_id_token(payload.id_token)
        user_google_id = id_info.get('sub')
        if not user_google_id:
            raise HTTPException(status_code=400, detail="Could not get user ID from token.")
        user_email = id_info.get('email')
        user_full_name = id_info.get('name')
        logger.info(f"Token exchange request authenticated for user: {user_email} (ID: {user_google_id})")

        # 2. Обмен кода авторизации на токены
        # Конфигурация для Flow БЕЗ файла секрета
        client_config = {
            "web": {
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                # ВАЖНО: Укажи redirect_uri, который ты добавишь в Google Cloud Console для ЛОКАЛЬНОЙ разработки
                # Это может быть просто localhost:порт, если твой фронтенд его использует, или 'postmessage'
                # Пример для случая, когда фронт работает локально и шлет код сюда:
                "redirect_uris": ["http://localhost:8080", "postmessage"], # Добавь свои варианты
            }
        }
        # Выбери ПРАВИЛЬНЫЙ redirect_uri, который будет использоваться!
        # Если не уверен, начни с 'postmessage' или того, что настроено в GCP.
        chosen_redirect_uri = 'http://localhost:8080' # Или client_config["web"]["redirect_uris"][0]

        flow = Flow.from_client_config(
            client_config=client_config,
            scopes=config.SCOPES,
            redirect_uri=chosen_redirect_uri
        )

        logger.info(f"Attempting to fetch token using auth code for user: {user_email} with redirect_uri: {chosen_redirect_uri}")
        flow.fetch_token(code=payload.auth_code)

        credentials_result = flow.credentials
        if not credentials_result or not credentials_result.refresh_token:
            logger.error("Failed to obtain refresh token from Google.")
            raise HTTPException(status_code=400, detail="Could not obtain refresh token from Google.")

        refresh_token = credentials_result.refresh_token

        # --- Сохранение в БД ---
        db_utils.upsert_user_token(
            db_session=db,
            google_id=user_google_id,
            email=user_email,
            full_name=user_full_name,
            refresh_token=refresh_token
        )
        logger.info(f"Successfully obtained and stored refresh token in LOCAL DB for user: {user_email} (ID: {user_google_id})")

        return {
            "status": "success",
            "message": "Authorization successful (Local). Calendar access granted.",
            "user_email": user_email
        }

    except HTTPException as e:
        raise e # Перебрасываем HTTP исключения
    except Exception as e:
        logger.error(f"Error exchanging auth code: {e}", exc_info=True)
        # Возможно, стоит проверить детали ошибки 'invalid_grant' - часто из-за неверного redirect_uri или уже использованного кода
        detail = f"Failed to exchange Google auth code: {e}"
        if "invalid_grant" in str(e):
             detail += " (Check if redirect_uri matches Google Console setup or if the code was already used)"
        raise HTTPException(status_code=500, detail=detail)


# --- Хранилище Состояния Диалога (остается in-memory для локальной разработки) ---
class ConversationState(BaseModel):
    stage: str = "start"
    initial_request_text: Optional[str] = None
    classification: Optional[str] = None
    extracted_event_data: Optional[Dict] = None
    last_clarification_question: Optional[str] = None
    error_message: Optional[str] = None

user_conversation_state: Dict[str, ConversationState] = {}

def clear_conversation_state(user_google_id: str):
    if user_google_id in user_conversation_state:
        del user_conversation_state[user_google_id]
        logger.info(f"Cleared conversation state for user {user_google_id}")

# --- Эндпоинт /process ---
@app.post("/process", tags=["Core Logic"])
async def process_unified_request(
    id_token_str: str = Form(...),
    text: Optional[str] = Form(None),
    audio: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db) # Добавляем зависимость от БД
):
    logger.info("Received request for /process")
    temp_audio_path: Optional[str] = None
    try:
        # 1. Аутентификация (как раньше, использует GOOGLE_CLIENT_ID из конфига)
        id_info = await verify_google_id_token(id_token_str)
        user_google_id = id_info.get('sub')
        user_email = id_info.get('email')
        if not user_google_id:
            raise HTTPException(status_code=401, detail="Could not get user ID from token.")
        logger.info(f"Processing request authenticated for user: {user_email} (ID: {user_google_id})")

        # 2. Получение текста (аудио или текст) - как раньше
        input_text: Optional[str] = None
        if audio:
            # ... (код обработки аудио файла и вызов recognize_speech)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
                content = await audio.read()
                if not content: raise HTTPException(status_code=400, detail="Empty audio file received.")
                tmp.write(content)
                temp_audio_path = tmp.name
            recognized_text = recognize_speech(temp_audio_path) # Предполагаем, что она есть
            if not recognized_text or recognized_text.isspace():
                raise HTTPException(status_code=400, detail="Could not recognize speech.")
            input_text = recognized_text
            logger.info(f"Recognized text: '{input_text}'")
        elif text:
            input_text = text
        else:
            raise HTTPException(status_code=400, detail="No text or audio input provided.")
        if not input_text or input_text.isspace():
             raise HTTPException(status_code=400, detail="Input processing resulted in empty text.")

        # 3. Управление состоянием диалога и конвейер LLM (как раньше, использует user_conversation_state)
        state = user_conversation_state.get(user_google_id, ConversationState(stage="start"))
        logger.info(f"Current conversation stage for user {user_google_id}: {state.stage}")

        # --- Логика стадий диалога (start, classified, awaiting_clarification) ---

        # --- Обработка в зависимости от стадии ---
        if state.stage == "start":
            # --- Этап 1: Классификация ---
            classification_result = llm.classify_intent(input_text)
            if not classification_result or "error" in classification_result:
                 error_detail = classification_result.get("error", "Unknown classification error") if classification_result else "LLM Classification call failed"
                 state.stage = "error"
                 state.error_message = f"Classification failed: {error_detail}"
                 logger.error(state.error_message + f" Raw Response: {classification_result.get('raw_response') if classification_result else 'N/A'}")
                 # Не бросаем исключение, а переходим к возврату ответа об ошибке
            else:
                state.classification = classification_result.get("classification")
                state.initial_request_text = input_text
                state.stage = "classified"
                logger.info(f"Intent classified as '{state.classification}'. Moving to next stage.")

        # Переход к следующему этапу возможен сразу после предыдущего, если не было ошибки
        if state.stage == "classified":
            if state.classification == "add":
                # --- Этап 2: Извлечение деталей ---
                logger.info("Proceeding to event detail extraction.")
                extraction_result = llm.extract_event_details(state.initial_request_text)
                state.extracted_event_data = extraction_result

                if not extraction_result or "error" in extraction_result:
                    error_detail = extraction_result.get("error", "Unknown extraction error") if extraction_result else "LLM Extraction call failed"
                    state.stage = "error"
                    state.error_message = f"Event extraction failed: {error_detail}"
                    logger.error(state.error_message + f" Raw Response: {extraction_result.get('raw_response') if extraction_result else 'N/A'}")
                elif extraction_result.get("clarification_needed"):
                    state.stage = "awaiting_clarification"
                    state.last_clarification_question = extraction_result.get("message")
                    logger.info("Clarification needed. Question: " + (state.last_clarification_question or "No question provided"))
                else:
                    state.stage = "finalizing"
                    logger.info("Extraction complete, no clarification needed. Moving to finalizing.")
            else:
                logger.info(f"Handling non-'add' classification: {state.classification}")
                clear_conversation_state(user_google_id)
                return {"status": "info", "message": f"Sorry, I can only help with adding events right now (Intent: {state.classification})."}

        elif state.stage == "awaiting_clarification":
            # --- Этап 3: Уточнение ---
            logger.info("Processing user answer for clarification.")
            if not state.extracted_event_data or not state.last_clarification_question or not state.initial_request_text:
                 state.stage = "error"; state.error_message = "Internal state error during clarification."
                 logger.error(state.error_message)
                 # Переходим к возврату ошибки
            else:
                user_answer = input_text # Текущий ввод - это ответ
                clarification_result = llm.clarify_event_details(
                    initial_request=state.initial_request_text,
                    current_event_data=state.extracted_event_data,
                    question_asked=state.last_clarification_question,
                    user_answer=user_answer
                )
                state.extracted_event_data = clarification_result # Обновляем, даже если ошибка

                if not clarification_result or "error" in clarification_result:
                    error_detail = clarification_result.get("error", "Unknown clarification error") if clarification_result else "LLM Clarification call failed"
                    state.stage = "error"
                    state.error_message = f"Clarification failed: {error_detail}"
                    logger.error(state.error_message + f" Raw Response: {clarification_result.get('raw_response') if clarification_result else 'N/A'}")
                elif clarification_result.get("clarification_needed"):
                     state.stage = "awaiting_clarification" # Снова нужно уточнение
                     state.last_clarification_question = clarification_result.get("message")
                     logger.info("Further clarification needed. New Question: " + (state.last_clarification_question or "No question provided"))
                else:
                     state.stage = "finalizing" # Уточнение успешно
                     state.last_clarification_question = None
                     logger.info("Clarification complete. Moving to finalizing.")


        # --- Внутри логики стадий диалога (если stage == "classified" или "awaiting_clarification" привел к успеху) ---
        # --- Мы доходим до момента, когда state.stage становится "finalizing" ---

         # --- Сохраняем обновленное состояние (если не было критической ошибки ДО этого момента) ---
        if state.stage != "error":
            user_conversation_state[user_google_id] = state
            logger.info(f"Saved updated state for user {user_google_id}: Stage={state.stage}")
        else:
            logger.info(f"Not saving state for user {user_google_id} due to error stage.")

        # --- Финальная обработка или возврат ответа ---
        if state.stage == "finalizing":
            logger.info(f"Executing final event creation stage for user {user_email}.")

            # --- Получение Учетных Данных из БД ---
            creds = get_credentials_from_db_token(user_google_id, db) # Используем новую функцию
            if not creds:
                clear_conversation_state(user_google_id)
                logger.warning(f"Credentials missing for user {user_email} (ID: {user_google_id}), requiring re-auth.")
                raise HTTPException(status_code=401, detail="User authorization required or expired. Please sign in again.")

            final_llm_data = state.extracted_event_data
            if not final_llm_data or not isinstance(final_llm_data.get("event"), list):
                clear_conversation_state(user_google_id)
                logger.error(f"Internal error: Final LLM data for user {user_email} is missing or invalid.")
                raise HTTPException(status_code=500, detail="Internal error: Event data missing or invalid before creation.")

            # --- Вызов функции создания событий (calendar_integration.py) ---
            try:
                # Передаем полученные creds
                created_events: List[Dict] = process_and_create_calendar_events(final_llm_data, creds)

                clear_conversation_state(user_google_id) # Очищаем состояние после попытки

                # --- Формирование ответа (как раньше) ---
                if not created_events:
                     return {"status": "info", "message": "I couldn't create any events..."}
                elif len(created_events) == 1:
                     event_info = created_events[0]
                     return {
                        "status": "success",
                        "message": "Event created successfully!",
                        "event": {
                            "event_name": event_info.get("summary"),
                            "start_time": event_info.get("start", {}).get("dateTime"),
                            "end_time": event_info.get("end", {}).get("dateTime"),
                        },
                        "event_link": event_info.get("htmlLink"),
                    }
                else:
                    # --- Успешно создано НЕСКОЛЬКО событий ---
                    logger.info(f"Successfully created {len(created_events)} events for user {user_email}.")
                    event_summaries = [ev.get("summary", "Unnamed Event") for ev in created_events]
                    # Формируем сообщение для пользователя
                    message = f"{len(created_events)} events created: " + ", ".join(event_summaries)
                    return {
                        "status": "success",
                        "message": message,
                        "events_created": event_summaries, # Список названий
                        "first_event_link": created_events[0].get("htmlLink") # Ссылка на первое для примера
                    }


            except Exception as final_ex:
                logger.error(f"Exception during final event creation stage for user {user_email}: {final_ex}\n{traceback.format_exc()}")
                clear_conversation_state(user_google_id)
                if "refresh" in str(final_ex).lower(): # Ошибка рефреша
                     raise HTTPException(status_code=401, detail=f"Authorization failed: {final_ex}")
                else:
                     raise HTTPException(status_code=500, detail=f"Failed to process event creation: {final_ex}")

        elif state.stage == "awaiting_clarification":
             # Возвращаем уточняющий вопрос
             return {
                 "status": "clarification_needed",
                 "message": state.last_clarification_question or "Could you please provide more details?"
             }
        elif state.stage == "error":
             # Возвращаем сообщение об ошибке LLM
             error_msg = state.error_message or "An unknown processing error occurred."
             clear_conversation_state(user_google_id)
             return {"status": "error", "message": error_msg}
        else: # Неожиданное состояние
             clear_conversation_state(user_google_id)
             logger.error(f"Reached unexpected state '{state.stage}' for user {user_google_id}")
             raise HTTPException(status_code=500, detail="Internal server error: Unexpected conversation state.")

    except HTTPException as http_ex:
        logger.warning(f"Caught HTTPException: {http_ex.status_code} - {http_ex.detail}", exc_info=True)
        raise http_ex # Перебрасываем HTTP ошибки
    except Exception as final_ex:
        logger.error(f"Unhandled exception during processing for user {user_google_id}: {final_ex}\n{traceback.format_exc()}")
        clear_conversation_state(user_google_id) # Очищаем состояние при неизвестной ошибке
        raise HTTPException(status_code=500, detail=f"An unexpected internal error occurred: {final_ex}")
    finally:
        # Очистка временного аудиофайла (как раньше)
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.unlink(temp_audio_path)
                logger.info(f"Deleted temporary audio file: {temp_audio_path}")
            except Exception as e:
                logger.error(f"Error deleting temporary file {temp_audio_path}: {e}")

# --- Root endpoint for testing ---
@app.get("/", tags=["Status"])
async def root():
    return {"message": "Audio Calendar Assistant Backend is running locally!"}

# --- Код для запуска uvicorn (если запускаешь скрипт напрямую) ---
# if __name__ == "__main__":
#     import uvicorn
#     logger.info("Starting Uvicorn server locally...")
#     # Важно: загрузка .env должна произойти до инициализации конфига и движка БД
#     # У нас это сделано в config.py, который импортируется выше
#     uvicorn.run(app, host="0.0.0.0", port=8000, reload=True) # Используй reload для разработки