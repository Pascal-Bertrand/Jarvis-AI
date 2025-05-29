# Use Python 3.9 as base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy backend files
COPY backend/ ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create logs directory
RUN mkdir -p logs

# Set environment variables for production
ENV PYTHONPATH=/app
ENV FLASK_ENV=production
ENV FORCE_GOOGLE_SERVICES=false

# Expose port (Railway will override this)
EXPOSE 5000

# Use Gunicorn as the production server
CMD ["gunicorn", "--config", "gunicorn.conf.py", "main:app"] 