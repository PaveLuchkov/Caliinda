# fastapi_backend.py
from fastapi import FastAPI, UploadFile, HTTPException, Form, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field # For request body models
import tempfile
import os
import logging
from typing import Dict, Optional
import traceback

# Google Auth Libraries
from google.oauth2 import id_token, credentials # Correct import for Credentials
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow # For exchanging the auth code

# Your existing imports
from src.llm_handler import LLMHandler # Assuming this exists and works
from src.calendar_integration import create_calendar_event
from src.speech_to_text import recognize_speech # Assuming this exists and works

# --- Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Audio Calendar Assistant API")

CLIENT_SECRETS_FILE = os.environ.get("GOOGLE_CLIENT_SECRETS", "client_secret.json")

BACKEND_WEB_CLIENT_ID = "835523232919-o0ilepmg8ev25bu3ve78kdg0smuqp9i8.apps.googleusercontent.com" # From your Android code

SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'openid',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/userinfo.email'
]

# --- CORS Configuration ---
# Adjust origins as needed for production
origins = [
    "*", # Allows all origins - BE CAREFUL in production
    # "http://localhost", # Example for local development if serving a web UI
    # "https://your-app-domain.com", # Example for production
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, etc.)
    allow_headers=["*"], # Allows all headers
)

# --- In-Memory Storage for Refresh Tokens (DEMO ONLY) ---
# !!! WARNING: Use a proper database (SQL, NoSQL) in production !!!
# Store mapping: user_google_id (sub) -> refresh_token
# This is NOT persistent and will be lost on server restart.
user_refresh_tokens: Dict[str, str] = {}

# --- Initialize Handlers ---
llm = LLMHandler()

# --- Helper Functions ---

async def verify_google_id_token(token: str) -> dict:
    """Verifies Google ID Token and returns payload."""
    try:
        # Specify the CLIENT_ID of your backend web application here.
        id_info = id_token.verify_oauth2_token(
            token, google_requests.Request(), BACKEND_WEB_CLIENT_ID
        )
        # Verify issuer
        if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')

        # ID token is valid. Return the payload.
        # Contains 'sub' (user ID), 'email', 'name', etc.
        logger.info(f"ID Token verified for user: {id_info.get('email')}")
        return id_info
    except ValueError as e:
        logger.error(f"ID Token verification failed: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid Google ID Token: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during token verification: {e}")
        raise HTTPException(status_code=500, detail="Token verification error")


def get_credentials_from_refresh_token(user_google_id: str) -> Optional[credentials.Credentials]:
    """Retrieves refresh token and builds Credentials object."""
    refresh_token = user_refresh_tokens.get(user_google_id)
    if not refresh_token:
        logger.warning(f"No refresh token found for user ID: {user_google_id}")
        return None

    try:
        creds = credentials.Credentials.from_authorized_user_info(
            info={
                 # We only strictly need the refresh token here for the object
                 # Client ID/Secret will be fetched from the secrets file implicitly by the library later if needed for refresh
                 "refresh_token": refresh_token,
                 # The following are needed if you use from_authorized_user_info directly
                 # If using Flow object later, it might handle this better.
                 # Load client_id and client_secret securely
                 "client_id": BACKEND_WEB_CLIENT_ID, # Make sure this is correct
                 "client_secret": get_client_secret(), # Helper function recommended
                 "token_uri": "https://oauth2.googleapis.com/token",
            },
            scopes=SCOPES # Ensure scopes match what was granted
        )
        # It's good practice to ensure it has the refresh token set
        if not creds.refresh_token:
             creds.refresh_token = refresh_token # Explicitly set if needed

        logger.info(f"Credentials object created for user ID: {user_google_id}")
        return creds
    except Exception as e:
        logger.error(f"Failed to create Credentials object from refresh token: {e}")
        return None

