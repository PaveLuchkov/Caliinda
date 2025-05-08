
# fastapi_backend.py
import datetime
from fastapi import FastAPI, HTTPException, Depends, Header, Query, File, UploadFile, Form, status
from fastapi.middleware.cors import CORSMiddleware
from grpc import Status
from mcp import Resource
from pydantic import BaseModel
import os
import logging
from typing import Dict, List, Optional

# Google Auth Libraries
from google.oauth2 import id_token, credentials
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow
from googleapiclient.errors import HttpError

# --- Импорт локальных модулей ---
from sqlalchemy.orm import Session # Тип для сессии БД
from pydantic import BaseModel, Field, field_validator
from fastapi import FastAPI, Depends, HTTPException, Body
from google.oauth2.credentials import Credentials  # Для работы с Credentials
from googleapiclient.discovery import build

from google.adk.runners import Runner # Пример
from google.adk.sessions import InMemorySessionService, Session as ADKSession
from google.adk.tools.google_api_tool import calendar_tool_set
from google.adk.auth import AuthCredentialTypes, OAuth2Auth # Важные классы
from google.adk.agents import Agent
from google.adk.auth import (
    AuthConfig,
    AuthCredential,
    AuthCredentialTypes,
    OAuth2Auth,
)
from google.adk.models.lite_llm import LiteLlm

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

import litellm
from zoneinfo import ZoneInfo

# litellm._turn_on_debug()

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1" #$env:PYTHONUTF8 = "1"
MODEL_OR = "openrouter/google/gemini-2.0-flash-001"

# --- ЗАХАРДКОЖЕННЫЕ ДАННЫЕ ДЛЯ ТЕСТА ---
# !!! ЗАМЕНИ ЭТИ ЗНАЧЕНИЯ СВОИМИ РЕАЛЬНЫМИ ДАННЫМИ !!!
TEST_USER_GOOGLE_ID = "112812348232829088110"
TEST_USER_EMAIL = "sliderlaad222@gmail.com"
HARDCODED_REFRESH_TOKEN = "1//0cvsbPdJWXduWCgYIARAAGAwSNwF-L9IrO1wnpaFzPQ7bp1O0gsiTE3qlv8cYqWyPMjYjHG6seTqX83R-WvUPUvbljzk9PCcKaIo" # !!! ЗАМЕНИ ЭТО !!!
HARDCODED_SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
HARDCODED_ACCESS_TOKEN = "ya29.a0AZYkNZgpig6NbDlleW8_9FDycGj5e6q5EtKYR-64kmZONJp4SM0VTgd6EPhJnEYDBoA9wldOqtABNimWNk4XhLONtOzx7GGilLU0HzCxc-XXS5IFiR2L_pXIoka6lI4WUJP7eBqCsSsAI_xh-RSkImWyPhzDZc-1aF__omTKaCgYKAW8SARQSFQHGX2MiKUY3LPQKbN-RLCb48ZBtCQ0175"
client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")

client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
# Use the specific configure method for this toolset type
calendar_tool_set.configure_auth(
    client_id=client_id, client_secret=client_secret
)
logger.info(f"calendar_tool_set configured with app's client_id/secret.")

calendar_check_tool = calendar_tool_set.get_tool("calendar_events_list")
rest_api_tool_inside = calendar_check_tool.rest_api_tool

user_auth_credential_with_access_token = AuthCredential(
    auth_type=AuthCredentialTypes.OPEN_ID_CONNECT, # Соответствует схеме инструмента
    oauth2=OAuth2Auth(
        client_id=client_id,
        client_secret=client_secret,
        access_token=HARDCODED_ACCESS_TOKEN,
#         refresh_token=HARDCODED_REFRESH_TOKEN,
#         token_uri=TOKEN_URI, 
        scopes=HARDCODED_SCOPES,
    )
)

logger.info(f"User AuthCredential with refresh token created.")
rest_api_tool_inside.auth_credential = user_auth_credential_with_access_token
logger.info(f"Set user_auth_credential_with_refresh directly on rest_api_tool_inside.")

session_service = InMemorySessionService()

APP_NAME = "caliinda"
USER_ID_FOR_SESSION = "112812348232829088110" # Используется GOOGLE ID sldierla
SESSION_ID = "session_001" # Using a fixed ID for simplicity
adk_user_session: ADKSession = session_service.get_session(
    app_name=APP_NAME, user_id=USER_ID_FOR_SESSION, session_id=SESSION_ID
)
if not adk_user_session:
    adk_user_session = session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID_FOR_SESSION,
        session_id=SESSION_ID
    )



root_agent = Agent(
    name="Google_Calendar_Agent",
    model=LiteLlm(model = MODEL_OR),
    description=(
        "Agent for Orchestrating"
    ),
    instruction=(
        f"You are a assistant that provides event list from Google Calendar On date using 'calendar_check_tool'"
    ),
    tools=[calendar_check_tool]
)

runner = Runner(
    agent=root_agent, # The agent we want to run
    app_name=APP_NAME,   # Associates runs with our app
    session_service=session_service # Uses our session manager
)