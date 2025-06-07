import os
import logging

from google.adk.runners import Runner # Пример
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
import litellm

import src.session as ses
from .shared import config as cfg
# from .sub_agents import planner, calendar_action
# from src.tools.agent_to_tool import time_finder_tool
from src.tools.calendar_tools import calendar_tool_instance, calendar_insert_tool


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

litellm._turn_on_debug()

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1" #$env:PYTHONUTF8 = "1"

# root_agent = Agent(
#     name="Google_Calendar_Agent",
#     model=cfg.MODEL,
#     description=(
#         "Agent for Orchestrating"
#     ),
#     instruction=(
#         f"You assistant. Delegate user query to planner if user wants to make plans and calendar_action if has concrete task to do in calendar"
#     ),
#     sub_agents = [planner, calendar_action]
# )


root_agent = Agent(
    name="Google_Calendar_Agent",
    model=cfg.MODEL,
    description=(
        "Agent for using calendar tools"
    ),
    instruction=(
        f"You assistant."
    ),
    # sub_agents = []
    tools=[calendar_insert_tool]  # Используем сконфигурированный инструмент
)

runner = Runner(
    agent=root_agent,
    app_name=ses.APP_NAME,
    session_service=ses.session_service
)