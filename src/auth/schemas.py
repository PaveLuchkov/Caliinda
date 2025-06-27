# src/auth/schemas.py
from pydantic import BaseModel

class TokenExchangeRequest(BaseModel):
    id_token: str
    auth_code: str

class AuthSuccessResponse(BaseModel):
    status: str = "success"
    message: str = "Authorization successful."
    user_email: str