import os
import logging

from google.adk.runners import Runner # Пример
from google.adk.sessions import InMemorySessionService, Session as ADKSession
from google.adk.tools.google_api_tool import calendar_tool_set
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from tools.calendar_tools import calendar_check_tool

import shared.config as config 

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# litellm._turn_on_debug()

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1" #$env:PYTHONUTF8 = "1"
MODEL = LiteLlm(model = config.MODEL_OR)


session_service = InMemorySessionService()

APP_NAME = "caliinda"
USER_ID_FOR_SESSION = "112812348232829088110"
SESSION_ID = "session_001"

adk_user_session: ADKSession = session_service.get_session(
    app_name=APP_NAME, user_id=config.TEST_USER_GOOGLE_ID, session_id=SESSION_ID
)
if not adk_user_session:
    adk_user_session = session_service.create_session(
        app_name=APP_NAME,
        user_id=TEST_USER_GOOGLE_ID,
        session_id=SESSION_ID
    )

root_agent = Agent(
    name="Google_Calendar_Agent",
    model=MODEL,
    description=(
        "Agent for Orchestrating"
    ),
    instruction=(
        f"You are a assistant that provides event list from Google Calendar On date using 'calendar_check_tool'"
    ),
    tools=[calendar_check_tool]
)

runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service
)