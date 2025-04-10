# fastapi_backend.py
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field # For request body models
import tempfile
import os
import logging
from typing import Dict, List, Optional
import traceback

# Google Auth Libraries
from google.oauth2 import id_token, credentials # Correct import for Credentials
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow # For exchanging the auth code

# Your existing imports
from src.llm_handler import LLMHandler # Assuming this exists and works
from src.calendar_integration import process_and_create_calendar_events
from src.speech_to_text import recognize_speech # Assuming this exists and works

# --- Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Audio Calendar Assistant API")

CLIENT_SECRETS_FILE = os.environ.get("GOOGLE_CLIENT_SECRETS", "client_secret.json")

BACKEND_WEB_CLIENT_ID = "835523232919-o0ilepmg8ev25bu3ve78kdg0smuqp9i8.apps.googleusercontent.com" # From your Android code

SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'openid',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/userinfo.email'
]

# --- CORS Configuration ---
# Adjust origins as needed for production
origins = [
    "*", # Allows all origins - BE CAREFUL in production
    # "http://localhost", # Example for local development if serving a web UI
    # "https://your-app-domain.com", # Example for production
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, etc.)
    allow_headers=["*"], # Allows all headers
)

# --- In-Memory Storage for Refresh Tokens (DEMO ONLY) ---
# !!! WARNING: Use a proper database (SQL, NoSQL) in production !!!
# Store mapping: user_google_id (sub) -> refresh_token
# This is NOT persistent and will be lost on server restart.
user_refresh_tokens: Dict[str, str] = {}

# --- Initialize Handlers ---
llm = LLMHandler()

# --- Helper Functions ---

async def verify_google_id_token(token: str) -> dict:
    """Verifies Google ID Token and returns payload."""
    try:
        # Specify the CLIENT_ID of your backend web application here.
        id_info = id_token.verify_oauth2_token(
            token, google_requests.Request(), BACKEND_WEB_CLIENT_ID
        )
        # Verify issuer
        if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')

        # ID token is valid. Return the payload.
        # Contains 'sub' (user ID), 'email', 'name', etc.
        logger.info(f"ID Token verified for user: {id_info.get('email')}")
        return id_info
    except ValueError as e:
        logger.error(f"ID Token verification failed: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid Google ID Token: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during token verification: {e}")
        raise HTTPException(status_code=500, detail="Token verification error")


def get_credentials_from_refresh_token(user_google_id: str) -> Optional[credentials.Credentials]:
    """Retrieves refresh token and builds Credentials object."""
    refresh_token = user_refresh_tokens.get(user_google_id)
    if not refresh_token:
        logger.warning(f"No refresh token found for user ID: {user_google_id}")
        return None

    try:
        creds = credentials.Credentials.from_authorized_user_info(
            info={
                 # We only strictly need the refresh token here for the object
                 # Client ID/Secret will be fetched from the secrets file implicitly by the library later if needed for refresh
                 "refresh_token": refresh_token,
                 # The following are needed if you use from_authorized_user_info directly
                 # If using Flow object later, it might handle this better.
                 # Load client_id and client_secret securely
                 "client_id": BACKEND_WEB_CLIENT_ID, # Make sure this is correct
                 "client_secret": get_client_secret(), # Helper function recommended
                 "token_uri": "https://oauth2.googleapis.com/token",
            },
            scopes=SCOPES # Ensure scopes match what was granted
        )
        # It's good practice to ensure it has the refresh token set
        if not creds.refresh_token:
             creds.refresh_token = refresh_token # Explicitly set if needed

        logger.info(f"Credentials object created for user ID: {user_google_id}")
        return creds
    except Exception as e:
        logger.error(f"Failed to create Credentials object from refresh token: {e}")
        return None

def get_client_secret() -> str:
    """ Placeholder to securely load client secret """
    # In production, load from environment variable or secrets manager
    import json
    try:
        with open(CLIENT_SECRETS_FILE, 'r') as f:
            secrets = json.load(f)
            return secrets.get("web", {}).get("client_secret")
    except Exception as e:
        logger.error(f"Could not load client secret from {CLIENT_SECRETS_FILE}: {e}")
        raise HTTPException(status_code=500, detail="Server configuration error: Missing client secret.")


