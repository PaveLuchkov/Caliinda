from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import agent_tool

from ...shared import config as cfg

MODEL = LiteLlm(model = cfg.MODEL_OR)
from . import prompt
from src.tools.agent_to_tool import time_finder_tool


planner = Agent(
    name="Agent_for_planning",
    model=MODEL,
    description=(
        "Talks with user trying to evaluate concrete plan of events"
    ),
    instruction=prompt.PLAN_AGENT_MAIN,
    tools=[time_finder_tool]
)

