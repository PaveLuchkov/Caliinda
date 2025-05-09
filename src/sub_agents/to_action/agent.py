from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

import src.shared.config as config 

MODEL = LiteLlm(model = config.MODEL_OR)


calendar_action = Agent(
    name="Google_Calendar_Agent",
    model=MODEL,
    description=(
        "Agent for making calendar actions based on user query"
    ),
    instruction=(
        f"You mockup agent. Just return 'WRONG AGENT'"
    ),
    tools=[]
)