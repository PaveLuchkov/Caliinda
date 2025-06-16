from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from . import prompt
from ..smart_search import _smart_search
from ...shared import config as cfg
from ...tools import calendarActionTools


MODEL = cfg.MODEL

_decomposer = Agent(
    name="Decomposer",
    model=MODEL,
    description=(
        "Agent who can create decomposed plan of user request"
    ),
    instruction=prompt.Decomposer, 
    output_key='plan',
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
