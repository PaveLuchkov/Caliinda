from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from ....shared import config as cfg

MODEL = cfg.MODEL
from . import prompt
# from src.tools.calendar_tools import event_list

# time_finder = Agent(
#     name="Time_Finder",
#     model=MODEL,
#     description=(
#         "Takes query of user for time analyzing for datetime range and gives users free time and probable usage of it."
#     ),
#     instruction=prompt.TIME_FINDER,
#     tools=[event_list],
# )