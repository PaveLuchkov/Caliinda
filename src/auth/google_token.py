from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
from typing import Optional
from sqlalchemy.orm import Session # Тип для сессии БД


# Google Auth Libraries
from google.oauth2 import id_token, credentials
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow

# --- Импорт локальных модулей ---
import shared.config as config
from shared.database import get_db_session
import shared.database as db_utils
from shared.types import TokenExchangeRequest

# --- Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Caliinda Assistant AI Backend",
    description="Handles user requests via text/audio, orchestrates LLMs and Google Calendar.",
    version="1.2.0"
)

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
# Эндпоинт для обмена кода авторизации на токен refresh_token
# TODO (возможно, стоит сделать его защищенным, но пока оставим открытым для тестов)
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

        client_config = {
            "web": {
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": ["http://localhost:8080", "postmessage"]
            }
        }
        chosen_redirect_uri = 'http://localhost:8080'

        flow = Flow.from_client_config(
            client_config=client_config,
            scopes=config.SCOPES,
            redirect_uri=chosen_redirect_uri
        )

        logger.info(f"Attempting to fetch token using auth code for user: {user_email} with redirect_uri: {chosen_redirect_uri}")
        flow.fetch_token(code=payload.auth_code)

        credentials_result = flow.credentials
        if not credentials_result or not credentials_result.token: 
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