# fastapi_backend.py
import datetime
from fastapi import FastAPI, HTTPException, Depends, Header, Query, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import tempfile
import os
import logging
from typing import Dict, List, Optional

# Google Auth Libraries
from google.oauth2 import id_token, credentials
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow
from googleapiclient.errors import HttpError
from requests import HTTPError

# --- Импорт локальных модулей ---
import src.config as config # Наш файл конфигурации
from src.database import get_db_session # Функция для получения сессии БД
import src.database as db_utils # Функции для работы с БД (get_user_by_google_id, etc.)
from sqlalchemy.orm import Session # Тип для сессии БД
from src.llm_handler import LLMHandler
from src.calendar_integration import process_and_create_calendar_events, get_events_for_date, SimpleCalendarEvent
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

# --- Pydantic модели для ответа API (события) ---
class CalendarEventResponse(BaseModel):
    id: str
    summary: str
    startTime: str
    endTime: str
    description: Optional[str] = None
    location: Optional[str] = None

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


async def get_current_user_id(authorization: str = Header(None), db: Session = Depends(get_db)) -> str:
    """
    Dependency to verify Authorization header ('Bearer <id_token>')
    and return user's Google ID ('sub'). Logs the user email.
    Raises HTTPException on errors.
    """
    if authorization is None:
        logger.warning("Authorization header missing")
        raise HTTPException(status_code=401, detail="Authorization header missing")

    scheme, _, token = authorization.partition(' ')
    if not scheme or scheme.lower() != 'bearer' or not token:
        logger.warning(f"Invalid authorization scheme or token missing: {scheme}")
        raise HTTPException(status_code=401, detail="Invalid authorization scheme or token")

    try:
        # Используем существующую функцию верификации
        id_info = await verify_google_id_token(token)
        user_google_id = id_info.get('sub')
        user_email = id_info.get('email', 'N/A') # Получаем email для лога

        if not user_google_id:
            logger.error("User ID ('sub') missing from verified token payload.")
            raise HTTPException(status_code=401, detail="Could not extract user ID from token")

        # Дополнительная проверка: существует ли пользователь в нашей БД? (Опционально, но полезно)
        user = db_utils.get_user_by_google_id(db, user_google_id)
        if not user:
             logger.warning(f"User with google_id {user_google_id} (email: {user_email}) not found in DB during request authorization.")
             raise HTTPException(status_code=403, detail="User not registered in the system")

        # Логируем email здесь, внутри зависимости
        logger.info(f"Request authorized for user_google_id: {user_google_id} (email: {user_email})")
        return user_google_id 

    except HTTPException as e:
        # Перебрасываем HTTP исключения от verify_google_id_token или проверки пользователя
        raise e
    except Exception as e:
        logger.error(f"Unexpected error during request authorization: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during authorization")

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
        if not credentials_result or not credentials_result.token: # Проверяем наличие хотя бы access_token
            logger.error("Failed to obtain access token (or any tokens) from Google.")
            # Возможно, стоит проверить credentials_result на наличие ошибки 'invalid_grant'
            error_detail = "Could not obtain valid tokens from Google."
            if hasattr(credentials_result, 'error_details'): # Попытка получить больше информации
                error_detail += f" Details: {credentials_result.error_details}"
            raise HTTPException(status_code=400, detail=error_detail)

        access_token = credentials_result.token # Есть access token
        refresh_token = credentials_result.refresh_token # Может быть None, если уже выдавался

        if refresh_token:
            # --- Сохранение/Обновление в БД (только если получили НОВЫЙ refresh_token) ---
            logger.info("Received a new refresh token from Google. Storing/updating in DB.")
            try:
                db_utils.upsert_user_token(
                    db_session=db,
                    google_id=user_google_id,
                    email=user_email,
                    full_name=user_full_name,
                    refresh_token=refresh_token # Сохраняем новый токен
                )
                logger.info(f"Successfully stored/updated refresh token in DB for user: {user_email}")
            except Exception as db_exc:
                logger.error(f"Database error while storing refresh token for {user_email}: {db_exc}", exc_info=True)
                # Можно вернуть 500 ошибку, т.к. не смогли сохранить важные данные
                raise HTTPException(status_code=500, detail="Database error storing token.")

        else:
            # --- Refresh token НЕ получен (вероятно, уже выдавался) ---
            logger.warning(f"No new refresh token received from Google for user: {user_email}. Assuming already granted.")
            # Не обновляем refresh_token в БД.
            # Можно добавить проверку, есть ли пользователь уже в БД, для уверенности.
            existing_user = db_utils.get_user_by_google_id(db, user_google_id)
            if not existing_user or not existing_user.refresh_token:
                logger.error(f"User {user_email} exists but has no refresh token in DB, and Google did not provide one now.")
                # Это проблемная ситуация - согласие вроде есть, а токена нет.
                # Возможно, стоит попросить пользователя перелогиниться с отзывом разрешений.
                raise HTTPException(status_code=400, detail="Authorization inconsistent. Please try signing out and signing in again.")
            else:
                logger.info(f"User {user_email} already has a refresh token in DB. Proceeding without update.")


        # --- Возвращаем успешный ответ ---
        logger.info(f"Authorization successful for user: {user_email}")
        return {
            "status": "success",
            "message": "Authorization successful. Calendar access granted.",
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

@app.get(
    "/calendar/events",
    response_model=List[CalendarEventResponse], # Указываем модель ответа (список событий)
    tags=["Calendar"]
)
async def get_calendar_events(
    # Запрос даты как обязательный параметр query string
    date: str = Query(..., description="Date to fetch events for (YYYY-MM-DD format)", regex=r"^\d{4}-\d{2}-\d{2}$"),
    # Используем зависимость для аутентификации и получения ID пользователя
    user_google_id: str = Depends(get_current_user_id),
    # Получаем сессию БД
    db: Session = Depends(get_db)
):
    """
    Fetches Google Calendar events for the authenticated user for a specified date.
    Requires a valid Bearer ID token in the Authorization header.
    """
    logger.info(f"Received request for /calendar/events for user {user_google_id} on date {date}")

    # 1. Парсинг даты
    try:
        target_date_obj = datetime.datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        logger.warning(f"Invalid date format received: {date}")
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    # 2. Получение учетных данных Google для пользователя из БД
    creds = get_credentials_from_db_token(user_google_id, db)
    if not creds:
        logger.error(f"Could not retrieve valid Google credentials for user {user_google_id} from DB.")
        # Пользователь аутентифицирован на нашем API, но нет учетных данных для Google
        raise HTTPException(status_code=403, detail="Google Calendar access not configured or token revoked. Please sign in again.")

    # Важно: Проверка и обновление токена доступа (если нужно)
    # google-api-python-client обычно делает это автоматически при вызове API,
    # если в объекте creds есть refresh_token и он валиден.
    # Добавим явную проверку на всякий случай, хотя она может быть избыточной.
    try:
        if creds.expired and creds.refresh_token:
            logger.info(f"Google access token expired for user {user_google_id}, attempting refresh.")
            creds.refresh(google_requests.Request())
            logger.info(f"Google access token refreshed successfully for user {user_google_id}.")
            # TODO: По-хорошему, обновленный access_token (и возможно refresh_token, если он изменился)
            # нужно было бы сохранить обратно в хранилище/БД, но Credentials не дает легкого доступа к обновленному refresh_token.
            # get_credentials_from_db_token всегда будет использовать исходный refresh_token из БД.
            # Это стандартное поведение и обычно работает нормально.
    except Exception as refresh_error:
         logger.error(f"Failed to refresh Google access token for user {user_google_id}: {refresh_error}", exc_info=True)
         # Если не удалось обновить токен, скорее всего, доступ отозван
         raise HTTPException(status_code=403, detail=f"Failed to refresh Google access token. Access might be revoked. Details: {refresh_error}")


    # 3. Вызов функции для получения событий из Google Calendar
    try:
        logger.debug(f"Calling get_events_for_date for user {user_google_id}")
        # Передаем объект Credentials и дату
        simple_events_list: list[SimpleCalendarEvent] = get_events_for_date(creds, target_date_obj)

        # Преобразуем SimpleCalendarEvent в dict для FastAPI/Pydantic
        response_events = [event.to_dict() for event in simple_events_list]

        logger.info(f"Successfully fetched {len(response_events)} events for user {user_google_id} on {date}")
        return response_events # FastAPI автоматически преобразует в JSON

    except HttpError as api_error:
        logger.error(f"Google Calendar API error for user {user_google_id}: {api_error.status_code} - {api_error.reason}", exc_info=True)
        detail = f"Google Calendar API error: {api_error.reason}"
        # Особые случаи
        if api_error.status_code == 401 or api_error.status_code == 403:
             detail = "Access to Google Calendar denied or token invalid. Please sign in again."
             raise HTTPException(status_code=403, detail=detail) # Возвращаем 403
        # Другие ошибки API (например, 404 Calendar not found, 5xx)
        raise HTTPException(status_code=502, detail=detail) # 502 Bad Gateway - ошибка при связи с внешним сервисом

    except Exception as e:
        logger.error(f"Unexpected error processing calendar events request for user {user_google_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error processing request: {e}")


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
@app.post("/process", tags=["AI Logic"]) # Метка тега может быть любой
async def process_unified_request(
    # УБРАЛИ id_token_str: str = Form(...)
    # ДОБАВИЛИ зависимость для аутентификации и получения user_google_id
    user_google_id: str = Depends(get_current_user_id),
    # Остальные параметры Form и File как были
    time: str = Form(...),
    timeZone: str = Form(...),
    text: Optional[str] = Form(None),
    audio: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db) # Зависимость от БД остается
):
    # Теперь user_google_id доступен напрямую. Логирование email происходит в get_current_user_id.
    logger.info(f"Received request for /process from user_google_id: {user_google_id}")
    logger.info(f"Time: {time}, TimeZone: {timeZone}, Text provided: {text is not None}, Audio provided: {audio is not None}")

    temp_audio_path: Optional[str] = None
    try:
        # 1. АУТЕНТИФИКАЦИЯ УЖЕ ВЫПОЛНЕНА зависимостью get_current_user_id
        # user_google_id уже содержит проверенный ID пользователя

        # 2. Получение текста (аудио или текст) - логика остается прежней
        input_text: Optional[str] = None
        if audio:
            # Используем tempfile для безопасного сохранения аудио
            # Убедитесь, что директория для временных файлов существует и доступна для записи
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
                content = await audio.read()
                if not content:
                    logger.warning(f"Empty audio file received from user {user_google_id}")
                    raise HTTPException(status_code=400, detail="Empty audio file received.")
                tmp.write(content)
                temp_audio_path = tmp.name
                logger.info(f"Temporary audio file saved for user {user_google_id} at: {temp_audio_path}")

            # Вызов вашей функции распознавания речи
            recognized_text = recognize_speech(temp_audio_path) # Предполагаем, что она есть и работает
            if not recognized_text or recognized_text.strip() == "": # Проверяем на пустую строку после strip
                logger.warning(f"Speech recognition resulted in empty text for user {user_google_id}.")
                # Можно вернуть ошибку или обработать как пустой ввод
                raise HTTPException(status_code=400, detail="Could not recognize speech or recognized text is empty.")
            input_text = recognized_text.strip() # Убираем лишние пробелы
            logger.info(f"Recognized text for user {user_google_id}: '{input_text}'")
        elif text:
            if text.strip() == "":
                 logger.warning(f"Received empty text input from user {user_google_id}")
                 raise HTTPException(status_code=400, detail="Received empty text input.")
            input_text = text.strip() # Убираем лишние пробелы
            logger.info(f"Using provided text for user {user_google_id}: '{input_text}'")
        else:
            # Этот случай не должен возникать, если Form/File параметры настроены правильно,
            # но проверка не повредит
            logger.error(f"No text or audio provided in request for user {user_google_id}")
            raise HTTPException(status_code=400, detail="No text or audio input provided.")

        # Повторная проверка на случай, если input_text как-то стал пустым
        if not input_text:
             logger.error(f"Input processing resulted in empty text unexpectedly for user {user_google_id}")
             raise HTTPException(status_code=400, detail="Input processing resulted in empty text.")

        # 3. Управление состоянием диалога и конвейер LLM - логика остается прежней
        # Используем user_google_id, полученный от зависимости
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
                 logger.error(state.error_message + f" (User: {user_google_id}). Raw Response: {classification_result.get('raw_response') if classification_result else 'N/A'}")
            else:
                state.classification = classification_result.get("classification")
                state.initial_request_text = input_text
                state.stage = "classified"
                logger.info(f"User time : {time}")
                logger.info(f"Intent classified as '{state.classification}' for user {user_google_id}. Moving to next stage.")

        # Переход к следующему этапу возможен сразу после предыдущего, если не было ошибки
        if state.stage == "classified":
            if state.classification == "add":
                # --- Этап 2: Извлечение деталей ---
                logger.info(f"Proceeding to event detail extraction for user {user_google_id}.")
                extraction_result = llm.extract_event_details(
                    state.initial_request_text,
                    time=time,
                    user_timezone=timeZone
                )
                state.extracted_event_data = extraction_result # Сохраняем результат

                if not extraction_result or "error" in extraction_result:
                    error_detail = extraction_result.get("error", "Unknown extraction error") if extraction_result else "LLM Extraction call failed"
                    state.stage = "error"
                    state.error_message = f"Event extraction failed: {error_detail}"
                    logger.error(state.error_message + f" (User: {user_google_id}). Raw Response: {extraction_result.get('raw_response') if extraction_result else 'N/A'}")
                elif extraction_result.get("clarification_needed"):
                    state.stage = "awaiting_clarification"
                    state.last_clarification_question = extraction_result.get("message")
                    logger.info(f"Clarification needed for user {user_google_id}. Question: " + (state.last_clarification_question or "No question provided"))
                else:
                    state.stage = "finalizing"
                    logger.info(f"Extraction complete for user {user_google_id}, no clarification needed. Moving to finalizing.")
            else:
                # Обработка других намерений (не 'add')
                logger.info(f"Handling non-'add' classification: {state.classification} for user {user_google_id}")
                # Формируем ответ пользователю и очищаем состояние
                response_message = f"Sorry, I can only help with adding events right now (Your intent was classified as: {state.classification})."
                clear_conversation_state(user_google_id)
                return {"status": "unsupported", "message": response_message} # Используем 'unsupported' или 'info'

        elif state.stage == "awaiting_clarification":
            # --- Этап 3: Уточнение ---
            logger.info(f"Processing user answer for clarification from user {user_google_id}.")
            if not state.extracted_event_data or not state.last_clarification_question or not state.initial_request_text:
                 state.stage = "error"
                 state.error_message = f"Internal state error during clarification for user {user_google_id}."
                 logger.error(state.error_message)
            else:
                user_answer = input_text # Текущий ввод - это ответ
                clarification_result = llm.clarify_event_details(
                    initial_request=state.initial_request_text,
                    current_event_data=state.extracted_event_data,
                    question_asked=state.last_clarification_question,
                    user_answer=user_answer,
                    time=time,
                    user_timezone=timeZone
                )
                # Обновляем данные в состоянии, даже если есть ошибка (могут быть частично обновлены)
                state.extracted_event_data = clarification_result

                if not clarification_result or "error" in clarification_result:
                    error_detail = clarification_result.get("error", "Unknown clarification error") if clarification_result else "LLM Clarification call failed"
                    state.stage = "error"
                    state.error_message = f"Clarification failed: {error_detail}"
                    logger.error(state.error_message + f" (User: {user_google_id}). Raw Response: {clarification_result.get('raw_response') if clarification_result else 'N/A'}")
                elif clarification_result.get("clarification_needed"):
                     # Снова нужно уточнение
                     state.stage = "awaiting_clarification"
                     state.last_clarification_question = clarification_result.get("message")
                     logger.info(f"Further clarification needed for user {user_google_id}. New Question: " + (state.last_clarification_question or "No question provided"))
                else:
                     # Уточнение успешно, данные обновлены
                     state.stage = "finalizing"
                     state.last_clarification_question = None # Сбрасываем вопрос
                     logger.info(f"Clarification complete for user {user_google_id}. Moving to finalizing.")

        # --- Сохраняем обновленное состояние (если не было критической ошибки, приведшей к stage="error") ---
        if state.stage != "error":
            user_conversation_state[user_google_id] = state
            logger.info(f"Saved updated state for user {user_google_id}: Stage={state.stage}")
        else:
            # Не сохраняем состояние, если оно ошибочное, но уже перешли к возврату ответа
            logger.info(f"Not saving state for user {user_google_id} due to error stage.")


        # --- Финальная обработка или возврат ответа ---
        if state.stage == "finalizing":
            logger.info(f"Executing final event creation stage for user {user_google_id}.")

            # --- Получение Учетных Данных из БД ---
            # Используем user_google_id, полученный от зависимости
            creds = get_credentials_from_db_token(user_google_id, db)
            if not creds:
                # Если нет учетных данных, пользователь аутентифицирован на нашем API,
                # но мы не можем получить доступ к Google Calendar.
                # Возвращаем ошибку, требующую повторного входа/авторизации на клиенте.
                clear_conversation_state(user_google_id) # Очищаем состояние диалога
                logger.warning(f"Credentials missing for user {user_google_id} during finalization, requiring re-auth.")
                # Статус 403 (Forbidden) может быть более подходящим, чем 401, так как пользователь аутентифицирован, но не авторизован для действия.
                raise HTTPException(status_code=403, detail="Google Calendar access not configured or token expired. Please sign in again.")

            final_llm_data = state.extracted_event_data
            # Проверяем, что данные для создания события корректны
            # Убедитесь, что ваша LLM возвращает данные в ожидаемом формате (например, словарь с ключом "event")
            if not final_llm_data or not isinstance(final_llm_data, dict) or "event" not in final_llm_data:
                clear_conversation_state(user_google_id)
                logger.error(f"Internal error: Final LLM data for user {user_google_id} is missing or invalid format. Data: {final_llm_data}")
                raise HTTPException(status_code=500, detail="Internal error: Event data missing or invalid before creation.")

            # --- Вызов функции создания событий (calendar_integration.py) ---
            try:
                # Передаем полученные creds и данные от LLM
                # Убедитесь, что process_and_create_calendar_events принимает эти аргументы
                created_events: List[Dict] = process_and_create_calendar_events(final_llm_data, creds, timeZone)

                # --- Очищаем состояние ПОСЛЕ УСПЕШНОЙ попытки создания ---
                clear_conversation_state(user_google_id)
                logger.info(f"Cleared conversation state for user {user_google_id} after event processing.")

                # --- Формирование ответа ---
                if not created_events:
                     logger.warning(f"Event creation function returned empty list for user {user_google_id}.")
                     # Возможно, LLM не смог извлечь данные, или они были некорректны
                     return {"status": "info", "message": "I understood your request, but couldn't extract valid event details to create anything."}
                elif len(created_events) == 1:
                     event_info = created_events[0]
                     logger.info(f"Successfully created 1 event for user {user_google_id}: {event_info.get('summary')}")
                     # Формируем ответ с деталями одного события
                     return {
                        "status": "success",
                        "message": "Event created successfully!",
                        "event": { # Используем структуру, ожидаемую Android клиентом
                            "event_name": event_info.get("summary"),
                            "start_time": event_info.get("start", {}).get("dateTime") or event_info.get("start", {}).get("date"), # Учитываем all-day
                            "end_time": event_info.get("end", {}).get("dateTime") or event_info.get("end", {}).get("date"), # Учитываем all-day
                            # Добавьте другие поля, если нужно
                        },
                        "event_link": event_info.get("htmlLink"),
                    }
                else:
                    # --- Успешно создано НЕСКОЛЬКО событий ---
                    logger.info(f"Successfully created {len(created_events)} events for user {user_google_id}.")
                    event_summaries = [ev.get("summary", "Unnamed Event") for ev in created_events]
                    message = f"OK! Created {len(created_events)} events for you: " + ", ".join(event_summaries)
                    return {
                        "status": "success",
                        "message": message,
                        "events_created": event_summaries, # Можно вернуть список названий
                        "first_event_link": created_events[0].get("htmlLink") # Ссылка на первое для примера
                    }

            except HTTPError as google_api_error:
                 # Обрабатываем ошибки Google API во время создания
                 logger.error(f"Google Calendar API error during event creation for user {user_google_id}: {google_api_error}", exc_info=True)
                 clear_conversation_state(user_google_id) # Очищаем состояние при ошибке
                 detail = f"Google Calendar API error: {google_api_error.reason}"
                 status_code = 502 # Bad Gateway по умолчанию для ошибок внешнего API
                 if google_api_error.status_code in [401, 403]:
                     detail = "Access to Google Calendar denied or token invalid during event creation. Please sign in again."
                     status_code = 403 # Используем 403
                 raise HTTPException(status_code=status_code, detail=detail)

            except Exception as final_ex:
                # Другие ошибки во время создания события (не Google API)
                logger.error(f"Exception during final event creation processing for user {user_google_id}: {final_ex}", exc_info=True)
                clear_conversation_state(user_google_id) # Очищаем состояние при ошибке
                # Проверяем, не связана ли ошибка с рефрешем токена (хотя это маловероятно здесь)
                if "refresh" in str(final_ex).lower():
                     raise HTTPException(status_code=403, detail=f"Authorization failed during event creation: {final_ex}")
                else:
                     # Общая ошибка сервера при создании
                     raise HTTPException(status_code=500, detail=f"Failed to process event creation: {final_ex}")

        elif state.stage == "awaiting_clarification":
             # Возвращаем уточняющий вопрос, состояние уже сохранено
             logger.info(f"Returning clarification question to user {user_google_id}.")
             return {
                 "status": "clarification_needed",
                 "message": state.last_clarification_question or "Could you please provide more details?"
             }
        elif state.stage == "error":
             # Возвращаем сообщение об ошибке LLM или внутренней ошибке состояния
             error_msg = state.error_message or "An unknown processing error occurred."
             logger.error(f"Returning error state to user {user_google_id}: {error_msg}")
             clear_conversation_state(user_google_id) # Очищаем ошибочное состояние
             return {"status": "error", "message": error_msg}
        else: # Неожиданное состояние (быть не должно, если логика верна)
             clear_conversation_state(user_google_id)
             logger.error(f"Reached unexpected state '{state.stage}' for user {user_google_id}")
             raise HTTPException(status_code=500, detail="Internal server error: Unexpected conversation state.")

    except HTTPException as http_ex:
        # Перехватываем и логируем HTTP ошибки, которые мы сами сгенерировали
        # Не очищаем состояние здесь, т.к. оно могло быть очищено ранее или это ошибка запроса
        logger.warning(f"HTTPException caught for user {user_google_id}: {http_ex.status_code} - {http_ex.detail}", exc_info=False) # Не нужен полный traceback
        raise http_ex # Перебрасываем дальше для FastAPI
    except Exception as final_ex:
        # Ловим все остальные неожиданные ошибки
        logger.error(f"Unhandled exception during processing for user {user_google_id}: {final_ex}", exc_info=True) # Полный traceback
        clear_conversation_state(user_google_id) # Очищаем состояние при неизвестной ошибке
        raise HTTPException(status_code=500, detail=f"An unexpected internal server error occurred.") # Не показываем детали ошибки пользователю
    finally:
        # Очистка временного аудиофайла - логика остается прежней
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