# Production Deployment Guide

This guide explains how to deploy the Jarvis AI application to production environments like Railway, Heroku, or any container platform.

## Environment Variables for Production

### Required
- `OPENAI_API_KEY` - Your OpenAI API key
- `GOOGLE_CLIENT_SECRET` - Google OAuth client secret

### Google Services (Optional)
- `FORCE_GOOGLE_SERVICES=false` - Disable Google services in production (recommended)
- `GOOGLE_SERVICE_ACCOUNT_JSON` - Service account credentials as JSON string
- `GOOGLE_SERVICE_ACCOUNT_FILE` - Path to service account file

### Server Configuration
- `PORT` - Port to run the server on (default: 5000)
- `GUNICORN_WORKERS` - Number of worker processes (default: CPU cores * 2 + 1)
- `LOG_LEVEL` - Logging level (default: info)
- `FLASK_ENV=production` - Set Flask to production mode

## Railway Deployment

1. **Set Environment Variables:**
   ```bash
   # Required
   OPENAI_API_KEY=your_openai_key_here
   GOOGLE_CLIENT_SECRET=your_google_secret_here
   
   # Recommended for production
   FORCE_GOOGLE_SERVICES=false
   FLASK_ENV=production
   LOG_LEVEL=info
   ```

2. **Deploy:**
   - Railway will automatically use the Dockerfile
   - The app will run with Gunicorn on the port Railway provides

## Google Services in Production

### Option 1: Disable (Recommended for initial deployment)
```bash
FORCE_GOOGLE_SERVICES=false
```
This disables calendar and email features but allows the core AI functionality to work.

### Option 2: Service Account
For full functionality, set up a Google service account:

1. Create service account in Google Cloud Console
2. Download the JSON key
3. Set as environment variable:
   ```bash
   GOOGLE_SERVICE_ACCOUNT_JSON='{"type": "service_account", ...}'
   ```

### Option 3: Copy OAuth Token
From development environment:
1. Generate `token.pickle` locally (already done)
2. Base64 encode it: `base64 token.pickle`
3. In production, decode and save it
4. Set `FORCE_GOOGLE_SERVICES=true`

## Production Server

The application now uses **Gunicorn** instead of Flask's development server:

- ✅ Production-ready WSGI server
- ✅ Multiple worker processes
- ✅ Better performance and stability
- ✅ Proper logging
- ✅ SocketIO support with eventlet workers

## Monitoring

The application logs to stdout/stderr, which Railway captures automatically.

Key log indicators:
- `Calendar OK` / `Gmail OK` - Google services working
- `Google services force-disabled` - Services intentionally disabled
- `No valid credentials available` - Need to set up Google auth

## Troubleshooting

### Google Services Issues
- If you see OAuth errors, set `FORCE_GOOGLE_SERVICES=false`
- For full functionality, use service account credentials
- Check that `GOOGLE_CLIENT_SECRET` is set correctly

### Server Issues
- If app won't start, check `OPENAI_API_KEY` is set
- For slow performance, increase `GUNICORN_WORKERS`
- Check logs for specific error messages

### Memory Issues
- Workers restart every 1000 requests to prevent memory leaks
- Reduce `GUNICORN_WORKERS` if experiencing memory pressure 