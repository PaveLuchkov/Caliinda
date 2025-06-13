from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from ...shared import config as cfg
from ...tools import calendarLookupTools, update_search_results
MODEL = cfg.MODEL
from . import prompt

_lookup = Agent(
    name="Calendar_Lookup_Agent",
    model=MODEL,
    description=(
        "Takes query of daterange of time and returns list of events in this range. "
    ),
    instruction=prompt.LOOKUP,
    tools=[calendarLookupTools],
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
    include_contents = False,
    output_key="search_result",
    after_agent_callback=update_search_results
)