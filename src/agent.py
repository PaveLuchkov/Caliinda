# Example: Configuring Google Calendar Tools
import os
from google.adk.tools.google_api_tool import calendar_tool_set
from google.adk.agents import Agent
from datetime import datetime
# @title 1. Import LiteLlm
from google.adk.models.lite_llm import LiteLlm

client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
# Use the specific configure method for this toolset type
calendar_tool_set.configure_auth(
    client_id=client_id, client_secret=client_secret
)
MODEL_OR = "openrouter/google/gemini-2.0-flash-001"
# текущее время в формате ISO 8601
now = datetime.now()
calendar_check = calendar_tool_set.get_tool("calendar_events_list")
calendar_insert = calendar_tool_set.get_tool("calendar_events_insert")
# calendar_tools = calendar_tool_set.get_tool()
# calendar_tools
root_agent = Agent(
    name="Google_Calendar_Agent",
    # model=LiteLlm(model = MODEL_OR),
    description=(
        "Agent to manage google calendars, including creating events, "
    ),
    instruction=(
        f"You are a helpful agent who can add ivents in user calendar. Now is {now}"
    ),
    tools=[calendar_check, calendar_insert]
)