def get_client_secret() -> str:
    """ Placeholder to securely load client secret """
    # In production, load from environment variable or secrets manager
    import json
    try:
        with open(CLIENT_SECRETS_FILE, 'r') as f:
            secrets = json.load(f)
            return secrets.get("web", {}).get("client_secret")
    except Exception as e:
        logger.error(f"Could not load client secret from {CLIENT_SECRETS_FILE}: {e}")
        raise HTTPException(status_code=500, detail="Server configuration error: Missing client secret.")


# --- Request Models ---
class TokenExchangeRequest(BaseModel):
    id_token: str = Field(..., description="Google ID Token received from client")
    auth_code: str = Field(..., description="Google Server Auth Code received from client")


# --- API Endpoints ---

@app.post("/auth/google/exchange", tags=["Authentication"])
async def auth_google_exchange(payload: TokenExchangeRequest):
    """
    Exchanges Google Auth Code for tokens and stores the refresh token.
    Verifies the ID token to link tokens to the correct user.
    """
    logger.info("Received request for /auth/google/exchange")

    # 1. Verify the ID Token first to authenticate the user
    try:
        id_info = await verify_google_id_token(payload.id_token)
        user_google_id = id_info.get('sub')
        if not user_google_id:
            raise HTTPException(status_code=400, detail="Could not get user ID from token.")
        user_email = id_info.get('email') # For logging/confirmation
        logger.info(f"Token exchange request authenticated for user: {user_email} (ID: {user_google_id})")
    except HTTPException as e:
        # Re-raise HTTPException from verification
        raise e
    except Exception as e:
        logger.error(f"Unexpected error during ID token verification: {e}")
        raise HTTPException(status_code=500, detail="Authentication error")

    # 2. Exchange the Authorization Code for Tokens
    try:
        # Configure the Flow object.
        # The redirect_uri must be one of the authorized redirect URIs
        # configured for your application in the Google Cloud Console, even if
        # it's not directly used in this server-to-server exchange.
        # It's often set to 'postmessage' or a dummy URL like 'urn:ietf:wg:oauth:2.0:oob'
        # or one matching your client setup. Check your GCP settings.
        # Use 'postmessage' if that's what your client setup expects or allows for this flow.
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            # Use 'postmessage' or ensure this matches a configured Redirect URI in GCP
            redirect_uri='http://localhost:8000'
            # redirect_uri='postmessage'
            # Or try: redirect_uri='urn:ietf:wg:oauth:2.0:oob'
        )

        logger.info(f"Attempting to fetch token using auth code for user: {user_email}")
        # Perform the code exchange to get tokens
        flow.fetch_token(code=payload.auth_code)

        # Get the credentials containing access and refresh tokens
        credentials_result = flow.credentials
        if not credentials_result or not credentials_result.refresh_token:
            logger.error("Failed to obtain refresh token from Google.")
            raise HTTPException(status_code=400, detail="Could not obtain refresh token from Google. User might have already granted permission or code expired.")

        refresh_token = credentials_result.refresh_token
        access_token = credentials_result.token # Optional to store/use immediately
        expiry = credentials_result.expiry # Optional

        # --- Store the Refresh Token Securely ---
        # !!! Replace this with DATABASE storage in production !!!
        user_refresh_tokens[user_google_id] = refresh_token
        logger.info(f"Successfully obtained and stored refresh token for user: {user_email} (ID: {user_google_id})")

        # You can return minimal confirmation or user info
        return {
            "status": "success",
            "message": "Authorization successful. Calendar access granted.",
            "user_email": user_email
        }

    except FileNotFoundError:
        logger.error(f"Client secrets file not found at: {CLIENT_SECRETS_FILE}")
        raise HTTPException(status_code=500, detail="Server configuration error: Client secrets file missing.")
    except Exception as e:
        logger.error(f"Error exchanging auth code: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}") # Log full traceback
        # Provide a more generic error to the client
        raise HTTPException(status_code=500, detail=f"Failed to exchange Google auth code: {e}")


