import logging
from typing import Optional


# Google Auth Libraries
from google.oauth2.credentials import Credentials as GoogleCredentials
from google.auth.transport.requests import Request as GoogleAuthRequest

# --- Импорт локальных модулей ---

# --- Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_access_token_from_refresh(refresh_token: str, client_id: str, client_secret: str, token_uri: str, scopes: list[str]) -> Optional[str]:
    try:
        creds = GoogleCredentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes
        )

        # Если credentials требуют обновления (т.е. access_token нет или истек),
        # этот вызов сделает запрос к token_uri
        if not creds.valid: # Проверка, есть ли валидный access_token
            if creds.expired and creds.refresh_token: # Если истек и есть refresh_token
                logger.info("Access token expired or not present, refreshing...")
                creds.refresh(GoogleAuthRequest()) # Обновляем
                logger.info("Access token refreshed successfully.")
            else:
                if creds.refresh_token:
                    logger.info("Refreshing/fetching access token using refresh token...")
                    creds.refresh(GoogleAuthRequest())
                    logger.info("Access token obtained successfully.")
                else:
                    logger.error("No refresh token available to get access token.")
                    return None
        
        if creds.token:
            logger.info(f"Obtained access_token: {creds.token[:20]}...")
            return creds.token
        else:
            logger.error("Failed to obtain access token after refresh attempt.")
            return None

    except Exception as e:
        logger.error(f"Error refreshing/getting access token: {e}", exc_info=True)
        # Здесь можно проверить, не связана ли ошибка с "invalid_grant" (невалидный refresh_token или client_id/secret)
        if "invalid_grant" in str(e).lower():
            logger.error("Error 'invalid_grant' received. Refresh token might be invalid, revoked, or client credentials incorrect.")
        return None