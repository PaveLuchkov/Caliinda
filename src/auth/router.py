# src/auth/router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from . import schemas, service
from src.core.dependencies import get_db

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

@router.post("/google/exchange", response_model=schemas.AuthSuccessResponse)
async def auth_google_exchange(
    payload: schemas.TokenExchangeRequest, db: Session = Depends(get_db)
):
    auth_service = service.AuthService(db)
    try:
        user_email = await auth_service.exchange_auth_code(payload)
        return schemas.AuthSuccessResponse(user_email=user_email)
    except HTTPException as e:
        raise e
    except Exception as e:
        # Логгирование
        raise HTTPException(status_code=500, detail=str(e))