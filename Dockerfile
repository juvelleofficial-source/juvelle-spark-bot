# 100% Free Cloud Deployment Dockerfile (Render / Railway / Hugging Face Spaces / Cloud Run)
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONPATH=/app \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

# Install minimal OS utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . /app/

# Ensure data directory exists for local SQLite storage
RUN mkdir -p /app/data

# Expose standard web ports
EXPOSE 8000 7860 8080 10000

# Start FastAPI serving server with clean Python entrypoint
CMD ["python", "start.py"]