# --- Request Models ---
class TokenExchangeRequest(BaseModel):
    id_token: str = Field(..., description="Google ID Token received from client")
    auth_code: str = Field(..., description="Google Server Auth Code received from client")


# --- API Endpoints ---

@app.post("/auth/google/exchange", tags=["Authentication"])
async def auth_google_exchange(payload: TokenExchangeRequest):
    """
    Exchanges Google Auth Code for tokens and stores the refresh token.
    Verifies the ID token to link tokens to the correct user.
    """
    logger.info("Received request for /auth/google/exchange")

    # 1. Verify the ID Token first to authenticate the user
    try:
        id_info = await verify_google_id_token(payload.id_token)
        user_google_id = id_info.get('sub')
        if not user_google_id:
            raise HTTPException(status_code=400, detail="Could not get user ID from token.")
        user_email = id_info.get('email') # For logging/confirmation
        logger.info(f"Token exchange request authenticated for user: {user_email} (ID: {user_google_id})")
    except HTTPException as e:
        # Re-raise HTTPException from verification
        raise e
    except Exception as e:
        logger.error(f"Unexpected error during ID token verification: {e}")
        raise HTTPException(status_code=500, detail="Authentication error")

    # 2. Exchange the Authorization Code for Tokens
    try:
        # Configure the Flow object.
        # The redirect_uri must be one of the authorized redirect URIs
        # configured for your application in the Google Cloud Console, even if
        # it's not directly used in this server-to-server exchange.
        # It's often set to 'postmessage' or a dummy URL like 'urn:ietf:wg:oauth:2.0:oob'
        # or one matching your client setup. Check your GCP settings.
        # Use 'postmessage' if that's what your client setup expects or allows for this flow.
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            # Use 'postmessage' or ensure this matches a configured Redirect URI in GCP
            redirect_uri='http://localhost:8000'
            # redirect_uri='postmessage'
            # Or try: redirect_uri='urn:ietf:wg:oauth:2.0:oob'
        )

        logger.info(f"Attempting to fetch token using auth code for user: {user_email}")
        # Perform the code exchange to get tokens
        flow.fetch_token(code=payload.auth_code)

        # Get the credentials containing access and refresh tokens
        credentials_result = flow.credentials
        if not credentials_result or not credentials_result.refresh_token:
            logger.error("Failed to obtain refresh token from Google.")
            raise HTTPException(status_code=400, detail="Could not obtain refresh token from Google. User might have already granted permission or code expired.")

        refresh_token = credentials_result.refresh_token
        access_token = credentials_result.token # Optional to store/use immediately
        expiry = credentials_result.expiry # Optional

        # --- Store the Refresh Token Securely ---
        # !!! Replace this with DATABASE storage in production !!!
        user_refresh_tokens[user_google_id] = refresh_token
        logger.info(f"Successfully obtained and stored refresh token for user: {user_email} (ID: {user_google_id})")

        # You can return minimal confirmation or user info
        return {
            "status": "success",
            "message": "Authorization successful. Calendar access granted.",
            "user_email": user_email
        }

    except FileNotFoundError:
        logger.error(f"Client secrets file not found at: {CLIENT_SECRETS_FILE}")
        raise HTTPException(status_code=500, detail="Server configuration error: Client secrets file missing.")
    except Exception as e:
        logger.error(f"Error exchanging auth code: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}") # Log full traceback
        # Provide a more generic error to the client
        raise HTTPException(status_code=500, detail=f"Failed to exchange Google auth code: {e}")

# --- Хранилище Состояния Диалога (In-Memory - WARNING для продакшена) ---
class ConversationState(BaseModel):
    stage: str = "start"
    initial_request_text: Optional[str] = None
    classification: Optional[str] = None
    extracted_event_data: Optional[Dict] = None
    last_clarification_question: Optional[str] = None
    error_message: Optional[str] = None

