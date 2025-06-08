from google.adk.agents import Agent

from ...shared import config as cfg

MODEL = cfg.MODEL
from . import prompt
from src.tools.calendar_tools import calendar_create_event, calendar_delete_event, calendar_edit_event



quick_patcher = Agent(
    name="Quick_Calendar_Agent",
    model=MODEL,
    description=(
        "Agent who can create delete and edit calendar events quickly based on user input. Specified for one action at a time. "
    ),
    instruction=prompt.QUICK_PATCHER,
    tools=[calendar_create_event, calendar_delete_event, calendar_edit_event],
)
