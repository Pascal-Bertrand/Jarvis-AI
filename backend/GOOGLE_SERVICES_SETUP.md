# Google Services Setup

This document explains how to set up Google Calendar and Gmail services for both development and production environments.

## Development Environment

For development, the system uses OAuth2 flow which opens a browser for authentication.

### Prerequisites
1. Set the `GOOGLE_CLIENT_SECRET` environment variable
2. Ensure you can open a browser (not in a headless environment)

### Setup
1. The first time you run the application, it will open a browser for Google OAuth
2. Grant the required permissions (Calendar and Gmail access)
3. Credentials will be saved to `token.pickle` for future use

## Production Environment

For production, you have several options:

### Option 1: Service Account (Recommended)
Use a Google Service Account for server-to-server authentication.

1. **Create a Service Account:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Enable Calendar and Gmail APIs
   - Create a Service Account
   - Download the JSON key file

2. **Set Environment Variables:**
   ```bash
   # Option A: File path
   export GOOGLE_SERVICE_ACCOUNT_FILE="/path/to/service-account-key.json"
   
   # Option B: JSON content as string
   export GOOGLE_SERVICE_ACCOUNT_JSON='{"type": "service_account", "project_id": "..."}'
   ```

### Option 2: Pre-generated OAuth Tokens
Generate OAuth tokens in development and deploy them to production.

1. Run the application locally to generate `token.pickle`
2. Copy `token.pickle` to your production environment
3. Set `FORCE_GOOGLE_SERVICES=true` to enable services

### Option 3: Force Enable OAuth in Production
```bash
export FORCE_GOOGLE_SERVICES=true
```
This will attempt OAuth flow even in production (requires browser access).

## Environment Variables Summary

| Variable | Description | Required |
|----------|-------------|----------|
| `GOOGLE_CLIENT_SECRET` | OAuth client secret | Yes (for OAuth) |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Path to service account JSON file | No (for service account) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Service account JSON as string | No (for service account) |
| `FORCE_GOOGLE_SERVICES` | Force enable in production | No (default: false) |

## Required Google API Permissions

- **Calendar API**: `https://www.googleapis.com/auth/calendar`
- **Gmail API**: `https://www.googleapis.com/auth/gmail.modify`

## Troubleshooting

### Services Always Disabled
- Check if you're in a production environment (container, Railway, etc.)
- Verify environment variables are set correctly
- Try setting `FORCE_GOOGLE_SERVICES=true` for testing

### OAuth Fails in Production
- Use service account credentials instead
- Or pre-generate tokens in development and deploy them

### Permission Denied
- Ensure the service account has the required scopes
- For OAuth, re-authenticate to grant missing permissions 