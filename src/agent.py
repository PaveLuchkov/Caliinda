# Example: Configuring Google Calendar Tools
import os
from google.adk.tools.google_api_tool import calendar_tool_set
from google.adk.agents import Agent #google-adk
from datetime import datetime
# @title 1. Import LiteLlm
from google.adk.models.lite_llm import LiteLlm
import litellm
from zoneinfo import ZoneInfo
import sys

litellm._turn_on_debug()

if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"

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
calendar_update = calendar_tool_set.get_tool("calendar_events_update")

def get_current_time(city: str) -> dict:
    """Returns the current time in a specified city.

    Args:
        city (str): The name of the city for which to retrieve the current time.

    Returns:
        dict: status and result or error msg.
    """

    if city.lower() == "new york":
        tz_identifier = "America/New_York"
    else:
        return {
            "status": "error",
            "error_message": (
                f"Sorry, I don't have timezone information for {city}."
            ),
        }

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    report = (
        f'The current time in {city} is {now.strftime("%Y-%m-%d %H:%M:%S %Z%z")}'
    )
    return {"status": "success", "report": report}

# calendar_tools = calendar_tool_set.get_tool()
# calendar_tools
root_agent = Agent(
    name="Google_Calendar_Agent",
    model=LiteLlm(model = MODEL_OR),
    description=(
        "Agent to manage google calendars, including creating events, "
    ),
    instruction=(
        f"Ты ассистент, который может управлять календарем Google.  И может добавлять события"
    ),
    tools=[calendar_insert]
)


