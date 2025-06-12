import os
import logging
from google.adk.tools.agent_tool import AgentTool
from google.adk.runners import Runner # Пример
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.agents.callback_context import CallbackContext
from datetime import datetime
import litellm
from src.tools.state import initialize_session_state, update_tasks
from . import prompt

from .shared import config as cfg
from .sub_agents import quick_patcher
# from src.tools.agent_to_tool import time_finder_tool

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

litellm._turn_on_debug()
#$env:PYTHONUTF8 = "1"
# after_tool_callback=update_tasks

task_manager = Agent(
    name="Task_Manager",
    model=cfg.MODEL,
    description=(
        "Agent who splits user request"
    ),
    instruction=prompt.TASK_MANAGER,
    output_key="tasks",
    after_agent_callback=update_tasks,
)

task_tool=AgentTool(agent=task_manager)

root_agent = Agent(
    name="Main_Agent",
    model=cfg.MODEL,
    description=(
        "Agent for Orchestrating user requests by pulling its requests to task-manager"
    ),
    instruction=(
        f"You are main router. Before routing user request to one of your sub-agents you MUST call task_tool to split tasks of user request. NEXT Route user requests to one of the sub_agents: {quick_patcher.name} "
    ),
    tools=[task_tool],
    sub_agents = [quick_patcher],
    before_agent_callback=initialize_session_state,
)


