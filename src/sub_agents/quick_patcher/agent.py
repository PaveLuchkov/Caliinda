from google.adk.agents import Agent
from ...shared import config as cfg
from . import prompt
from ...tools import calendarActionTools

MODEL = cfg.MODEL

_calendar_handler = Agent(
    name="Calendar_Agent",
    model=MODEL,
    description=(
        "Agent who can create delete and edit calendar events"
    ),
    instruction=prompt.QUICK_PATCHER, 
    tools=[calendarActionTools] #TODO надо добавить тул просмотра календаря - агента. Указать агента в промпте
    # TODO для нового агента нужно добавить обработку состояния сессии и обновление последних полученных данных.
)
