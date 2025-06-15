from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from ...shared import config as cfg
from ...shared import LookupOutput
from ...tools import calendarLookupTools, update_search_results
MODEL = cfg.MODEL
from . import prompt

_lookup = Agent(
    name="Calendar_Lookup_Agent",
    model=MODEL,
    description=(
        "Returns list of events in range, requires DateTime start and Datetime End. "
    ),
    instruction=prompt.SMART_SEARCH,
    tools=[calendarLookupTools],
    # output_schema=LookupOutput,
    output_key="search_result",
    # after_agent_callback=update_search_results
)