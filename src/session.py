import logging
from google.adk.sessions import InMemorySessionService, Session as ADKSession

import src.shared.config as cfg 

session_service = InMemorySessionService()

APP_NAME = "caliinda"
USER_ID_FOR_SESSION = "112812348232829088110"
SESSION_ID = "session_001"

adk_user_session: ADKSession = session_service.get_session(
    app_name=APP_NAME, user_id=cfg.TEST_USER_GOOGLE_ID, session_id=SESSION_ID
)
if not adk_user_session:
    adk_user_session = session_service.create_session(
        app_name=APP_NAME,
        user_id=cfg.TEST_USER_GOOGLE_ID,
        session_id=SESSION_ID
    )