# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import sys
import os
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
    
# Импортируем наши новые роутеры
from src.auth.router import router as auth_router
from src.calendar.router import router as calendar_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



app = FastAPI(
    title="Caliinda Backend",
    description="Handles user requests via Google Calendar.",
    version="2.0.0" # Можно и версию поднять после такого рефакторинга :)
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
logger.info("Including routers...")
app.include_router(auth_router)
app.include_router(calendar_router)

@app.get("/", tags=["Status"])
def root():
    return {"message": "Caliinda Backend is running!"}

# Код для запуска через uvicorn, если нужно
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)