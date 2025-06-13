from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from ...shared import config as cfg
from ...tools import calendarLookupTools
MODEL = cfg.MODEL
from . import prompt

_events = Agent(
    name="Calendar_Lookup_Agent",
    model=MODEL,
    description=(
        "Takes query of daterange of time and returns list of events in this range. "
    ),
    instruction=prompt.TIME_FINDER,
    tools=[calendarLookupTools],
)