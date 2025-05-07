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
# calendar_tool_set.configure_auth(
#     client_id=client_id, client_secret=client_secret
# )

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
actionHandler = Agent(
    name="ActionHandler",
    model=GEMINI_MODEL,
    description=(
        "Agent taking concrete tasks to make actions"
    ),
    instruction=(
        f"You are agent who response to user query as 'done' nevertheless what user asks"
    ),
)

storyCreation = Agent(
    name="StoryCreator",
    model=GEMINI_MODEL,
    description=(
        "Agent responsible for creating short stories based on user input"
    ),
    instruction=(
        f"Create a very short story based on the user's query. Ensure the story is concise and directly related to the input."
    ),
    output_key="story",
)

storyChecker = Agent(
    name="StoryChecker",
    model=GEMINI_MODEL,
    description=(
        "Agent responsible for verifying the relevance of created stories"
    ),
    instruction=(
        f"Check if the following story is based on the user's query. Respond with 'Yes' if it is relevant, or 'No' if it is not. "
        f"Here is the story: {{story}}."
    ),
    output_key="story_check",
)

storyRefactor = Agent(
    name="StoryRefactorer",
    model=GEMINI_MODEL,
    description=(
        "Agent responsible for refining and improving created stories"
    ),
    instruction=(
        f"Refactor the following story to improve its quality while keeping it aligned with the user's query. "
        f"Here is the story: {{story}}. Here is the relevance check result: {{story_check}}. "
        f"if relevance check result is 'No' then refactor the story to make it relevant. "
        f"if relevance check result is 'Yes' then output the story as is. "
    ),
    output_key="story_refactored",
)

story_agent = SequentialAgent(
    name="StoryPipelineAgent",
    sub_agents=[storyCreation, storyChecker, storyRefactor],
    description="Executes a sequence of story creation, verification, and refinement",
)

root_agent = LlmAgent(
    name="Main_Agent",
    model=GEMINI_MODEL,
    description=(
        "Agent for Orchestrating"
    ),
    instruction=(
        f"Ты ассистент, который может управлять календарем Google.  И может добавлять события"
    ),
    sub_agents= [story_agent, actionHandler]
)


