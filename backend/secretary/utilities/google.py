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

def is_production_environment():
    """Check if we're running in a production/headless environment"""
    
    # Debug: print environment info
    print(f"DEBUG: Checking environment variables...")
    print(f"DEBUG: RAILWAY_ENVIRONMENT = {os.getenv('RAILWAY_ENVIRONMENT')}")
    print(f"DEBUG: RAILWAY_PUBLIC_DOMAIN = {os.getenv('RAILWAY_PUBLIC_DOMAIN')}")
    print(f"DEBUG: RAILWAY_STATIC_URL = {os.getenv('RAILWAY_STATIC_URL')}")
    print(f"DEBUG: RENDER = {os.getenv('RENDER')}")
    print(f"DEBUG: NODE_ENV = {os.getenv('NODE_ENV')}")
    print(f"DEBUG: DISPLAY = {os.getenv('DISPLAY')}")
    print(f"DEBUG: PWD = {os.getenv('PWD')}")
    
    # More aggressive detection for Railway and other cloud platforms
    is_production = (
        os.getenv('RAILWAY_ENVIRONMENT') is not None or
        os.getenv('RAILWAY_PUBLIC_DOMAIN') is not None or
        os.getenv('RAILWAY_STATIC_URL') is not None or
        'railway' in os.getenv('PWD', '').lower() or
        '/app' in os.getenv('PWD', '') or  # Common in Docker containers
        os.getenv('RENDER') is not None or
        os.getenv('VERCEL') is not None or
        os.getenv('HEROKU') is not None or
        os.getenv('NODE_ENV') == 'production' or
        os.getenv('PYTHONPATH', '').startswith('/app') or  # Docker/container indicator
        not os.getenv('DISPLAY') or  # No display (headless)
        os.getenv('DISPLAY') == ':0'  # Default display in containers
    )
    
    print(f"DEBUG: is_production = {is_production}")
    return is_production

def initialize_google_services(node_id: str = None) -> dict:
    """
    Perform OAuth (or refresh) and return {'calendar': service, 'gmail': service}.
    If node_id is given, prints/logs "[{node_id}] …" prefixes as before.
    In production environments, returns empty services to avoid browser requirement.
    """
    prefix = f"[{node_id}]" if node_id else ""
    print(f"{prefix} Initializing Google services…")

    services = {'calendar': None, 'gmail': None}
    
    # Force production mode if we're clearly in a container/server environment
    current_path = os.getcwd()
    if '/app' in current_path or '/opt' in current_path:
        print(f"{prefix} Container environment detected (path: {current_path}) - forcing production mode")
        print(f"{prefix} Google Calendar and Gmail features will be disabled")
        return services
    
    # Skip Google services in production environments
    if is_production_environment():
        print(f"{prefix} Production environment detected - skipping Google services OAuth (requires browser)")
        print(f"{prefix} Google Calendar and Gmail features will be disabled")
        return services

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
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
        if not creds:
            try:
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
            except Exception as e:
                print(f"{prefix} Failed to initialize OAuth flow (likely headless environment): {e}")
                return services
                
        try:
            with open(TOKEN_FILE, 'wb') as f:
                pickle.dump(creds, f)
                print(f"{prefix} Saved credentials to {TOKEN_FILE}")
        except Exception as e:
            print(f"{prefix} Failed to save credentials: {e}")

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
