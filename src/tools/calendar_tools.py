import os
import logging
from google.adk.tools.google_api_tool.googleapi_to_openapi_converter import GoogleApiToOpenApiConverter
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.auth import OpenIdConnectWithConfig
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.base_toolset import ToolPredicate
from google.adk.tools.openapi_tool import OpenAPIToolset

from google.adk.tools import BaseTool
from google.adk.auth import AuthCredential
from google.adk.auth import AuthCredentialTypes
from google.adk.auth.auth_credential import HttpAuth, HttpCredentials
from google.adk.tools.openapi_tool import RestApiTool
from google.adk.tools.tool_context import ToolContext

from google.genai.types import FunctionDeclaration

from typing_extensions import override

import inspect
import os
from typing import Any
from typing import List
from typing import Optional
from typing import Type
from typing import Union
from typing import Dict

from src.auth.google_token import get_access_token_from_refresh
import src.shared.config as cfg
from src.tools.tools_auth import configure_calendar_tools


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

access_token = get_access_token_from_refresh(
    refresh_token=cfg.HARDCODED_REFRESH_TOKEN,
    client_id=cfg.GOOGLE_CLIENT_ID,
    client_secret=cfg.GOOGLE_CLIENT_SECRET,
    token_uri=cfg.TOKEN_URI,
    scopes=cfg.SCOPES
)

class GoogleApiToolHttp(BaseTool):

  def __init__(
      self,
      rest_api_tool: RestApiTool,
      access_token: Optional[str] = None,
  ):
    super().__init__(
        name=rest_api_tool.name,
        description=rest_api_tool.description,
        is_long_running=rest_api_tool.is_long_running,
    )
    self._rest_api_tool = rest_api_tool
    self.configure_auth(access_token)

  @override
  def _get_declaration(self) -> FunctionDeclaration:
    return self._rest_api_tool._get_declaration()

  @override
  async def run_async(
      self, *, args: dict[str, Any], tool_context: Optional[ToolContext]
  ) -> Dict[str, Any]:
    return await self._rest_api_tool.run_async(
        args=args, tool_context=tool_context
    )

  def configure_auth(self, access_token: str):
    self._rest_api_tool.auth_credential = AuthCredential(
        auth_type=AuthCredentialTypes.HTTP,
        http=HttpAuth(
          scheme="bearer",
          credentials=HttpCredentials(token=access_token),
      ),
    )

class GoogleApiToolsetCustom(BaseToolset):
  """Google API Toolset contains tools for interacting with Google APIs.

  Usually one toolsets will contains tools only related to one Google API, e.g.
  Google Bigquery API toolset will contains tools only related to Google
  Bigquery API, like list dataset tool, list table tool etc.
  """

  def __init__(
      self,
      api_name: str,
      api_version: str,
      access_token: Optional[str] = None,
      tool_filter: Optional[Union[ToolPredicate, List[str]]] = None,
  ):
    self.api_name = api_name
    self.api_version = api_version
    self._access_token = access_token
    self._openapi_toolset = self._load_toolset_with_oidc_auth()
    self.tool_filter = tool_filter

  @override
  async def get_tools(
      self, readonly_context: Optional[ReadonlyContext] = None
  ) -> List[GoogleApiToolHttp]:
    """Get all tools in the toolset."""

    return [
        GoogleApiToolHttp(tool, self._access_token)
        for tool in await self._openapi_toolset.get_tools(readonly_context)
        if self._is_tool_selected(tool, readonly_context)
    ]

  def set_tool_filter(self, tool_filter: Union[ToolPredicate, List[str]]):
    self.tool_filter = tool_filter

  def _load_toolset_with_oidc_auth(self) -> OpenAPIToolset:
    spec_dict = GoogleApiToOpenApiConverter(
        self.api_name, self.api_version
    ).convert()
    scope = list(
        spec_dict['components']['securitySchemes']['oauth2']['flows'][
            'authorizationCode'
        ]['scopes'].keys()
    )[0]
    return OpenAPIToolset(
        spec_dict=spec_dict,
        spec_str_type='yaml',
        auth_scheme=OpenIdConnectWithConfig(
            authorization_endpoint=(
                'https://accounts.google.com/o/oauth2/v2/auth'
            ),
            token_endpoint='https://oauth2.googleapis.com/token',
            userinfo_endpoint=(
                'https://openidconnect.googleapis.com/v1/userinfo'
            ),
            revocation_endpoint='https://oauth2.googleapis.com/revoke',
            token_endpoint_auth_methods_supported=[
                'client_secret_post',
                'client_secret_basic',
            ],
            grant_types_supported=['authorization_code'],
            scopes=[scope],
        ),
    )

  def configure_auth(self, access_token: str):
    self._access_token = access_token

  @override
  async def close(self):
    if self._openapi_toolset:
      await self._openapi_toolset.close()
