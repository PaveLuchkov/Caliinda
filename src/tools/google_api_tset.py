
from google.adk.tools.google_api_tool.googleapi_to_openapi_converter import GoogleApiToOpenApiConverter
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.auth import OpenIdConnectWithConfig
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.base_toolset import ToolPredicate
from google.adk.tools.openapi_tool import OpenAPIToolset

from .google_api_tool import GoogleApiToolHttp

from typing_extensions import override

from typing import List
from typing import Optional
from typing import Union


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