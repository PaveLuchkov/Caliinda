from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from . import prompt
from ..smart_search import _smart_search
from ...shared import config as cfg
from ...tools import calendarActionTools


MODEL = cfg.MODEL

# _create = Agent(
#     name="Calendar_Lookup_Agent",
#     model=MODEL,
#     description=(
#         "Takes query for creating events"
#     ),
#     instruction=prompt.LOOKUP,
#     tools=[calendarLookupTools],
#     disallow_transfer_to_parent=True,
#     disallow_transfer_to_peers=True,
#     include_contents ='none',
#     output_key="search_result",
#     after_agent_callback=update_search_results
# )

_calendar_handler = Agent(
    name="Calendar_Action_Agent",
    model=MODEL,
    description=(
        "Agent who can create delete and edit calendar events"
    ),
    instruction=prompt.CALENDAR_HANDLER, 
    tools=[
        calendarActionTools,
        AgentTool(agent=_smart_search)
        ],
    output_key='action_report',
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
