from datetime import datetime
from google.adk.sessions import InMemorySessionService, Session as ADKSession

import src.shared.config as cfg 

session_service = InMemorySessionService()

APP_NAME, USER_ID_FOR_SESSION, SESSION_ID = "caliinda", "112812348232829088110", "session_001"
current_user_time, user_timezone, user_prefered_calendar = datetime.now().replace(microsecond=0), "Asia/Yekaterinburg", "primary"

adk_user_session: ADKSession = session_service.get_session(
    app_name=APP_NAME, user_id=cfg.TEST_USER_GOOGLE_ID, session_id=SESSION_ID
)
if not adk_user_session:
    adk_user_session = session_service.create_session(
        app_name=APP_NAME,
        user_id=cfg.TEST_USER_GOOGLE_ID,
        session_id=SESSION_ID,
        state={
            "current_user_time": current_user_time,
            "user_timezone": user_timezone,
            "user_prefered_calendar": user_prefered_calendar,
        },
    )