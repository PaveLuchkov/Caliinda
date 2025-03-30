from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os

def create_calendar_event(event_data):
    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    
    flow = InstalledAppFlow.from_client_secrets_file(
        os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json'),
        SCOPES
    )
    creds = flow.run_local_server(port=0)
    
    service = build("calendar", "v3", credentials=creds)
    
    event = {
        "summary": event_data["event_name"],
        "start": {
            "dateTime": f"{event_data['date']}T{event_data['time']}:00",
            "timeZone": "Europe/Moscow",
        },
        "end": {
            "dateTime": f"{event_data['date']}T{event_data['time']}:00",
            "timeZone": "Europe/Moscow",
        },
    }
    
    service.events().insert(calendarId="primary", body=event).execute()