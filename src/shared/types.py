from pydantic import BaseModel

class TokenExchangeRequest(BaseModel):
    id_token: str
    auth_code: str
# --- Helper Functions ---