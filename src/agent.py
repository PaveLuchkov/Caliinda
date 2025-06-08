import os
import logging

from google.adk.runners import Runner # Пример
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.agents.callback_context import CallbackContext
from datetime import datetime
import litellm
from src.tools.state import initialize_session_state

from .shared import config as cfg
from .sub_agents import quick_patcher
# from src.tools.agent_to_tool import time_finder_tool

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

litellm._turn_on_debug()
#$env:PYTHONUTF8 = "1"

root_agent = Agent(
    name="Main_Router_Agent",
    model=cfg.MODEL,
    description=(
        "Agent for Orchestrating user requests related to Google Calendar"
    ),
    instruction=(
        f"You are main router. Route user requests to one of the sub_agents which can handle specific tasks."
    ),
    sub_agents = [quick_patcher],
    before_agent_callback=initialize_session_state
)