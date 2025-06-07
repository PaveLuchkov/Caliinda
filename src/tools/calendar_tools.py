import logging
from google.adk.tools.base_toolset import ToolPredicate
from .google_api_tset import GoogleApiToolsetCustom

from typing import List
from typing import Optional
from typing import Union

from src.auth.google_token import get_access_token_from_refresh
import src.shared.config as cfg


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class CalendarToolset(GoogleApiToolsetCustom):
  """Auto-generated Calendar toolset based on Google Calendar API v3 spec exposed by Google API discovery API"""

  def __init__(
      self,
      access_token: str = None,
      tool_filter: Optional[Union[ToolPredicate, List[str]]] = None,
  ):
    super().__init__("calendar", "v3", access_token, tool_filter)

access_token = get_access_token_from_refresh(
    refresh_token=cfg.HARDCODED_REFRESH_TOKEN,
    client_id=cfg.GOOGLE_CLIENT_ID,
    client_secret=cfg.GOOGLE_CLIENT_SECRET,
    token_uri=cfg.TOKEN_URI,
    scopes=cfg.SCOPES
)

calendar_tool_instance = CalendarToolset(access_token=access_token)
calendar_insert_tool = CalendarToolset(access_token=access_token, tool_filter=["calendar_events_insert"])