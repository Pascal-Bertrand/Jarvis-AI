import os, pickle, webbrowser
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Import the logging utilities
from secretary.utilities.logging import log_system_message, log_error, log_warning

# Google API scopes required for the application
# - calendar: Read/write access to Google Calendar
# - gmail.modify: Read/write access to Gmail (needed for email management)
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.modify',
]

# OAuth 2.0 client ID for the application (registered in Google Cloud Console)
CLIENT_ID = '473172815719-uqsf1bv6rior1ctebkernlnamca3mv3e.apps.googleusercontent.com'

# Local file to store OAuth tokens for persistent authentication
TOKEN_FILE = 'token.pickle'

def is_production_environment():
    """
    Determine if the application is running in a production/headless environment.
    
    This function checks various environment variables and system indicators to detect
    if we're running in a cloud platform, container, or CI/CD environment where
    interactive OAuth flows (opening browser windows) are not possible.
    
    The function checks for:
    - Cloud platforms: Railway, Render, Vercel, Heroku
    - Container environments: Docker (typically /app path)
    - CI/CD systems: GitHub Actions, general CI environments
    - Headless systems: No display, no TTY access
    
    Returns:
        bool: True if running in production/headless environment, False otherwise.
        
    Examples:
        >>> # On Railway cloud platform
        >>> os.environ['RAILWAY_ENVIRONMENT'] = 'production'
        >>> is_production_environment()
        True
        
        >>> # On local development machine
        >>> # (assuming no production environment variables are set)
        >>> is_production_environment()
        False
    """
    
    # Check for Railway cloud platform indicators
    # Railway sets multiple environment variables that we can detect
    railway_indicators = (
        os.getenv('RAILWAY_ENVIRONMENT') is not None or
        os.getenv('RAILWAY_PUBLIC_DOMAIN') is not None or
        os.getenv('RAILWAY_STATIC_URL') is not None or
        'railway' in os.getenv('PWD', '').lower()
    )
    
    # Check for Docker container indicators
    # Docker containers typically mount code in /app directory
    docker_indicators = (
        '/app' in os.getenv('PWD', '') or
        os.getenv('PYTHONPATH', '').startswith('/app')
    )
    
    # Check for other cloud platforms
    cloud_platform_indicators = (
        os.getenv('RENDER') is not None or      # Render cloud platform
        os.getenv('VERCEL') is not None or      # Vercel serverless platform
        os.getenv('HEROKU') is not None         # Heroku cloud platform
    )
    
    # Check for CI/CD and development environment indicators
    cicd_indicators = (
        os.getenv('NODE_ENV') == 'production' or    # Node.js production flag
        os.getenv('CI') is not None or              # Generic CI environment
        os.getenv('GITHUB_ACTIONS') is not None     # GitHub Actions CI
    )
    
    # Check for truly headless environment (no way to open browser)
    # This is a more conservative check - only treat as production if there's
    # genuinely no way to interact with a GUI
    headless_indicators = (
        not os.getenv('DISPLAY') and           # No X11 display
        not os.getenv('SSH_CONNECTION') and    # Not connected via SSH
        not os.path.exists('/dev/tty')         # No terminal device
    )
    
    # Combine all indicators - if any production indicator is present, treat as production
    is_production = (
        railway_indicators or
        docker_indicators or
        cloud_platform_indicators or
        cicd_indicators or
        headless_indicators
    )
    
    return is_production

