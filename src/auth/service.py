import logging
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

# --- Импорты для работы с Google Auth ---
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow
from google.auth.exceptions import GoogleAuthError

# --- Импорты из нашего приложения ---
from src.core.config import settings
from src.users import crud as users_crud
from .schemas import TokenExchangeRequest

# --- Настройка логгера ---
logger = logging.getLogger(__name__)


class AuthService:
    """
    Сервисный слой, отвечающий за всю логику, связанную с аутентификацией
    и авторизацией через Google.
    """

    def __init__(self, db_session: Session):
        """
        Инициализирует сервис с сессией базы данных.
        
        Args:
            db_session: Активная сессия SQLAlchemy.
        """
        self.db = db_session

    async def verify_google_id_token(self, token: str) -> dict:
        """
        Верифицирует Google ID Token и возвращает его payload (содержимое).
        Этот метод инкапсулирует логику проверки токена.

        Args:
            token: ID токен от Google в виде строки.

        Raises:
            HTTPException: Если токен невалиден или произошла ошибка проверки.

        Returns:
            Словарь с данными пользователя из токена.
        """
        try:
            # Используем CLIENT_ID из нашего централизованного конфига
            id_info = id_token.verify_oauth2_token(
                token, google_requests.Request(), settings.GOOGLE_CLIENT_ID
            )

            # Дополнительная проверка издателя (issuer)
            if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise ValueError('Wrong issuer.')

            logger.info(f"ID Token успешно верифицирован для пользователя: {id_info.get('email')}")
            return id_info
            
        except ValueError as e:
            # Эта ошибка возникает, если токен не прошел проверку подписи, истек и т.д.
            logger.error(f"Верификация ID Token не удалась: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid Google ID Token: {e}"
            )
        except Exception as e:
            # Любая другая непредвиденная ошибка
            logger.error(f"Неожиданная ошибка при верификации токена: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal error during token verification"
            )

    async def exchange_auth_code(self, payload: TokenExchangeRequest) -> str:
        """
        Основной метод, который выполняет всю логику обмена кода авторизации
        на токены доступа и обновления, а затем сохраняет их в БД.

        Args:
            payload: Данные из запроса, содержащие id_token и auth_code.

        Raises:
            HTTPException: В случае ошибок валидации, взаимодействия с Google или БД.

        Returns:
            Email пользователя в случае успеха.
        """
        # 1. Верификация ID токена для подтверждения личности пользователя
        id_info = await self.verify_google_id_token(payload.id_token)
        
        user_google_id = id_info.get('sub')
        if not user_google_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not get user ID from token.")
            
        user_email = id_info.get('email')
        user_full_name = id_info.get('name')
        logger.info(f"Аутентификация для обмена токенов пройдена для пользователя: {user_email} (ID: {user_google_id})")

        # 2. Обмен кода авторизации на токены (access и refresh)
        try:
            # Конфигурация для Flow берется из централизованных настроек
            client_config = {
                "web": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["postmessage"], # 'postmessage' - стандартное значение для JS-библиотеки Google
                }
            }

            # 'postmessage' является безопасным и стандартным redirect_uri для клиентских приложений,
            # которые передают auth_code на бэкенд. Убедись, что он разрешен в Google Cloud Console.
            flow = Flow.from_client_config(
                client_config=client_config,
                scopes=settings.SCOPES,
                redirect_uri='postmessage'
            )

            logger.info(f"Попытка получить токены от Google по auth_code для пользователя: {user_email}")
            # Этот вызов делает синхронный HTTP-запрос к Google
            flow.fetch_token(code=payload.auth_code)

            credentials = flow.credentials
            if not credentials or not credentials.token:
                logger.error("Не удалось получить access_token от Google.")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not obtain valid tokens from Google.")

            refresh_token = credentials.refresh_token

            # 3. Работа с базой данных
            if refresh_token:
                # Мы получили новый refresh_token. Это обычно происходит при первом логине
                # или если пользователь отозвал доступ и предоставил его заново.
                # Сохраняем или обновляем его в нашей БД.
                logger.info(f"Получен новый refresh_token для {user_email}. Сохранение в БД.")
                users_crud.upsert_user_token(
                    db=self.db,
                    google_id=user_google_id,
                    email=user_email,
                    full_name=user_full_name,
                    refresh_token=refresh_token
                )
                logger.info(f"Refresh token для {user_email} успешно сохранен/обновлен.")
            else:
                # Refresh token не пришел. Это нормальное поведение, если пользователь
                # уже давал разрешение ранее.
                logger.warning(f"Новый refresh_token для {user_email} не получен. Проверяем наличие старого в БД.")
                # Критически важно убедиться, что у нас уже есть refresh_token для этого пользователя.
                existing_user = users_crud.get_user_by_google_id(self.db, user_google_id)
                if not existing_user or not existing_user.refresh_token:
                    # Это проблемная ситуация: Google не дал токен, и у нас его нет.
                    # Пользователь не сможет работать с API в фоновом режиме.
                    logger.error(f"У пользователя {user_email} нет refresh_token в БД, и Google не предоставил новый.")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Authorization inconsistent. Please sign out from Google, revoke app access, and sign in again."
                    )
                logger.info(f"Пользователь {user_email} уже имеет refresh_token в БД. Обновление не требуется.")

            logger.info(f"Авторизация для пользователя {user_email} прошла успешно.")
            return user_email

        except GoogleAuthError as e:
            # Обработка ошибок от библиотеки Google
            error_detail = str(e)
            logger.error(f"Ошибка Google Auth при обмене кода: {error_detail}", exc_info=True)
            # 'invalid_grant' - частая ошибка, если код уже использован или redirect_uri не совпадает
            if "invalid_grant" in error_detail:
                detail_message = "Failed to exchange auth code. It might be expired, already used, or the redirect_uri is incorrect."
            else:
                detail_message = f"Google authentication error: {error_detail}"
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail_message)
            
        except Exception as e:
            # Обработка других неожиданных ошибок (например, сетевых или ошибок БД из CRUD)
            logger.error(f"Неожиданная ошибка в процессе обмена кода: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected internal error occurred.")