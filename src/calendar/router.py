# src/calendar/router.py

from fastapi import APIRouter, Depends, status, Path, Query, Response, HTTPException
from typing import List
import datetime
import logging
from googleapiclient.errors import HttpError

from . import schemas
from .service import GoogleCalendarService
from src.core.dependencies import get_calendar_service

# Инициализация роутера и логгера
router = APIRouter(
    prefix="/calendar",
    tags=["Calendar"],
)
logger = logging.getLogger(__name__)

# --- Обработчик ошибок для Google API ---
# Это можно вынести в отдельную утилиту, если будет использоваться в других роутерах
def handle_google_api_error(e: HttpError, user_email: str, action: str):
    """Преобразует HttpError от Google в FastAPI HTTPException."""
    error_details = e.content.decode('utf-8') if e.content else str(e)
    status_code = e.resp.status if hasattr(e, 'resp') else 500
    logger.error(f"Google API error during '{action}' for user {user_email}: {status_code} - {error_details}", exc_info=True)
    
    if status_code in [401, 403]:
        detail = f"Access to Google Calendar denied or token invalid. Please sign in again. (Reason: {e.reason})"
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    if status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The requested calendar resource was not found.")
    if status_code == 400:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid request to Google API: {error_details}")
    
    # Общая ошибка для всех остальных случаев
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Google Calendar API Error: {e.reason}")

@router.get(
    "/events/range",
    response_model=List[schemas.CalendarEventResponse],
    summary="Get events for a date range"
)
def get_calendar_events_range(
    startDate: str = Query(..., description="Start date (YYYY-MM-DD)", regex=r"^\d{4}-\d{2}-\d{2}$"),
    endDate: str = Query(..., description="End date (YYYY-MM-DD)", regex=r"^\d{4}-\d{2}-\d{2}$"),
    calendar_service: GoogleCalendarService = Depends(get_calendar_service)
):
    """
    Fetches calendar events for the authenticated user within a specified date range.
    """
    logger.info(f"Request to get events from {startDate} to {endDate} for user {calendar_service.user_email}")
    try:
        start_date_obj = datetime.date.fromisoformat(startDate)
        end_date_obj = datetime.date.fromisoformat(endDate)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    
    if start_date_obj > end_date_obj:
        raise HTTPException(status_code=400, detail="Start date cannot be after end date.")

    try:
        events = calendar_service.get_events(start_date_obj, end_date_obj)
        return events
    except HttpError as e:
        handle_google_api_error(e, calendar_service.user_email, "get_events")
    except Exception as e:
        logger.error(f"Unexpected error getting events for {calendar_service.user_email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error.")

@router.post(
    "/events",
    response_model=schemas.CreateEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new event"
)
def create_calendar_event(
    event_data: schemas.CreateEventRequest,
    calendar_service: GoogleCalendarService = Depends(get_calendar_service)
):
    """Creates a new event in the user's primary Google Calendar."""
    logger.info(f"Request to create event for user {calendar_service.user_email}: {event_data.model_dump()}")
    try:
        created_event = calendar_service.create_event(event_data)
        return schemas.CreateEventResponse(eventId=created_event.get('id'))
    except HttpError as e:
        handle_google_api_error(e, calendar_service.user_email, "create_event")
    except ValueError as e: # Для обработки ошибок валидации из сервиса
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating event for {calendar_service.user_email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error.")

@router.patch(
    "/events/{event_id}",
    response_model=schemas.UpdateEventResponse,
    summary="Update an existing event"
)
def update_calendar_event(
    event_id: str = Path(..., description="The ID of the event to update"),
    event_data: schemas.UpdateEventRequest = ...,
    update_mode: schemas.EventUpdateMode = Query(..., description="Update mode for recurring events"),
    calendar_service: GoogleCalendarService = Depends(get_calendar_service)
):
    """Updates an existing event in the user's primary Google Calendar."""
    logger.info(f"Request to update event {event_id} for user {calendar_service.user_email} with mode {update_mode}")
    try:
        # Сервис возвращает dict, который Pydantic автоматически валидирует и преобразует
        updated_event_response = calendar_service.update_event(event_id, event_data, update_mode)
        return updated_event_response
    except HttpError as e:
        handle_google_api_error(e, calendar_service.user_email, f"update_event:{event_id}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NotImplementedError as e: # Для режима THIS_AND_FOLLOWING
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error updating event {event_id} for {calendar_service.user_email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error.")

@router.delete(
    "/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an event"
)
def delete_calendar_event(
    event_id: str = Path(..., description="The ID of the event to delete"),
    mode: schemas.DeleteEventMode = Query(schemas.DeleteEventMode.DEFAULT, description="Deletion mode"),
    calendar_service: GoogleCalendarService = Depends(get_calendar_service)
):
    """Deletes an event from the user's primary Google Calendar."""
    logger.info(f"Request to delete event {event_id} for user {calendar_service.user_email} with mode {mode}")
    try:
        calendar_service.delete_event(event_id, mode)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HttpError as e:
        # Особый случай для 410 Gone - событие уже удалено, это успех
        if hasattr(e, 'resp') and e.resp.status == 410:
            logger.warning(f"Event {event_id} was already deleted (410 Gone). Returning success.")
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        handle_google_api_error(e, calendar_service.user_email, f"delete_event:{event_id}")
    except Exception as e:
        logger.error(f"Unexpected error deleting event {event_id} for {calendar_service.user_email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error.")