@app.post("/process_audio", tags=["Calendar"])
async def process_audio(
    audio: UploadFile,
    id_token_str: str = Form(..., alias="id_token_str") # Match the name from Android client
):
    """
    Processes audio, extracts event details, and creates a Google Calendar event
    using stored user credentials (obtained via refresh token).
    """
    logger.info("Received request for /process_audio")

    # 1. Verify ID Token to identify the user
    try:
        id_info = await verify_google_id_token(id_token_str)
        user_google_id = id_info.get('sub')
        user_email = id_info.get('email')
        if not user_google_id:
            raise HTTPException(status_code=401, detail="Could not get user ID from token.")
        logger.info(f"Audio processing request authenticated for user: {user_email} (ID: {user_google_id})")
    except HTTPException as e:
        raise e # Propagate verification errors
    except Exception as e:
        logger.error(f"Unexpected error during ID token verification: {e}")
        raise HTTPException(status_code=500, detail="Authentication error")

    # 2. Get User Credentials using stored Refresh Token
    creds = get_credentials_from_refresh_token(user_google_id)
    if not creds:
        logger.error(f"No valid credentials found for user {user_email} (ID: {user_google_id}). User may need to re-authenticate via /auth/google/exchange.")
        # Inform the client they need to re-run the auth flow
        raise HTTPException(status_code=401, detail="User authorization required. Please sign in again to grant calendar access.")

    tmp_path = None # Initialize outside try block
    try:
        # 3. Save audio temporarily
        # Consider using io.BytesIO if speech_to_text supports it to avoid disk I/O
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp: # Ensure suffix matches expected format
            content = await audio.read()
            if not content:
                raise HTTPException(status_code=400, detail="Empty audio file received.")
            tmp.write(content)
            tmp_path = tmp.name
            logger.info(f"Audio file saved temporarily to: {tmp_path}")

        # 4. Speech-to-Text
        # Replace with your actual STT implementation
        logger.info(f"Performing speech-to-text on {tmp_path}")
        text = recognize_speech(tmp_path)
        if not text:
            logger.warning("Speech recognition returned empty text.")
            # Decide how to handle - error or specific message?
            raise HTTPException(status_code=400, detail="Could not recognize speech in the audio.")
        logger.info(f"Recognized text: '{text}'")


        # 5. LLM Processing
        logger.info("Parsing text with LLM...")
        event_data = llm.parse_calendar_request(text)
        if not event_data or not event_data.get("event_name") or not event_data.get("date") : # Basic check
            logger.warning(f"LLM failed to parse event details from text: '{text}'")
            raise HTTPException(status_code=400, detail=f"Could not understand the event details from your request: '{text}'")
        logger.info(f"LLM parsed event data: {event_data}")


        # 6. Create Calendar Event using the retrieved credentials
        logger.info(f"Creating calendar event for user: {user_email}")
        created_event = create_calendar_event(event_data, creds) # Pass the Credentials object

        # 7. Return Success Response
        return {
            "status": "success",
            "message": "Event created successfully!",
            "event": { # Return structured event data used/created
                "event_name": created_event.get("summary"),
                "date": event_data.get("date"), # Or parse from created_event start/end
                "time": event_data.get("time"), # Or parse
                "description": created_event.get("description"),
            },
            "event_link": created_event.get("htmlLink"), # Link to the event in Google Calendar
            "recognized_text": text,
        }

    except HTTPException as e:
         # Re-raise HTTPExceptions directly
         raise e
    except Exception as e:
        logger.error(f"Error processing audio for user {user_email}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Return a generic server error
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")

    finally:
        # Ensure temporary file is always deleted
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
                logger.info(f"Deleted temporary audio file: {tmp_path}")
            except Exception as e:
                logger.error(f"Error deleting temporary file {tmp_path}: {e}")


# --- Root endpoint for testing ---
@app.get("/", tags=["Status"])
async def root():
    return {"message": "Audio Calendar Assistant Backend is running!"}

# --- Run with Uvicorn (for local development) ---
# if __name__ == "__main__":
#     import uvicorn
#     # Use 0.0.0.0 to make it accessible on your local network
#     uvicorn.run(app, host="0.0.0.0", port=8000)
#     # Command line: uvicorn fastapi_backend:app --host 0.0.0.0 --port 8000 --reload