user_conversation_state: Dict[str, ConversationState] = {}

# --- Новая модель для универсального запроса ---
class UnifiedProcessRequest(BaseModel):
    id_token_str: str
    text: Optional[str] = None # Текст, если пользователь ввел его
    # Если добавляем аудио снова:
    # audio: Optional[UploadFile] = None # Аудио, если пользователь записал

# --- Вспомогательная функция для очистки состояния ---
def clear_conversation_state(user_google_id: str):
    if user_google_id in user_conversation_state:
        del user_conversation_state[user_google_id]
        logger.info(f"Cleared conversation state for user {user_google_id}")


async def finalize_event_creation(user_google_id: str, user_email: str, state: ConversationState):
    """Helper function to handle the final event creation step."""
    logger.info(f"Executing final event creation stage for user {user_email}.")

    creds = get_credentials_from_refresh_token(user_google_id)
    if not creds:
        clear_conversation_state(user_google_id)
        # Используем 401, так как проблема с авторизацией пользователя
        raise HTTPException(status_code=401, detail="User authorization required or expired. Please sign in again.")

    final_llm_data = state.extracted_event_data
    if not final_llm_data or not final_llm_data.get("event"):
        clear_conversation_state(user_google_id)
        raise HTTPException(status_code=500, detail="Internal error: Final event data missing.")

    try:
        # --- Вызов НОВОЙ функции ---
        created_events = process_and_create_calendar_events(final_llm_data, creds)

        clear_conversation_state(user_google_id) # Очищаем состояние после попытки создания

        if not created_events:
             # Ни одно событие не было создано (возможно, из-за ошибок валидации или API)
             logger.warning(f"No events were actually created for user {user_email} based on LLM data.")
             # Возвращаем ошибку или инфо-сообщение? Вернем инфо.
             return {
                 "status": "info", # Или "error"? Зависит от того, считаем ли мы это ошибкой LLM или API
                 "message": "Could not create any events based on the provided details. Please try rephrasing your request."
             }
        elif len(created_events) == 1:
            # --- Успешно создано одно событие ---
            event_info = created_events[0]
            logger.info(f"Successfully created 1 event for user {user_email}.")
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
            # Формируем общее сообщение
            event_summaries = [ev.get("summary", "Unnamed Event") for ev in created_events]
            return {
                "status": "success",
                "message": f"{len(created_events)} events created successfully!",
                # Можно вернуть список ссылок или названий
                "events_created": event_summaries,
                "first_event_link": created_events[0].get("htmlLink") # Ссылка на первое для примера
            }

    except Exception as final_ex:
        # Ловим ошибки из process_and_create_calendar_events (напр., refresh token error)
        # или другие неожиданные ошибки
        logger.error(f"Exception during finalize_event_creation for user {user_email}: {final_ex}\n{traceback.format_exc()}")
        clear_conversation_state(user_google_id) # Очищаем состояние при ошибке
        # Перебрасываем как HTTP ошибку
        if "refresh" in str(final_ex).lower(): # Простой чек на ошибку рефреша
             raise HTTPException(status_code=401, detail=f"Authorization failed: {final_ex}")
        else:
             raise HTTPException(status_code=500, detail=f"Failed to process event creation: {final_ex}")


