import traceback
from typing import Optional, Dict, List, Any 
from datetime import datetime
import logging
import re

import datetime
import pytz # Нужен для работы с IANA таймзонами
from dateutil import parser # Очень удобен для парсинга разных форматов дат/времени

from googleapiclient.discovery import build
from google.oauth2 import credentials
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request as GoogleRequest

from src.redis_cache import get_message_history, add_message_to_history
import src.config as config
import src.database as db_utils
from sqlalchemy.orm import Session
from src.calendar_integration import get_events_for_date, SimpleCalendarEvent
from src.llm_handler import LLMHandler
import src.redis_cache as redis


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self, llm_handler: LLMHandler):
        self.llm_handler = llm_handler

    def _get_valid_credentials(self, user_google_id: str, db: Session) -> Optional[credentials.Credentials]:
        # ... (код из предыдущего ответа)
        refresh_token = db_utils.get_refresh_token(db, user_google_id)
        if not refresh_token: return None
        try:
            creds = credentials.Credentials.from_authorized_user_info(
                info={"refresh_token": refresh_token, "client_id": config.GOOGLE_CLIENT_ID,
                      "client_secret": config.GOOGLE_CLIENT_SECRET, "token_uri": "https://oauth2.googleapis.com/token"},
                scopes=config.SCOPES
            )
            if creds.expired and creds.refresh_token:
                try: creds.refresh(GoogleRequest())
                except Exception as refresh_err: logger.error(f"Refresh failed: {refresh_err}"); return None
            return creds
        except Exception as e: logger.error(f"Creds error: {e}"); return None

    def _search_calendar(self, user_google_id: str, search_params_str: str, db: Session, user_timezone: str) -> Dict[str, Any]:
        logger.info(f"Calendar Search: User={user_google_id}, Query='{search_params_str}'")
        creds = self._get_valid_credentials(user_google_id, db)
        if not creds: return {"error": "Authorization required or token invalid."}

        try:
            service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
            calendar_id = 'primary'
            events_list: List[SimpleCalendarEvent] = []
            query_description = f"query: '{search_params_str}'" # Для логов и сообщений
            results_str = ""
            # Пытаемся распознать timeMin/timeMax
            time_min_match = re.search(r"timeMin:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", search_params_str, re.IGNORECASE)
            time_max_match = re.search(r"timeMax:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", search_params_str, re.IGNORECASE)
            date_match = None
            if not time_min_match or not time_max_match: # Если нет диапазона, ищем дату
                try:
                    parts = search_params_str.split(); date_part = next((p for p in parts if re.fullmatch(r'\d{4}-\d{2}-\d{2}', p)), None)
                    if date_part: date_match = date_part; datetime.datetime.strptime(date_match, '%Y-%m-%d') # Validate
                except (StopIteration, ValueError): date_match = None

            if time_min_match and time_max_match:
                time_min_naive_str = time_min_match.group(1).strip()
                time_max_naive_str = time_max_match.group(1).strip()

                time_min_api = self._parse_and_format_datetime(time_min_naive_str, user_timezone)
                time_max_api = self._parse_and_format_datetime(time_max_naive_str, user_timezone)

                if not time_min_api or not time_max_api:
                    logger.error(f"Failed to parse naive timeMin/timeMax from Clara: '{time_min_naive_str}', '{time_max_naive_str}'")
                    # Возвращаем результат для Clara, чтобы она сообщила об ошибке
                    return {"results": "Internal error processing time range for calendar search."}

                query_description = f"events between {time_min_naive_str} and {time_max_naive_str} ({user_timezone})"
                logger.info(f"Calling events.list API with converted time: timeMin='{time_min_api}', timeMax='{time_max_api}'")
                # Вызов events.list с КОНВЕРТИРОВАННЫМ временем
                events_result = service.events().list(
                    calendarId=calendar_id, timeMin=time_min_api, timeMax=time_max_api,
                    singleEvents=True, orderBy='startTime'
                ).execute()

                items = events_result.get('items', [])
                # Преобразуем в SimpleCalendarEvent (как в get_events_for_date)
                for event in items:
                    start_info=event.get('start',{}); end_info=event.get('end',{})
                    start_time=start_info.get('dateTime', start_info.get('date'))
                    end_time=end_info.get('dateTime', end_info.get('date'))
                    if start_time:
                        try:
                            # Используем snake_case для аргументов, как в __init__
                            events_list.append(SimpleCalendarEvent(
                                id=event.get('id'),
                                summary=event.get('summary','N/A'),
                                start_time=start_time,  # ИЗМЕНЕНО: start_time=...
                                end_time=end_time or start_time,  # ИЗМЕНЕНО: end_time=...
                                description=event.get('description'), # Передаем и другие поля
                                location=event.get('location')      # Передаем и другие поля
                            ))
                        except TypeError as te:
                            # Добавим логгирование конкретно этой ошибки для отладки
                            logger.error(f"TypeError creating SimpleCalendarEvent for event ID {event.get('id')}: {te}")
                            logger.error(f"  start_time type: {type(start_time)}, value: {start_time}")
                            logger.error(f"  end_time type: {type(end_time)}, value: {end_time}")

            elif date_match:
                target_date_obj = datetime.datetime.strptime(date_match, '%Y-%m-%d').date()
                query_description = f"events for date {date_match}"
                logger.info(f"Detected date {date_match}. Calling external get_events_for_date.")
                # Используем твою внешнюю функцию
                events_list = get_events_for_date(creds, target_date_obj)
            else:
                logger.warning(f"Calendar Search: Unsupported query format: '{search_params_str}'")
                # Возвращаем НЕ ошибку, а результат поиска = сообщение для Clara
                logger.info(f"Returning search results for Clara: '{results_str[:500]}...'")
                return {"results": f"Could not understand the calendar query format: '{search_params_str}'. Please ask for events on a specific date (YYYY-MM-DD) or a time range (timeMin: RFC3339; timeMax: RFC3339)."}

            # Форматируем результат для LLM Clara
            if not events_list:
                no_events_msg = f"No events found for {query_description}."
                logger.info(f"Returning search result: {no_events_msg}")
                logger.info(f"Returning search results for Clara: '{results_str[:500]}...'")
                return {"results": no_events_msg}

            else:
                results_str = f"Found events for {query_description}:\n"
                results_str += "\n".join([f"- {evt.summary} (ID: {evt.id}, Time: {evt.startTime} - {evt.endTime})" for evt in events_list])
                logger.info(f"Returning search results: {results_str[:200]}...")
                return {"results": results_str}

        except HttpError as api_error:
            detail = api_error.reason; status = api_error.resp.status
            if status in (401, 403): detail = "Access denied by Google Calendar API."
            error_msg = f"Google Calendar API error ({status}): {detail}"
            # Возвращаем НЕ ошибку, а результат поиска = сообщение об ошибке для Clara
            logger.info(f"Returning search results for Clara: '{results_str[:500]}...'")
            return {"results": f"API Error during calendar search: {error_msg}"}
        except Exception as e:
            logger.error(f"Unexpected calendar search error: {e}", exc_info=True)
            # Возвращаем НЕ ошибку, а результат поиска = сообщение об ошибке для Clara
            logger.info(f"Returning search results for Clara: '{results_str[:500]}...'")
            return {"results": f"Unexpected error during calendar search: {e}"}

    def _parse_and_format_datetime(self, time_str: str, user_timezone_str: str) -> Optional[str]:
            """Парсит строку времени, добавляет таймзону и форматирует в RFC3339."""
            if not time_str:
                return None
            try:
                naive_dt = parser.parse(time_str)

                try:
                    user_tz = pytz.timezone(user_timezone_str)
                except pytz.UnknownTimeZoneError:
                    logger.error(f"Unknown timezone provided: {user_timezone_str}. Falling back to UTC.")
                    user_tz = pytz.utc # Запасной вариант

                # 3. Локализуем "наивное" время в таймзону пользователя
                # ИЛИ если время уже содержит смещение, конвертируем в нужную зону
                if naive_dt.tzinfo is None or naive_dt.tzinfo.utcoffset(naive_dt) is None:
                    # Время "наивное" - считаем, что оно введено в зоне пользователя
                    aware_dt = user_tz.localize(naive_dt)
                else:
                    # Время уже содержит смещение/зону - конвертируем в зону пользователя
                    aware_dt = naive_dt.astimezone(user_tz)

                # 4. Форматируем в RFC3339 (ISO 8601 со смещением)
                rfc3339_time = aware_dt.isoformat()
                logger.debug(f"Parsed time '{time_str}' with timezone '{user_timezone_str}' -> '{rfc3339_time}'")
                return rfc3339_time
            except ValueError as e:
                logger.error(f"Could not parse datetime string: '{time_str}'. Error: {e}")
                return None
            except Exception as e:
                logger.error(f"Error processing datetime string '{time_str}': {e}", exc_info=True)
                return None
        
    async def _process_final_prompt_step(self, user_google_id: str, final_prompt_json: Dict, user_timezone: str, db: Session, time: str) -> Dict[str, Any]:
        """
        Обрабатывает JSON от Clara, вызывает нужные форматтеры/скрипты и выполняет действия в Google Calendar.
        """
        logger.info(f"--- TIME PASSED {time} ---")
        logger.info(f"Processing final prompt step for user {user_google_id} with {len(final_prompt_json)} action(s).")
        action_results = []
        has_errors = False

        creds = self._get_valid_credentials(user_google_id, db)
        if not creds:
            # ... (обработка ошибки credentials как раньше) ...
            logger.error(f"Cannot process final actions for {user_google_id}: Invalid credentials.")
            add_message_to_history(user_google_id, {"role": "system", "content": "Final action failed: Authorization required or token invalid."})
            add_message_to_history(user_google_id, {"role": "assistant", "content": "I can't perform this action right now because I don't have access to your calendar. Please try signing in again."})
            return {"status": "error", "message": "Authorization required or token invalid to perform calendar actions."}

        try:
            service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
        except Exception as build_err:
             logger.error(f"Failed to build Google Calendar service for final actions: {build_err}", exc_info=True)
             add_message_to_history(user_google_id, {"role": "system", "content": f"Final action failed: Cannot build calendar service: {build_err}"})
             add_message_to_history(user_google_id, {"role": "assistant", "content": "Sorry, there was a problem connecting to the calendar service."})
             return {"status": "error", "message": "Internal error connecting to calendar service."}

        for action_key, description_string in final_prompt_json.items():
            action_type = None
            if action_key.startswith("create_"): action_type = "create"
            elif action_key.startswith("change_"): action_type = "change"
            elif action_key.startswith("delete_"): action_type = "delete"
            if not action_type: continue

            logger.info(f"--- Processing action: {action_key} ---")
            add_message_to_history(user_google_id, {"role": "system", "content": f"Processing action {action_key}: {description_string}"})

            api_response = None
            error_message = None
            event_id_for_op = None

            try:
                if action_type == "create":
                    # Вызвать LLM-форматтер для получения ТЕЛА запроса
                    formatted_body = self.llm_handler.format_create_request(description_string, user_timezone, time)
                    if not formatted_body or "error" in formatted_body:
                         error_message = formatted_body.get("error", "Failed to format create request") if formatted_body else "Formatter returned None"
                    else:
                        # --- ДОБАВИТЬ ОБРАБОТКУ ВРЕМЕНИ ---
                        start_obj = formatted_body.get("start")
                        end_obj = formatted_body.get("end")
                        if start_obj and end_obj and start_obj.get("dateTime") and end_obj.get("dateTime"):
                            start_str_naive = start_obj["dateTime"]
                            end_str_naive = end_obj["dateTime"]
                            # Парсим, локализуем и форматируем
                            start_rfc3339 = self._parse_and_format_datetime(start_str_naive, user_timezone)
                            end_rfc3339 = self._parse_and_format_datetime(end_str_naive, user_timezone)

                            if start_rfc3339 and end_rfc3339:
                                # Обновляем body перед отправкой в API
                                formatted_body["start"]["dateTime"] = start_rfc3339
                                formatted_body["start"]["timeZone"] = user_timezone # Добавляем таймзону
                                formatted_body["end"]["dateTime"] = end_rfc3339
                                formatted_body["end"]["timeZone"] = user_timezone   # Добавляем таймзону
                                logger.info(f"Time processed for create: start='{start_rfc3339}', end='{end_rfc3339}'")
                                # --- КОНЕЦ ОБРАБОТКИ ВРЕМЕНИ ---
                                # Выполнить API запрос insert
                                logger.info(f"Executing Calendar API Insert...")
                                api_response = service.events().insert(calendarId='primary', body=formatted_body).execute()
                                event_id_for_op = api_response.get('id')
                                logger.info(f"API Insert successful. Event ID: {event_id_for_op}")
                            else:
                                error_message = "Failed to parse or format time from LLM for create request."
                        else:
                            error_message = "LLM formatter did not return valid start/end dateTime for create request."

                elif action_type == "change":
                    # Извлечь EventID
                    match = re.search(r"EventID:\s*(\S+)", description_string, re.IGNORECASE)
                    if not match: error_message = "Could not parse EventID from change description."
                    else:
                        event_id_for_op = match.group(1).strip()
                        logger.info(f"Extracted EventID for update: {event_id_for_op}")
                        # Вызвать LLM-форматтер для получения ТЕЛА запроса patch
                        formatted_body = self.llm_handler.format_update_request(description_string, user_timezone, time)
                        if not formatted_body or "error" in formatted_body:
                            error_message = formatted_body.get("error", "Failed to format update request") if formatted_body else "Formatter returned None"
                        elif not formatted_body:
                             # LLM решил, что менять нечего. Это не ошибка, а инфо.
                             logger.info(f"Formatter indicated no fields to update for event {event_id_for_op}. Skipping API call.")
                             error_message = None # Сбрасываем ошибку
                             # Сообщаем об этом как об успехе (или info)
                             action_results.append((action_key, "success", f"No changes needed for event ID {event_id_for_op}."))
                             add_message_to_history(user_google_id, {"role": "system", "content": f"Success on {action_key}: No update needed."})
                             continue # Переходим к следующему действию, т.к. это обработано
                        else:
                            # --- ДОБАВИТЬ ОБРАБОТКУ ВРЕМЕНИ (ЕСЛИ ЕСТЬ) ---
                             start_obj = formatted_body.get("start")
                             end_obj = formatted_body.get("end")
                             if start_obj and start_obj.get("dateTime"):
                                 start_rfc3339 = self._parse_and_format_datetime(start_obj["dateTime"], user_timezone)
                                 if start_rfc3339:
                                     formatted_body["start"]["dateTime"] = start_rfc3339
                                     formatted_body["start"]["timeZone"] = user_timezone
                                 else: error_message = "Failed to parse/format start time for update."
                             if end_obj and end_obj.get("dateTime") and not error_message: # Продолжаем только если нет ошибки
                                 end_rfc3339 = self._parse_and_format_datetime(end_obj["dateTime"], user_timezone)
                                 if end_rfc3339:
                                     formatted_body["end"]["dateTime"] = end_rfc3339
                                     formatted_body["end"]["timeZone"] = user_timezone
                                 else: error_message = "Failed to parse/format end time for update."
                            # --- КОНЕЦ ОБРАБОТКИ ВРЕМЕНИ ---

                             if not error_message: # Если время обработано успешно (или его не было)
                                # Выполнить API запрос patch
                                logger.info(f"Executing Calendar API Patch for event {event_id_for_op}...")
                                api_response = service.events().patch(calendarId='primary', eventId=event_id_for_op, body=formatted_body).execute()
                                logger.info(f"API Patch successful. Event ID: {event_id_for_op}")

                elif action_type == "delete":
                    # Извлечь EventID
                    match = re.search(r"EventID:\s*(\S+)", description_string, re.IGNORECASE)
                    if not match: error_message = "Could not parse EventID from delete description."
                    else:
                        event_id_for_op = match.group(1).strip()
                        logger.info(f"Extracted EventID for delete: {event_id_for_op}")
                        # Выполнить API запрос delete
                        logger.info(f"Executing Calendar API Delete for event {event_id_for_op}...")
                        service.events().delete(calendarId='primary', eventId=event_id_for_op).execute()
                        logger.info(f"API Delete successful for Event ID: {event_id_for_op}")
                        api_response = {"id": event_id_for_op, "status": "deleted"} # Имитируем ответ

                # Обработка результата текущего действия (если не было 'continue' для change)
                if error_message:
                    logger.error(f"Error processing action {action_key}: {error_message}")
                    action_results.append((action_key, "error", error_message))
                    has_errors = True
                    add_message_to_history(user_google_id, {"role": "system", "content": f"Error on {action_key}: {error_message}"})
                elif api_response:
                    success_msg = f"Action {action_key} completed successfully."
                    summary = api_response.get('summary', 'N/A')
                    evt_id = api_response.get('id')
                    if action_type == "create": success_msg = f"Created event '{summary}' (ID: {evt_id})."
                    if action_type == "change": success_msg = f"Updated event '{summary}' (ID: {evt_id})."
                    if action_type == "delete": success_msg = f"Deleted event (ID: {evt_id})."
                    action_results.append((action_key, "success", success_msg))
                    add_message_to_history(user_google_id, {"role": "system", "content": f"Success on {action_key}: {success_msg}"})
                # else: # Этот else больше не нужен из-за continue в change

            except HttpError as api_error:
                logger.error(f"Google API error during {action_key}: {api_error}", exc_info=True)
                detail = api_error.reason; status_code = api_error.resp.status
                if status_code in (401, 403): detail = "Access denied by Google Calendar API."
                elif status_code == 404: detail = f"Event not found (ID: {event_id_for_op})." # Добавили ID
                error_message = f"Google Calendar API error ({status_code}): {detail}"
                action_results.append((action_key, "error", error_message))
                has_errors = True
                add_message_to_history(user_google_id, {"role": "system", "content": f"API Error on {action_key}: {error_message}"})
            except Exception as e:
                logger.error(f"Unexpected error during {action_key}: {e}", exc_info=True)
                error_message = f"Unexpected internal error during {action_type} action."
                action_results.append((action_key, "error", error_message))
                has_errors = True
                add_message_to_history(user_google_id, {"role": "system", "content": f"Unexpected Error on {action_key}: {e}"})

        # --- Формирование финального ответа пользователю ---
        final_status = "success" if not has_errors else "partial_error" if any(r[1] == 'success' for r in action_results) else "error"
        if not action_results: # Если входной JSON был пуст или все ключи были неизвестны
             final_message = "No actions were specified or understood."
             final_status = "info"
        else:
            final_message_parts = []
            for key, status, msg in action_results:
                 prefix = "[OK] " if status == "success" else "[FAILED] " if status == "error" else "[?] "
                 final_message_parts.append(prefix + msg)
            final_message = "\n".join(final_message_parts)

        add_message_to_history(user_google_id, {"role": "assistant", "content": final_message})
        return {"status": final_status, "message": final_message}


    # --- Основной метод handle_user_request ---
    async def handle_user_request(self, user_google_id: str, user_text: str, time: str, timezone: str, db: Session) -> Dict[str, Any]:
        """Основная логика обработки запроса с использованием Clara."""
        logger.info(f"--- Handling request for user {user_google_id} ---")
        if not redis.redis_client: return {"status": "error", "message": "History service unavailable."}

        add_message_to_history(user_google_id, {"role": "user", "content": user_text})
        history = get_message_history(user_google_id)

        try:
            # --- Первый вызов Clara ---
            clara_response = self.llm_handler.clara(
                user_input=user_text, time=time, timezone=timezone, history=history
            )

            if not clara_response or "error" in clara_response:
                # ... (обработка ошибки Clara как раньше) ...
                error_msg = clara_response.get('error', 'Unknown Clara error') if clara_response else "Clara None"
                logger.error(f"Clara Error (1st call): {error_msg}")
                add_message_to_history(user_google_id, {"role": "assistant", "content": f"System Error: {error_msg}"})
                return {"status": "error", "message": "Sorry, encountered an internal error."}

            if "message_to_user" in clara_response:
                clarification = clara_response["message_to_user"]
                add_message_to_history(user_google_id, {"role": "assistant", "content": clarification})
                return {"status": "clarification_needed", "message": clarification}

            elif "calendar" in clara_response:
                search_params = clara_response["calendar"]
                add_message_to_history(user_google_id, {"role": "system", "content": f"Action: Calendar search for '{search_params}'."})
                calendar_search_result = self._search_calendar(user_google_id, search_params_str=search_params, user_timezone=timezone, db = db)

                if "error" in calendar_search_result: # Проверяем ключ error
                    calendar_error = calendar_search_result["error"]
                    logger.error(f"Calendar search failed: {calendar_error}")
                    add_message_to_history(user_google_id, {"role": "system", "content": f"Calendar Search Error: {calendar_error}"})
                    # Сообщаем пользователю об ошибке API/авторизации
                    user_friendly_cal_error = "Sorry, I couldn't check your calendar right now."
                    if "Authorization required" in calendar_error or "Access denied" in calendar_error:
                        user_friendly_cal_error = calendar_error # Показываем сообщение о необходимости авторизации
                    add_message_to_history(user_google_id, {"role": "assistant", "content": user_friendly_cal_error})
                    return {"status": "error", "message": user_friendly_cal_error}
                else:
                    # Ошибки нет, получаем результаты
                    calendar_results_str = calendar_search_result.get("results", "No results found.") # Используем .get для безопасности
                    logger.info(f"Calendar search successful. Adding results to history.")
                    # Добавляем РЕЗУЛЬТАТЫ в историю
                    add_message_to_history(user_google_id, {"role": "system", "content": f"Calendar Search Results:\n{calendar_results_str}"})
                    # --- Продолжение как было (второй вызов Clara) ---
                    logger.info("Calling Clara again with calendar results...")
                    history_with_calendar = get_message_history(user_google_id)
                    second_clara_input = f"User's original request: '{user_text}'. Results for calendar query '{search_params}' are in history. Decide next step."
                    second_clara_response = self.llm_handler.clara(
                        user_input=second_clara_input, time=time, timezone=timezone,
                        history=history_with_calendar, calendar_results=calendar_results_str
                    )

                    if not second_clara_response or "error" in second_clara_response:
                         error_msg = second_clara_response.get('error', 'Unknown Clara error') if second_clara_response else "Clara None"
                         logger.error(f"Clara Error (2nd call): {error_msg}")
                         add_message_to_history(user_google_id, {"role": "assistant", "content": f"System Error after search: {error_msg}"})
                         return {"status": "error", "message": "Sorry, error after calendar search."}

                    # Обработка второго ответа
                    if "message_to_user" in second_clara_response:
                        clarification = second_clara_response["message_to_user"]
                        add_message_to_history(user_google_id, {"role": "assistant", "content": clarification})
                        return {"status": "clarification_needed", "message": clarification}
                    elif "prompt_to_llm" in second_clara_response:
                        final_prompt_json = second_clara_response["prompt_to_llm"]
                        return await self._process_final_prompt_step(user_google_id = user_google_id, final_prompt_json = final_prompt_json, user_timezone=timezone, db = db, time=time)
                    # --- ДОБАВИТЬ ЭТУ ПРОВЕРКУ ---
                    elif "calendar" in second_clara_response:
                        # Clara неожиданно снова запросила календарь
                        error_msg = "Clara requested another calendar search unexpectedly after receiving previous results."
                        logger.error(error_msg + f" Request: {second_clara_response['calendar']}")
                        add_message_to_history(user_google_id, {"role": "system", "content": f"Error: {error_msg}"})
                        add_message_to_history(user_google_id, {"role": "assistant", "content": "Sorry, I got stuck trying to check the calendar repeatedly. Could you please rephrase your request?"})
                        return {"status": "error", "message": "Sorry, I encountered an issue while checking the calendar. Please try rephrasing."}
                    # --- КОНЕЦ ДОБАВЛЕННОЙ ПРОВЕРКИ ---
                    else: # Неожиданный ответ (не message_to_user, не prompt_to_llm, не calendar)
                        logger.error(f"Unexpected 2nd Clara response structure: {second_clara_response}")
                        add_message_to_history(user_google_id, {"role": "assistant", "content": "Unexpected internal response."})
                        return {"status": "error", "message": "Unexpected internal response."}

            elif "prompt_to_llm" in clara_response:
                # Клара сразу дала финальное задание
                final_prompt_json = clara_response["prompt_to_llm"]
                return await self._process_final_prompt_step(user_google_id = user_google_id, final_prompt_json = final_prompt_json, user_timezone=timezone, db = db, time=time)
            else:
                # Невалидный ответ Clara
                logger.error(f"Invalid response structure from Clara (main): {clara_response}")
                add_message_to_history(user_google_id, {"role": "assistant", "content": "System Error: Invalid response."})
                return {"status": "error", "message": "Sorry, invalid response received."}

        except Exception as e:
            logger.error(f"Unhandled exception in handle_user_request: {e}\n{traceback.format_exc()}")
            add_message_to_history(user_google_id, {"role": "assistant", "content": f"System Error: {str(e)}"})
            return {"status": "error", "message": "Sorry, an unexpected error occurred."}