def get_service_account_credentials():
    """
    Attempt to load Google service account credentials for server-to-server authentication.
    
    Service accounts are used in production environments where interactive OAuth flows
    are not possible. This function tries two methods to load service account credentials:
    
    1. From a JSON key file whose path is specified in GOOGLE_SERVICE_ACCOUNT_FILE
    2. From a JSON string stored directly in GOOGLE_SERVICE_ACCOUNT_JSON environment variable
    
    Service account credentials allow the application to authenticate without user interaction,
    making them ideal for server deployments, CI/CD pipelines, and containerized environments.
    
    Environment Variables:
        GOOGLE_SERVICE_ACCOUNT_FILE (str, optional): Path to service account JSON key file
        GOOGLE_SERVICE_ACCOUNT_JSON (str, optional): Service account JSON key as string
    
    Returns:
        ServiceAccountCredentials or None: Valid service account credentials if successfully
        loaded, None if no valid credentials could be obtained.
        
    Raises:
        Does not raise exceptions - logs warnings instead and returns None on failure.
        
    Examples:
        >>> # Method 1: Using file path
        >>> os.environ['GOOGLE_SERVICE_ACCOUNT_FILE'] = '/path/to/service-account.json'
        >>> creds = get_service_account_credentials()
        >>> if creds:
        ...     print("Service account loaded from file")
        
        >>> # Method 2: Using JSON string
        >>> os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'] = '{"type": "service_account", ...}'
        >>> creds = get_service_account_credentials()
        >>> if creds:
        ...     print("Service account loaded from JSON string")
    """
    
    # Method 1: Load from service account key file
    # This is useful when the JSON key file is mounted as a volume in containers
    # or stored as a file on the server filesystem
    service_account_file = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
    if service_account_file and os.path.exists(service_account_file):
        try:
            # Load credentials from the JSON key file
            return ServiceAccountCredentials.from_service_account_file(
                service_account_file, scopes=SCOPES
            )
        except Exception as e:
            # Log warning but don't raise - we'll try the next method
            log_warning(f"Failed to load service account from file: {e}")
    
    # Method 2: Load from JSON string in environment variable
    # This is useful for cloud platforms where secrets are injected as environment variables
    # The entire JSON key content is stored as a string in the environment variable
    service_account_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
    if service_account_json:
        try:
            import json
            # Parse the JSON string into a Python dictionary
            service_account_info = json.loads(service_account_json)
            # Create credentials from the parsed JSON info
            return ServiceAccountCredentials.from_service_account_info(
                service_account_info, scopes=SCOPES
            )
        except Exception as e:
            # Log warning but don't raise - graceful degradation
            log_warning(f"Failed to load service account from JSON: {e}")
    
    # If both methods failed, return None
    return None

