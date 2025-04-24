import os, pickle, webbrowser
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.modify',
]
CLIENT_ID = '473172815719-uqsf1bv6rior1ctebkernlnamca3mv3e.apps.googleusercontent.com'
TOKEN_FILE = 'token.pickle'

def initialize_google_services(node_id: str = None) -> dict:
    """
    Perform OAuth (or refresh) and return {'calendar': service, 'gmail': service}.
    If node_id is given, prints/logs “[{node_id}] …” prefixes as before.
    """
    prefix = f"[{node_id}]" if node_id else ""
    print(f"{prefix} Initializing Google services…")

    services = {'calendar': None, 'gmail': None}
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    if not client_secret:
        print(f"{prefix} ERROR: GOOGLE_CLIENT_SECRET not set")
        return services

    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'rb') as f:
                creds = pickle.load(f)
            print(f"{prefix} Loaded credentials from {TOKEN_FILE}")
        except Exception:
            os.remove(TOKEN_FILE)
            creds = None

    # refresh or do OAuth
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print(f"{prefix} Credentials refreshed")
            except Exception:
                creds = None
                os.remove(TOKEN_FILE)
        if not creds:
            flow = InstalledAppFlow.from_client_config({
                "installed": {
                    "client_id": CLIENT_ID,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "redirect_uris": ["http://localhost:8080/"]
                }
            }, SCOPES)
            auth_url, _ = flow.authorization_url(prompt='consent')
            print(f"{prefix} Opening {auth_url}")
            webbrowser.open(auth_url)
            creds = flow.run_local_server(port=8080)
        with open(TOKEN_FILE, 'wb') as f:
            pickle.dump(creds, f)
            print(f"{prefix} Saved credentials to {TOKEN_FILE}")

    # build Calendar
    try:
        cal = build('calendar', 'v3', credentials=creds)
        _ = cal.calendarList().list().execute()
        services['calendar'] = cal
        print(f"{prefix} Calendar OK")
    except Exception as e:
        print(f"{prefix} Calendar init failed: {e}")

    # build Gmail
    try:
        gm = build('gmail', 'v1', credentials=creds)
        _ = gm.users().getProfile(userId='me').execute()
        services['gmail'] = gm
        print(f"{prefix} Gmail OK")
    except Exception as e:
        print(f"{prefix} Gmail init failed: {e}")

    return services
