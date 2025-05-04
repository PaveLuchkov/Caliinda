# fastapi_backend.py
import datetime
from fastapi import FastAPI, HTTPException, Depends, Header, Query, File, UploadFile, Form, status
from fastapi.middleware.cors import CORSMiddleware
from grpc import Status
from mcp import Resource
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

# --- Импорт локальных модулей ---
import src.config as config # Наш файл конфигурации
from src.database import get_db_session # Функция для получения сессии БД
import src.database as db_utils # Функции для работы с БД (get_user_by_google_id, etc.)
from sqlalchemy.orm import Session # Тип для сессии БД
from src.llm_handler import LLMHandler
from src.calendar_integration import get_events_for_date, SimpleCalendarEvent, get_events_for_range
from src.speech_to_text import recognize_speech
from src.orchestrator import Orchestrator
import src.redis_cache as redis
from pydantic import BaseModel, Field, field_validator
from fastapi import FastAPI, Depends, HTTPException, Body
from google.oauth2.credentials import Credentials  # Для работы с Credentials
from googleapiclient.discovery import build

# --- Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Caliinda Assistant AI Backend",
    description="Handles user requests via text/audio, orchestrates LLMs and Google Calendar.",
    version="1.2.0"
)

# --- CORS Configuration ---
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic модели для ответа API (события) ---
class ProcessResponse(BaseModel):
    status: str # 'clarification_needed', 'success', 'error', 'partial_error', 'info', 'auth_required' ?
    message: str

class TokenExchangeRequest(BaseModel):
    id_token: str
    auth_code: str

class CalendarEventResponse(BaseModel):
    id: str
    summary: str
    startTime: str
    endTime: str
    isAllDay: bool
    description: Optional[str] = None
    location: Optional[str] = None

    class Config:
        from_attributes = True

class CreateEventRequest(BaseModel):
    summary: str = Field(..., min_length=1, description="Event title")
    startTime: str = Field(..., description="Start time in ISO 8601 format (date or datetime)")
    endTime: str = Field(..., description="End time in ISO 8601 format (date or datetime)")
    isAllDay: bool = Field(..., description="Flag indicating if the event is all-day")
    description: Optional[str] = Field(None, description="Optional event description")
    location: Optional[str] = Field(None, description="Optional event location")

    @field_validator('endTime')
    @classmethod # Добавляем classmethod для Pydantic V2
    def end_time_after_start_time(cls, v, info): # info вместо values в Pydantic V2
        start_time = info.data.get('startTime')
        if start_time and v < start_time:
            logger.warning(f"Validation warning: endTime '{v}' might be before startTime '{start_time}'. Allowing for now.")
            # Добавить реальный парсинг и сравнение datetime, если нужна строгая валидация
        return v

# Модель ответа при успешном создании события
class CreateEventResponse(BaseModel):
    status: str = "success"
    message: str = "Event created successfully"
    eventId: Optional[str] = Field(None, description="ID of the created Google Calendar event")

