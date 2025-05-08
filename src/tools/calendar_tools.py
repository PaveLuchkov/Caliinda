import os
import logging

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

import shared.config as config 


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Use the specific configure method for this toolset type
calendar_tool_set.configure_auth(
    client_id=config.GOOGLE_CLIENT_ID, client_secret=config.GOOGLE_CLIENT_SECRET
)
logger.info(f"calendar_tool_set configured with app's client_id/secret.")

user_auth_credential_with_access_token = AuthCredential(
    auth_type=AuthCredentialTypes.OPEN_ID_CONNECT, # Соответствует схеме инструмента
    oauth2=OAuth2Auth(
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
        access_token=config.HARDCODED_ACCESS_TOKEN,
        scopes=config.SCOPES,
    )
)

logger.info(f"User AuthCredential with refresh token created.")
calendar_tool_set.rest_api_tool.auth_credential = user_auth_credential_with_access_token
logger.info(f"Set user_auth_credential_with_refresh directly on rest_api_tool_inside.")

calendar_check_tool = calendar_tool_set.get_tool("calendar_events_list")