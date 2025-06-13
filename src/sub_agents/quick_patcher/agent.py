from google.adk.agents import Agent

from ...shared import config as cfg

MODEL = cfg.MODEL
from . import prompt
from src.tools.calendar_tools import calendarActionTools



_calendar_handler = Agent(
    name="Calendar_Agent",
    model=MODEL,
    description=(
        "Agent who can create delete and edit calendar events"
    ),
    instruction=prompt.QUICK_PATCHER,
    tools=[calendarActionTools]
)
