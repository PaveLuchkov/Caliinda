from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

import src.shared.config as config 
# from src.tools.calendar_tools import event_list, insert, edit, delete

MODEL = LiteLlm(model = config.MODEL_OR)


# calendar_action = Agent(
#     name="Google_Calendar_Agent",
#     model=MODEL,
#     description=(
#         "Agent for making calendar actions based on user query"
#     ),
#     instruction=(
#         f"You agent who uses event_list, insert, edit, delete tools to make calendar actions based on user query. "
#         "You should use event_list tool to get all events in calendar, then you can use insert tool to add new event, edit tool to change existing event and delete tool to remove event. "
#     ),
#     tools=[event_list, insert, edit, delete]
# )