def initialize_google_services(node_id: str = None) -> dict:
    """
    Initialize and authenticate Google Calendar and Gmail services.
    
    This is the main authentication function that handles multiple authentication scenarios:
    
    1. **Production Environment with Service Account**: Uses service account credentials
       for server-to-server authentication without user interaction.
    
    2. **Production Environment with Existing OAuth**: Falls back to previously saved
       OAuth tokens if available.
    
    3. **Development Environment**: Performs interactive OAuth flow, opening a browser
       for user authentication.
    
    4. **Force-enabled Production**: When FORCE_GOOGLE_SERVICES=true, allows OAuth
       even in production environments.
    
    The function implements intelligent environment detection and graceful fallbacks
    to ensure Google services work in both development and production scenarios.
    
    Authentication Flow:
        1. Detect if running in production environment
        2. If production: try service account → existing OAuth → disable (unless forced)
        3. If development: try existing OAuth → new OAuth flow
        4. Test both Calendar and Gmail APIs to ensure credentials work
        5. Return service objects for successful authentications
    
    Args:
        node_id (str, optional): Identifier for logging purposes. If provided,
            all log messages will be prefixed with "[{node_id}]" for easier
            debugging in multi-node or distributed systems.
    
    Environment Variables:
        FORCE_GOOGLE_SERVICES (str): Set to 'true', '1', or 'yes' to enable
            Google services even in production environments.
        GOOGLE_CLIENT_SECRET (str): OAuth 2.0 client secret for authentication.
        GOOGLE_SERVICE_ACCOUNT_FILE (str): Path to service account JSON file.
        GOOGLE_SERVICE_ACCOUNT_JSON (str): Service account JSON as string.
    
    Returns:
        dict: Dictionary containing initialized Google service objects:
            {
                'calendar': googleapiclient.discovery.Resource or None,
                'gmail': googleapiclient.discovery.Resource or None
            }
            
            Services will be None if authentication failed or was disabled.
    
    Examples:
        >>> # Basic usage
        >>> services = initialize_google_services()
        >>> if services['calendar']:
        ...     events = services['calendar'].events().list(calendarId='primary').execute()
        
        >>> # With node identifier for logging
        >>> services = initialize_google_services(node_id="worker-1")
        >>> # Logs will show: "[worker-1] Initializing Google services…"
        
        >>> # Force enable in production
        >>> os.environ['FORCE_GOOGLE_SERVICES'] = 'true'
        >>> services = initialize_google_services()
        >>> # Will attempt OAuth even in production environment
    
    Notes:
        - OAuth tokens are cached in 'token.pickle' for reuse
        - Service account credentials take precedence in production
        - Container environments (/app, /opt paths) are automatically detected
        - Failed authentication attempts are logged but don't raise exceptions
        - The function tests API connectivity before returning service objects
    """
    
    # Create log message prefix for this node/instance
    prefix = f"[{node_id}]" if node_id else ""
    log_system_message(f"{prefix} Initializing Google services…")

    # Initialize return structure - services start as None (disabled)
    services = {'calendar': None, 'gmail': None}
    
    # Check if Google services are force-enabled via environment variable
    # This allows overriding production restrictions when needed
    force_enabled = os.getenv('FORCE_GOOGLE_SERVICES', '').lower() in ['true', '1', 'yes']
    
    # Additional check for container environments based on current working directory
    # Docker containers and cloud platforms often use /app or /opt as the base path
    current_path = os.getcwd()
    if '/app' in current_path or '/opt' in current_path:
        log_system_message(f"{prefix} Container environment detected (path: {current_path})")
        if not force_enabled:
            log_system_message(f"{prefix} Google Calendar and Gmail features will be disabled (set FORCE_GOOGLE_SERVICES=true to enable)")
            return services

    # Determine if we're in a production environment
    is_prod = is_production_environment()
    
    # Initialize credentials variable
    creds = None
    
    # Production Environment Authentication Strategy
    if is_prod:
        log_system_message(f"{prefix} Production environment detected - trying service account authentication")
        
        # First priority: Service account credentials (best for production)
        creds = get_service_account_credentials()
        if creds:
            log_system_message(f"{prefix} Service account credentials loaded successfully")
        else:
            log_system_message(f"{prefix} No service account credentials found, trying existing OAuth tokens")
            
            # Second priority: Existing OAuth tokens (fallback for production)
            if os.path.exists(TOKEN_FILE):
                try:
                    with open(TOKEN_FILE, 'rb') as f:
                        creds = pickle.load(f)
                    log_system_message(f"{prefix} Loaded existing OAuth credentials")
                except Exception as e:
                    log_warning(f"{prefix} Failed to load existing OAuth credentials: {e}")
            
            # If no valid credentials and not force-enabled, disable services
            if not creds and not force_enabled:
                log_system_message(f"{prefix} No valid credentials available and OAuth not possible in production")
                log_system_message(f"{prefix} Google Calendar and Gmail features will be disabled")
                log_system_message(f"{prefix} To enable, set FORCE_GOOGLE_SERVICES=true or provide service account credentials")
                return services

    # Development Environment or No Service Account Authentication
    if not creds:
        # Check for required OAuth client secret
        client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        if not client_secret:
            log_warning(f"{prefix} GOOGLE_CLIENT_SECRET not set - Google services will be unavailable")
            return services

        # Try to load existing OAuth tokens from local file
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, 'rb') as f:
                    creds = pickle.load(f)
                log_system_message(f"{prefix} Loaded credentials from {TOKEN_FILE}")
            except Exception:
                # If token file is corrupted, remove it and start fresh
                os.remove(TOKEN_FILE)
                creds = None

        # Refresh expired credentials or perform new OAuth flow
        if not creds or not creds.valid:
            # Try to refresh expired but valid credentials
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    log_system_message(f"{prefix} Credentials refreshed")
                except Exception:
                    # Refresh failed, need new OAuth flow
                    creds = None
                    if os.path.exists(TOKEN_FILE):
                        os.remove(TOKEN_FILE)
            
            # Perform new OAuth flow if no valid credentials
            if not creds:
                # Check if OAuth is allowed in current environment
                if is_prod and not force_enabled:
                    log_system_message(f"{prefix} Cannot perform OAuth in production without FORCE_GOOGLE_SERVICES=true")
                    return services
                
                try:
                    # Create OAuth flow with client configuration
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
                    
                    # Generate authorization URL and open in browser
                    auth_url, _ = flow.authorization_url(prompt='consent')
                    log_system_message(f"{prefix} Opening {auth_url}")
                    webbrowser.open(auth_url)
                    
                    # Start local server to receive OAuth callback
                    creds = flow.run_local_server(port=8080)
                except Exception as e:
                    log_warning(f"{prefix} Failed to initialize OAuth flow: {e}")
                    return services
                    
            # Save credentials for future use
            try:
                with open(TOKEN_FILE, 'wb') as f:
                    pickle.dump(creds, f)
                    log_system_message(f"{prefix} Saved credentials to {TOKEN_FILE}")
            except Exception as e:
                log_warning(f"{prefix} Failed to save credentials: {e}")

    # Initialize Google Calendar Service
    try:
        # Build Calendar API service object
        cal = build('calendar', 'v3', credentials=creds)
        
        # Test the connection by listing calendars
        # This ensures the credentials work and the API is accessible
        _ = cal.calendarList().list().execute()
        
        # Store the working service object
        services['calendar'] = cal
        log_system_message(f"{prefix} Calendar OK")
    except Exception as e:
        log_warning(f"{prefix} Calendar init failed: {e}")

    # Initialize Gmail Service
    try:
        # Build Gmail API service object
        gm = build('gmail', 'v1', credentials=creds)
        
        # Test the connection by getting user profile
        # This ensures the credentials work and the API is accessible
        _ = gm.users().getProfile(userId='me').execute()
        
        # Store the working service object
        services['gmail'] = gm
        log_system_message(f"{prefix} Gmail OK")
    except Exception as e:
        log_warning(f"{prefix} Gmail init failed: {e}")

    return services
