from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from . import prompt
from ..lookup import _lookup
from ...shared import config as cfg
from ...tools import calendarActionTools


MODEL = cfg.MODEL

_calendar_handler = Agent(
    name="Calendar_Agent",
    model=MODEL,
    description=(
        "Agent who can create delete and edit calendar events"
    ),
    instruction=prompt.QUICK_PATCHER, 
    tools=[
        calendarActionTools,
        AgentTool(agent=_lookup)
        ],
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