# --- Initialize Handlers ---
llm_handler_instance = LLMHandler()
orchestrator_instance = Orchestrator(llm_handler_instance)


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
    with get_db_session() as db:
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
    "/calendar/events/range", # Новый путь
    response_model=List[CalendarEventResponse], # Модель ответа та же - список событий
    tags=["Calendar"] # Тот же тег
)
async def get_calendar_events_range(
    # Новые параметры: startDate и endDate
    startDate: str = Query(..., description="Start date for the range (YYYY-MM-DD format)", regex=r"^\d{4}-\d{2}-\d{2}$"),
    endDate: str = Query(..., description="End date for the range (YYYY-MM-DD format)", regex=r"^\d{4}-\d{2}-\d{2}$"),
    # Зависимости остаются теми же
    user_google_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Fetches Google Calendar events for the authenticated user for a specified date range.
    Requires a valid Bearer ID token in the Authorization header.
    """
    logger.info(f"Received request for /calendar/events/range for user {user_google_id} from {startDate} to {endDate}")

    # 1. Парсинг дат
    try:
        start_date_obj = datetime.datetime.strptime(startDate, '%Y-%m-%d').date()
        end_date_obj = datetime.datetime.strptime(endDate, '%Y-%m-%d').date()
    except ValueError:
        logger.warning(f"Invalid date format received: startDate={startDate}, endDate={endDate}")
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD for both startDate and endDate.")

    # Проверка логичности диапазона
    if start_date_obj > end_date_obj:
         logger.warning(f"Invalid date range: start date {startDate} is after end date {endDate}")
         raise HTTPException(status_code=400, detail="Invalid date range: startDate cannot be after endDate.")

    # 2. Получение учетных данных Google и обновление токена (логика та же)
    creds = get_credentials_from_db_token(user_google_id, db)
    if not creds:
        logger.error(f"Could not retrieve valid Google credentials for user {user_google_id} from DB.")
        raise HTTPException(status_code=403, detail="Google Calendar access not configured or token revoked. Please sign in again.")

    try:
        if creds.expired and creds.refresh_token:
            logger.info(f"Google access token expired for user {user_google_id}, attempting refresh.")
            # Используй правильный объект Request (возможно, из google.auth.transport.requests)
            creds.refresh(google_requests.Request())
            logger.info(f"Google access token refreshed successfully for user {user_google_id}.")
            # TODO: Не забудь реализовать сохранение обновленного токена в БД!
            # save_refreshed_credentials(user_google_id, creds, db)
    except Exception as refresh_error:
         logger.error(f"Failed to refresh Google access token for user {user_google_id}: {refresh_error}", exc_info=True)
         raise HTTPException(status_code=403, detail=f"Failed to refresh Google access token. Access might be revoked. Details: {refresh_error}")

    # 3. Вызов НОВОЙ функции для получения событий из Google Calendar
    try:
        logger.debug(f"Calling get_events_for_range for user {user_google_id}")
        # Передаем Credentials и объекты дат
        simple_events_list: List[SimpleCalendarEvent] = get_events_for_range(creds, start_date_obj, end_date_obj)

        # Преобразуем SimpleCalendarEvent в dict для FastAPI/Pydantic
        # FastAPI автоматически проверит соответствие модели CalendarEventResponse
        response_events = [event.to_dict() for event in simple_events_list]

        logger.info(f"Successfully fetched {len(response_events)} events for user {user_google_id} in range {startDate} to {endDate}")
        return response_events # FastAPI автоматически преобразует в JSON

    # Обработка ошибок остается такой же, как в старом эндпоинте
    except HttpError as api_error:
        logger.error(f"Google Calendar API error for user {user_google_id} (range {startDate}-{endDate}): {api_error.status_code} - {api_error.reason}", exc_info=True)
        detail = f"Google Calendar API error: {api_error.reason}"
        if api_error.status_code == 401 or api_error.status_code == 403:
             detail = "Access to Google Calendar denied or token invalid. Please sign in again."
             raise HTTPException(status_code=403, detail=detail)
        raise HTTPException(status_code=502, detail=detail)

    except Exception as e:
        logger.error(f"Unexpected error processing calendar events range request for user {user_google_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error processing request: {e}")
    

# --- Эндпоинт /process (ОБНОВЛЕННЫЙ) ---
@app.post("/process", response_model=ProcessResponse, tags=["AI Logic"])
async def process_unified_request(
    user_google_id: str = Depends(get_current_user_id), # Аутентификация
    time: str = Form(..., description="Client's current time in ISO format (e.g., 2023-10-27T10:30:00+03:00)"),
    timeZone: str = Form(..., description="Client's IANA timezone name (e.g., Europe/Moscow)"),
    text: Optional[str] = Form(None), # Текстовый ввод
    audio: Optional[UploadFile] = File(None), # Аудио ввод
    db: Session = Depends(get_db), # Сессия БД
    temper: str = Form(None), # Дополнительный параметр (если нужен)
):
    """
    Handles user request (text or audio), orchestrates LLMs and Google Calendar actions.
    Requires 'Authorization: Bearer <google_id_token>' header.
    """
    # --- Проверка инициализации ---
    if not orchestrator_instance or not llm_handler_instance:
         logger.critical("Core components (Orchestrator/LLMHandler) not initialized.")
         raise HTTPException(status_code=503, detail="Service temporarily unavailable. Core components offline.")
    if not redis.redis_client:
         logger.warning("Redis unavailable, history will not be used.")
         # Можно либо падать, либо продолжать без истории (зависит от требований)
         # raise HTTPException(status_code=503, detail="Service temporarily unavailable. History storage offline.")

    logger.info(f"Processing request for user {user_google_id} | Time: {time} ({timeZone}) | Text: {text is not None} | Audio: {audio is not None}")
    temp_audio_path: Optional[str] = None
    input_text: Optional[str] = None

    try:
        # 1. Получение текста (аудио или текст)
        if audio:
            # Проверяем размер файла перед чтением, если нужно
            # MAX_SIZE = 10 * 1024 * 1024 # 10 MB limit example
            # if audio.size > MAX_SIZE:
            #     raise HTTPException(status_code=413, detail=f"Audio file too large (>{MAX_SIZE} bytes).")

            # Используем безопасный временный файл
            # Важно: убедись, что система имеет права на запись в директорию временных файлов
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp: # Уточни суффикс
                try:
                    content = await audio.read()
                    if not content: raise HTTPException(status_code=400, detail="Empty audio file.")
                    tmp.write(content)
                    temp_audio_path = tmp.name
                except Exception as read_err:
                    logger.error(f"Error reading/writing audio file: {read_err}", exc_info=True)
                    raise HTTPException(status_code=500, detail="Error processing uploaded audio file.")
            logger.info(f"Audio saved to temp file: {temp_audio_path}")

            # Вызов функции распознавания речи (из speech.py)
            try:
                recognized_text = recognize_speech(temp_audio_path)
            except Exception as stt_err:
                 logger.error(f"Speech recognition failed: {stt_err}", exc_info=True)
                 raise HTTPException(status_code=500, detail=f"Speech recognition service error: {stt_err}")

            if not recognized_text or not recognized_text.strip():
                logger.warning(f"STT result empty for user {user_google_id}")
                raise HTTPException(status_code=400, detail="Speech recognition failed or result is empty.")
            input_text = recognized_text.strip()
            logger.info(f"Recognized text: '{input_text}'")
        elif text:
            if not text.strip(): raise HTTPException(status_code=400, detail="Empty text input.")
            input_text = text.strip()
            logger.info(f"Using provided text: '{input_text}'")
        else:
            raise HTTPException(status_code=400, detail="No text or audio input provided.")

        # Финальная проверка input_text
        if not input_text: # Должно быть избыточно, но безопасно
             raise HTTPException(status_code=400, detail="Input processing resulted in empty text.")

        # 2. Вызов Оркестратора
        orchestrator_result = await orchestrator_instance.handle_user_request(
            user_google_id=user_google_id,
            user_text=input_text,
            time=time,           # Время из запроса
            timezone=timeZone,   # Таймзона из запроса
            db=db,                # Сессия БД
            temper = temper, # Дополнительный параметр (если нужен)
        )

        # 3. Формирование ответа FastAPI
        response_status = orchestrator_result.get("status", "error")
        response_message = orchestrator_result.get("message", "An unknown error occurred.")

        # Логируем финальный ответ
        logger.info(f"Orchestrator result for user {user_google_id}: Status='{response_status}', Message='{response_message[:100]}...'")

        return ProcessResponse(status=response_status, message=response_message)

    except HTTPException as http_ex:
        # Логируем и перебрасываем HTTP исключения (ошибки валидации, аутентификации и т.д.)
        logger.warning(f"HTTPException in /process: {http_ex.status_code} - {http_ex.detail}")
        raise http_ex
    except Exception as final_ex:
        # Ловим все остальные неожиданные ошибки
        logger.error(f"Unhandled exception in /process for user {user_google_id}: {final_ex}", exc_info=True)
        # Не показываем внутренние детали ошибки пользователю
        raise HTTPException(status_code=500, detail="An unexpected internal server error occurred.")
    finally:
        # Очистка временного аудиофайла
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.unlink(temp_audio_path)
                logger.info(f"Deleted temp audio file: {temp_audio_path}")
            except Exception as e:
                logger.error(f"Error deleting temp file {temp_audio_path}: {e}")


@app.post(
    "/calendar/events",
    response_model=CreateEventResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Calendar"],
    summary="Create a new Google Calendar event",
    responses={
        400: {"description": "Invalid input data"},
        401: {"description": "Authentication failed (token issue)"},
        403: {"description": "Forbidden (e.g., scope missing, user not in DB)"},
        500: {"description": "Internal server error"},
        502: {"description": "Google API error"},
    }
)
async def create_calendar_event(
    event_data: CreateEventRequest, # Данные события из тела запроса
    user_google_id: str = Depends(get_current_user_id), # Проверка аутентификации и получение ID
    db: Session = Depends(get_db) # Получаем сессию БД для получения Credentials
):
    """ Creates a new event in the user's primary Google Calendar. """
    logger.info(f"Received request to create event for user {user_google_id}: '{event_data.summary}'")

    # 1. Получаем Credentials пользователя из БД
    creds = get_credentials_from_db_token(user_google_id, db)
    if not creds:
        # get_current_user_id уже проверил, что пользователь есть в БД,
        # значит, проблема именно с получением/обновлением токена.
        logger.error(f"Could not retrieve/refresh valid Google credentials for user {user_google_id}.")
        # Используем 403, т.к. проблема с доступом к ресурсу Google
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Google Calendar access token invalid or revoked. Please sign in again.")

    # 2. Формируем тело запроса для Google API
    event_body = {
        'summary': event_data.summary,
        'description': event_data.description,
        'location': event_data.location,
        'start': {},
        'end': {}
    }
    if event_data.isAllDay:
        # Google Calendar API ожидает только дату для all-day событий
        try:
            # Проверяем формат на всякий случай
            datetime.date.fromisoformat(event_data.startTime)
            datetime.date.fromisoformat(event_data.endTime)
            event_body['start']['date'] = event_data.startTime
            event_body['end']['date'] = event_data.endTime # Конец не включительно
        except ValueError:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format for all-day event. Use YYYY-MM-DD.")
    else:
        # Google Calendar API ожидает dateTime в формате RFC3339
        # Клиент должен прислать строку в правильном формате (например, из Instant.toString() или со смещением)
        event_body['start']['dateTime'] = event_data.startTime
        event_body['end']['dateTime'] = event_data.endTime
        # event_body['start']['timeZone'] = '...' # Опционально

    # 3. Вызов Google Calendar API для вставки события
    try:
        service: Resource = build('calendar', 'v3', credentials=creds)
        logger.info(f"Attempting to insert event for user {user_google_id}: '{event_data.summary}'")

        created_event: dict = service.events().insert(
            calendarId='primary',
            body=event_body
        ).execute()

        event_id = created_event.get('id')
        logger.info(f"Event created successfully for user {user_google_id}. Event ID: {event_id}")

        # Возвращаем успешный ответ с ID события
        return CreateEventResponse(eventId=event_id)

    except HttpError as error:
        # Обрабатываем ошибки Google API
        error_details = error.resp.get('content', b'').decode('utf-8')
        status_code = error.resp.status
        logger.error(f"Google API error inserting event for user {user_google_id}: {status_code} - {error_details}", exc_info=True)

        http_status = status.HTTP_502_BAD_GATEWAY # По умолчанию Bad Gateway
        detail=f"Google API Error: {error_details}"
        if status_code == 401:
             http_status=status.HTTP_401_UNAUTHORIZED
             detail=f"Google API Authentication Error: {error_details}"
        elif status_code == 403:
             http_status=status.HTTP_403_FORBIDDEN
             detail=f"Google API Forbidden: {error_details}"
        elif status_code == 400:
             http_status=status.HTTP_400_BAD_REQUEST
             detail=f"Google API Bad Request (check data format/values): {error_details}"
        # Добавим обработку 404, если вдруг 'primary' календарь не найден
        elif status_code == 404:
             http_status = status.HTTP_404_NOT_FOUND
             detail = "Primary Google Calendar not found."

        raise HTTPException(status_code=http_status, detail=detail)

    except Exception as e:
        logger.error(f"Unexpected error inserting event for user {user_google_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error while creating event.")


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