from google.adk.tools import BaseTool
from google.adk.auth import AuthCredential
from google.adk.auth import AuthCredentialTypes
from google.adk.auth.auth_credential import HttpAuth, HttpCredentials
from google.adk.tools.openapi_tool import RestApiTool
from google.adk.tools.tool_context import ToolContext

from google.genai.types import FunctionDeclaration

from typing_extensions import override

from typing import Any
from typing import Optional
from typing import Dict

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