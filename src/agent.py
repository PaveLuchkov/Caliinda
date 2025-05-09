import os
import logging

from google.adk.runners import Runner # Пример
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

import src.session as ses
import src.shared.config as config 
from .sub_agents import planner, calendar_action

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
        f"You assistant. Delegate user query to planner if user wants to make plans and calendar_action if has concrete task to do in calendar"
    ),
    sub_agents = [planner, calendar_action]
)

runner = Runner(
    agent=root_agent,
    app_name=ses.APP_NAME,
    session_service=ses.session_service
)