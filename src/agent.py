import os
import logging

from google.adk.runners import Runner # Пример
from google.adk.tools.google_api_tool import calendar_tool_set
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from src.tools.calendar_tools import calendar_check_tool

import src.session as ses
import src.shared.config as config 

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# litellm._turn_on_debug()

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1" #$env:PYTHONUTF8 = "1"
MODEL = LiteLlm(model = config.MODEL_OR)

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
    app_name=ses.APP_NAME,
    session_service=ses.session_service
)