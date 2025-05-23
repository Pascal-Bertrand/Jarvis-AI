# Use Python 3.9 as base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy backend files
COPY backend/ ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port (Railway will override this)
EXPOSE 5001

# Run the application
CMD ["python", "main.py"] 