# --- Обновленный Универсальный Эндпоинт Обработки ---
@app.post("/process", tags=["Core Logic"])
async def process_unified_request(
    # Используем Form и File для multipart/form-data
    id_token_str: str = Form(...),
    text: Optional[str] = Form(None),
    audio: Optional[UploadFile] = File(None) # Аудио теперь опциональный файл
):
    """
    Handles both text and audio requests through a multi-stage conversational LLM pipeline.
    Manages conversation state for clarifications. Prioritizes audio if provided.
    """
    logger.info("Received request for /process")
    if text: logger.info(f"Received text form data (length: {len(text)})")
    if audio: logger.info(f"Received audio file: {audio.filename} ({audio.content_type})")

    # --- 1. Аутентификация ---
    try:
        id_info = await verify_google_id_token(id_token_str)
        user_google_id = id_info.get('sub')
        user_email = id_info.get('email')
        if not user_google_id:
            raise HTTPException(status_code=401, detail="Could not get user ID from token.")
        logger.info(f"Processing request authenticated for user: {user_email} (ID: {user_google_id})")
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error during ID token verification: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Authentication error")

    # --- 2. Получение текста запроса (Приоритет Аудио) ---
    input_text: Optional[str] = None
    temp_audio_path: Optional[str] = None # Путь к временному аудиофайлу

    try:
        if audio:
            logger.info(f"Processing provided audio file: {audio.filename}")
            # --- Обработка Аудио ---
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp: # Укажите нужный суффикс
                content = await audio.read()
                if not content:
                     logger.warning("Empty audio file received.")
                     raise HTTPException(status_code=400, detail="Empty audio file received.")
                tmp.write(content)
                temp_audio_path = tmp.name
                logger.info(f"Audio file saved temporarily to: {temp_audio_path}")

            # --- Speech-to-Text ---
            logger.info(f"Performing speech-to-text on {temp_audio_path}")
            # Убедитесь, что recognize_speech корректно обрабатывает ошибки и возвращает None или пустую строку при неудаче
            recognized_text = recognize_speech(temp_audio_path)

            if not recognized_text or recognized_text.isspace():
                logger.warning(f"Speech recognition returned empty or failed for {temp_audio_path}.")
                raise HTTPException(status_code=400, detail="Could not recognize speech in the audio.")
            else:
                input_text = recognized_text
                logger.info(f"Recognized text: '{input_text}'")

        elif text:
            # --- Используем предоставленный текст ---
            logger.info(f"Using provided text.")
            input_text = text
        else:
            # --- Нет ни аудио, ни текста ---
            logger.warning("No text or audio provided in the request.")
            raise HTTPException(status_code=400, detail="No text or audio input provided.")

        # --- Финальная проверка текста ---
        if not input_text or input_text.isspace():
             logger.error("Input text is empty after processing audio/text input.") # Эта ситуация не должна возникать при правильной логике выше
             raise HTTPException(status_code=400, detail="Input processing resulted in empty text.")

        # --- 3. Управление Состоянием Диалога и Конвейер LLM ---
        state = user_conversation_state.get(user_google_id, ConversationState(stage="start"))
        logger.info(f"Current conversation stage for user {user_google_id}: {state.stage}")

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

        # --- Сохраняем обновленное состояние (если не было критической ошибки ДО этого момента) ---
        if state.stage != "error":
             user_conversation_state[user_google_id] = state
             logger.info(f"Saved updated state for user {user_google_id}: Stage={state.stage}")
        else:
             logger.info(f"Not saving state for user {user_google_id} due to error stage.")


        # --- Финальная обработка или возврат ответа ---
        if state.stage == "finalizing":
            logger.info(f"Executing final event creation stage for user {user_email}.") # Добавил user_email для лога

            # --- Этап 4: Получение Учетных Данных и Данных События ---
            creds = get_credentials_from_refresh_token(user_google_id)
            if not creds:
                clear_conversation_state(user_google_id)
                logger.warning(f"Credentials missing for user {user_email}, requiring re-auth.")
                # Используем 401, так как проблема с авторизацией пользователя
                raise HTTPException(status_code=401, detail="User authorization required or expired. Please sign in again.")

            final_llm_data = state.extracted_event_data
            # Проверяем наличие и валидность ключа 'event' (должен быть список)
            if not final_llm_data or not isinstance(final_llm_data.get("event"), list):
                clear_conversation_state(user_google_id)
                logger.error(f"Internal error: Final LLM data for user {user_email} is missing or invalid 'event' list.")
                raise HTTPException(status_code=500, detail="Internal error: Event data missing or invalid before creation.")

            # --- Вызов новой функции для создания событий ---
            try:
                # Эта функция теперь обрабатывает список событий и вызывает _create_single_calendar_event
                created_events: List[Dict] = process_and_create_calendar_events(final_llm_data, creds)

                # Очищаем состояние ПОСЛЕ успешной или неуспешной *попытки* создания
                # Если process_and_create_calendar_events бросит исключение, оно будет поймано внешним блоком
                clear_conversation_state(user_google_id)

                # --- Формирование ответа на основе результата ---
                if not created_events:
                    # Ни одно событие не было создано (возможно, из-за ошибок валидации или API внутри цикла)
                    logger.warning(f"No events were actually created for user {user_email} based on LLM data.")
                    return {
                        "status": "info", # Возвращаем инфо-статус
                        "message": "I couldn't create any events from your request. Perhaps the details were invalid or incomplete. Please try rephrasing."
                    }
                elif len(created_events) == 1:
                    # --- Успешно создано ОДНО событие ---
                    event_info = created_events[0]
                    logger.info(f"Successfully created 1 event for user {user_email}: {event_info.get('id')}")
                    return {
                        "status": "success",
                        "message": "Event created successfully!",
                        "event": { # Структура ответа для одного события
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
                # Ловим ошибки из process_and_create_calendar_events
                # (напр., ошибка обновления токена, ошибка сборки сервиса)
                # или другие неожиданные ошибки на этом финальном этапе
                logger.error(f"Exception during final event creation stage for user {user_email}: {final_ex}\n{traceback.format_exc()}")
                clear_conversation_state(user_google_id) # Очищаем состояние при ошибке

                # Перебрасываем как HTTP ошибку, чтобы клиент получил ошибку сервера
                if "refresh" in str(final_ex).lower(): # Простой чек на ошибку рефреша
                     raise HTTPException(status_code=401, detail=f"Authorization failed: {final_ex}")
                else:
                     raise HTTPException(status_code=500, detail=f"Failed to process event creation: {final_ex}")

        elif state.stage == "awaiting_clarification":
             # Возвращаем уточняющий вопрос (код без изменений)
             return {
                 "status": "clarification_needed",
                 "message": state.last_clarification_question or "Could you please provide more details?"
             }
        elif state.stage == "error":
             # Возвращаем сообщение об ошибке LLM (код без изменений)
             error_msg = state.error_message or "An unknown processing error occurred."
             clear_conversation_state(user_google_id)
             return {
                 "status": "error",
                 "message": error_msg
             }
        else: # Неожиданное состояние (код без изменений)
             clear_conversation_state(user_google_id)
             logger.error(f"Reached unexpected state '{state.stage}' for user {user_google_id}")
             raise HTTPException(status_code=500, detail="Internal server error: Unexpected conversation state.")

    except HTTPException as http_ex:
        # Если ошибка возникла до сохранения состояния (напр., аутентификация), состояние не трогаем
        # Если после - оно может быть уже очищено или содержать ошибку
        logger.warning(f"Caught HTTPException: {http_ex.status_code} - {http_ex.detail}")
        raise http_ex # Перебрасываем HTTP ошибки
    except Exception as final_ex:
        # Ловим любые другие ошибки (напр., при обработке аудио)
        logger.error(f"Unhandled exception during processing for user {user_google_id}: {final_ex}\n{traceback.format_exc()}")
        clear_conversation_state(user_google_id) # Очищаем состояние при неизвестной ошибке
        raise HTTPException(status_code=500, detail=f"An unexpected internal error occurred: {final_ex}")
    finally:
        # --- Очистка временного аудиофайла ---
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.unlink(temp_audio_path)
                logger.info(f"Deleted temporary audio file: {temp_audio_path}")
            except Exception as e:
                logger.error(f"Error deleting temporary file {temp_audio_path}: {e}")

# --- Root endpoint for testing ---
@app.get("/", tags=["Status"])
async def root():
    return {"message": "Audio Calendar Assistant Backend is running!"}

# --- Run with Uvicorn (for local development) ---
# if __name__ == "__main__":
#     import uvicorn
#     # Use 0.0.0.0 to make it accessible on your local network
#     uvicorn.run(app, host="0.0.0.0", port=8000)
#     # Command line: uvicorn fastapi_backend:app --host 0.0.0.0 --port 8000 --reload