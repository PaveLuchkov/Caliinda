from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import traceback
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_calendar_event(event_data: dict, user_credentials: Credentials):
    """
    Creates a Google Calendar event using the provided user credentials.

    Args:
        event_data: Dictionary containing event details ('event_name', 'date', 'time').
        user_credentials: An instance of google.oauth2.credentials.Credentials
                          obtained for the specific user (likely via refresh token).
    Returns:
        The created event object from the Google Calendar API, including the htmlLink.
    Raises:
        Exception: If there's an error interacting with the Calendar API or refreshing credentials.
    """
    try:
        creds = user_credentials

        if creds.expired and creds.refresh_token:
            logger.info("Credentials expired, attempting refresh.")
            try:
                creds.refresh(Request())
                logger.info("Credentials refreshed successfully.")
            except Exception as refresh_error:
                logger.error(f"Failed to refresh credentials: {refresh_error}")
                raise Exception(f"Failed to refresh credentials: {refresh_error}")
        elif not creds.token and not creds.refresh_token:
             raise ValueError("User credentials lack a valid token or refresh token.")
        elif not creds.valid:
             logger.warning("Credentials are not valid (may lack token or be expired without refresh token). Attempting API call anyway.")

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        # Optional: Get calendar info for logging
        try:
            calendar = service.calendars().get(calendarId='primary').execute()
            logger.info(f"Event will be added to calendar: {calendar['summary']}")
        except Exception as cal_get_err:
            logger.warning(f"Could not get primary calendar summary: {cal_get_err}")


        # TODO: Add error handling for missing keys in event_data
        start_datetime = f"{event_data['date']}T{event_data.get('time', '09:00')}:00" # Default time if missing
        # Assume a 1-hour duration if end time is not specified by LLM
        # You might want more sophisticated duration logic
        from datetime import datetime, timedelta
        try:
            start_dt_obj = datetime.fromisoformat(start_datetime)
            end_dt_obj = start_dt_obj + timedelta(hours=1)
            end_datetime = end_dt_obj.isoformat()
        except ValueError:
             logger.error(f"Invalid date/time format from LLM: {start_datetime}. Using fallback.")
             # Fallback if parsing fails - adjust as needed
             start_datetime = f"{event_data['date']}T09:00:00"
             end_datetime = f"{event_data['date']}T10:00:00"


        event = {
            "summary": event_data.get("event_name", "New Event"), # Default name
            # Ensure you have a default timezone or get it from user profile if possible
            # TODO: СДЕЛАТЬ ПОЛУЧЕНИЕ НУЖНОГО ЧАСОВОГО ПОЯСА
            "start": {"dateTime": start_datetime, "timeZone": "Asia/Yekaterinburg"},
            "end": {"dateTime": end_datetime, "timeZone": "Asia/Yekaterinburg"},     
             # Add other fields like description, attendees if needed
             "description": event_data.get("description", "")
        }

        logger.info(f"Attempting to insert event: {event['summary']}")
        created_event = service.events().insert(
            calendarId="primary", # Use 'primary' for the user's main calendar
            body=event
        ).execute()

        event_link = created_event.get('htmlLink')
        logger.info(f"Event created successfully: {event_link}")
        return created_event # Return the full event object

    except Exception as e:
        logger.error(f"Calendar API Error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Re-raise a more specific exception or handle it
        raise Exception(f"Error creating calendar event: {str(e)}")