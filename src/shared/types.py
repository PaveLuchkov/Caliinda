from pydantic import BaseModel
from typing import List, Dict, Any, Union
from enum import Enum
from pydantic import Field

class TokenExchangeRequest(BaseModel):
    id_token: str
    auth_code: str
# --- Helper Functions ---