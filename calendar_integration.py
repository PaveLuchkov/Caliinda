from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import os

def create_calendar_event(event_data: dict, google_token: str):
    try:
        creds = Credentials(
            token=google_token,
            refresh_token=os.getenv("GOOGLE_REFRESH_TOKEN"),
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            token_uri="https://oauth2.googleapis.com/token"
        )
        
        # Обязательное обновление токена
        if creds.expired:
            creds.refresh(Request())

        service = build("calendar", "v3", credentials=creds)

        # Проверка календаря
        calendar = service.calendars().get(calendarId='primary').execute()
        print(f"Событие добавится в календарь: {calendar['summary']}")  # Для отладки

        event = {
            "summary": event_data["event_name"],
            "start": {"dateTime": f"{event_data['date']}T{event_data['time']}:00", "timeZone": "Europe/Moscow"},
            "end": {"dateTime": f"{event_data['date']}T{event_data['time']}:00", "timeZone": "Europe/Moscow"},
        }
        
        service.events().insert(
            calendarId="primary",
            body=event
        ).execute()
        
    except Exception as e:
        raise Exception(f"Calendar error: {str(e)}")