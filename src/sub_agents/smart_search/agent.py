from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from google.adk.models.lite_llm import LiteLlm

from ...shared import config as cfg
from ...shared import LookupOutput
from ...tools import calendarLookupTools, update_search_results, initialize_session_state
MODEL = cfg.MODEL
from . import prompt

_simple_search = Agent(
    name="Simple_searcher",
    model=MODEL,
    description=("Takes: DateRange, Format. Returns simple list of events"),
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
    instruction=prompt.SIMPLE_SEARCH,
    tools=[calendarLookupTools],
    output_key="simple_search"
)

_query_search = Agent(
    name="Query_searcher",
    model=MODEL,
    description=("Takes: DateRange, Format, Query. Returns simple list of events"),
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
    instruction=prompt.QUERY_SEARCH,
    tools=[calendarLookupTools],
    output_key="query_search"
)

_find_free_slots = Agent(
    name="Free_Slots_Finder",
    model=MODEL,
    description=("Takes: DateRange, Format, Night(Optional): Boolean. Returns list of free slots on daterange"),
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
    instruction=prompt.FREE_SLOTS,
    tools=[calendarLookupTools],
    output_key="free_slots"
)

_find_conflicts = Agent(
    name="Conflicts_Checker",
    model=MODEL,
    description=("Takes: DateRange. Returns report on conflicts"),
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
    instruction=prompt.FIND_CONFLICTS,
    tools=[calendarLookupTools],
    output_key="conflicts_report"
)


_analytics = Agent(
    name="Calendar_Analytic",
    model=MODEL,
    description=("Takes: DateRange, Intent: Boolean. Returns analytics of events/habits based on daterange"),
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
    instruction=prompt.ANALYTICS,
    tools=[
        AgentTool(agent=_simple_search),
        AgentTool(agent=_query_search)
    ],
    output_key="analytics"
)



_smart_search = Agent(
    name="Smart_Search",
    model=MODEL,
    description=(
        "Uses toolAgents to return the best calendar search results"
    ),
    instruction=prompt.SMART_SEARCH,
    tools=[
        AgentTool(agent=_simple_search),
        AgentTool(agent=_query_search),
        AgentTool(agent=_find_free_slots),
        AgentTool(agent=_find_conflicts),
        AgentTool(agent=_analytics),

    ],
    output_key="search_result",



    before_agent_callback=initialize_session_state,
    # after_agent_callback=update_search_results
)