import logging
from google.adk.tools.agent_tool import AgentTool
from google.adk.agents import Agent
import litellm
from src.tools.state import initialize_session_state
from . import prompt

from .shared import config as cfg
# from src.tools.agent_to_tool import time_finder_tool

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

litellm._turn_on_debug()
#$env:PYTHONUTF8 = "1"
# after_tool_callback=update_tasks

_reviewer = Agent(
    name="Story_takes",
    model=cfg.MODEL,
    description=(
        "Agent who takes story to review it"
    ),
    instruction=prompt.REVIEW,
    output_key="story",
    # after_agent_callback=update_tasks,
)

story_reviewer=AgentTool(agent=_reviewer)

root_agent = Agent(
    name="Main_Agent",
    model=cfg.MODEL,
    description=(
        "Agent for creating story from single-word user request. "
    ),
    instruction=(
        f"You writting a story based on single-word user request. Provide your story to story_reviewer agent for review. If story is good return it to user. Rules: -your first step is always tool call with request of your story provided. Do not mention that there is review needed or past for user. Provide story only after it is reviewed and approved by story_reviewer agent. "
    ),
    tools=[story_reviewer],
    #sub_agents = [quick_patcher],
    before_agent_callback=initialize_session_state,
)


