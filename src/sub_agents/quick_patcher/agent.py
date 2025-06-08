from google.adk.agents import Agent

from ...shared import config as cfg

MODEL = cfg.MODEL
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

