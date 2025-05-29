import os, pickle, webbrowser
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
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
        os.getenv('CI') is not None or  # CI/CD environments
        os.getenv('GITHUB_ACTIONS') is not None or  # GitHub Actions
        # Only treat as production if there's truly no way to open a browser
        (not os.getenv('DISPLAY') and not os.getenv('SSH_CONNECTION') and not os.path.exists('/dev/tty'))
    )
    
    return is_production

def get_service_account_credentials():
    """
    Get service account credentials for production environments.
    
    Returns:
        ServiceAccountCredentials or None if not available
    """
    # Option 1: Service account key file path
    service_account_file = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
    if service_account_file and os.path.exists(service_account_file):
        try:
            return ServiceAccountCredentials.from_service_account_file(
                service_account_file, scopes=SCOPES
            )
        except Exception as e:
            print(f"Failed to load service account from file: {e}")
    
    # Option 2: Service account key as JSON string in environment variable
    service_account_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
    if service_account_json:
        try:
            import json
            service_account_info = json.loads(service_account_json)
            return ServiceAccountCredentials.from_service_account_info(
                service_account_info, scopes=SCOPES
            )
        except Exception as e:
            print(f"Failed to load service account from JSON: {e}")
    
    return None

def initialize_google_services(node_id: str = None) -> dict:
    """
    Perform OAuth (or service account auth) and return {'calendar': service, 'gmail': service}.
    If node_id is given, prints/logs "[{node_id}] …" prefixes as before.
    
    In production environments:
    - First tries to use service account credentials
    - Falls back to existing OAuth tokens if available
    - Can be forced to enable with FORCE_GOOGLE_SERVICES=true
    """
    prefix = f"[{node_id}]" if node_id else ""
    print(f"{prefix} Initializing Google services…")

    services = {'calendar': None, 'gmail': None}
    
    # Check if Google services are force-enabled
    force_enabled = os.getenv('FORCE_GOOGLE_SERVICES', '').lower() in ['true', '1', 'yes']
    
    # Force production mode if we're clearly in a container/server environment
    current_path = os.getcwd()
    if '/app' in current_path or '/opt' in current_path:
        print(f"{prefix} Container environment detected (path: {current_path})")
        if not force_enabled:
            print(f"{prefix} Google Calendar and Gmail features will be disabled (set FORCE_GOOGLE_SERVICES=true to enable)")
            return services

    is_prod = is_production_environment()
    
    # In production, try service account first
    creds = None
    if is_prod:
        print(f"{prefix} Production environment detected - trying service account authentication")
        creds = get_service_account_credentials()
        if creds:
            print(f"{prefix} Service account credentials loaded successfully")
        else:
            print(f"{prefix} No service account credentials found, trying existing OAuth tokens")
            # Try to load existing OAuth tokens
            if os.path.exists(TOKEN_FILE):
                try:
                    with open(TOKEN_FILE, 'rb') as f:
                        creds = pickle.load(f)
                    print(f"{prefix} Loaded existing OAuth credentials")
                except Exception as e:
                    print(f"{prefix} Failed to load existing OAuth credentials: {e}")
            
            if not creds and not force_enabled:
                print(f"{prefix} No valid credentials available and OAuth not possible in production")
                print(f"{prefix} Google Calendar and Gmail features will be disabled")
                print(f"{prefix} To enable, set FORCE_GOOGLE_SERVICES=true or provide service account credentials")
                return services

    # If not in production or no service account, use OAuth flow
    if not creds:
        client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        if not client_secret:
            print(f"{prefix} ERROR: GOOGLE_CLIENT_SECRET not set")
            return services

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
                if is_prod and not force_enabled:
                    print(f"{prefix} Cannot perform OAuth in production without FORCE_GOOGLE_SERVICES=true")
                    return services
                
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
                    print(f"{prefix} Failed to initialize OAuth flow: {e}")
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
