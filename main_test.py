# main_test.py
from fastapi import FastAPI
import logging

# Импортируем ТОЛЬКО роутер аутентификации
from src.auth.router import router as auth_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Test App")

logger.info("Including ONLY the auth router...")
app.include_router(auth_router)
logger.info("Auth router included.")

@app.get("/")
def root():
    return {"message": "Test server is running!"}