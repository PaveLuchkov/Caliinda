import logging
from google.adk.tools.agent_tool import AgentTool
from google.adk.agents import Agent
import litellm

from .tools import initialize_session_state, calendarActionTools, calendarCreateTool, calendarLookupTools, update_search_results
from . import prompt
from .sub_agents import _calendar_handler, _smart_search
from .shared import config as cfg
# from src.tools.agent_to_tool import time_finder_tool

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

litellm._turn_on_debug()
#$env:PYTHONUTF8 = "1"

calendar_action=AgentTool(agent=_calendar_handler)

# root_agent = Agent(
#     name="Main_Agent",
#     model=cfg.MODEL,
#     description=(
#         "Agent for calendar related activities"
#     ),
#     instruction=prompt.MAIN,
#     tools=[calendar_action],
#     #sub_agents = [planner], TODO сделать планнера
#     before_agent_callback=initialize_session_state,
# )
# root_agent = Agent(
#     name="Calendar_Action_Agent",
#     model=cfg.MODEL,
#     description=(
#         "Agent who can create delete and edit calendar events"
#     ),
#     instruction=prompt.CALENDAR_HANDLER, 
#     tools=[
#         calendarActionTools,
#         AgentTool(agent=_lookup, skip_summarization=False)
#         ],
#     output_key='action_report',
#     before_agent_callback=initialize_session_state,
# )

root_agent = _smart_search