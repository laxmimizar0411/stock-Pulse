FROM python:3.11-slim

WORKDIR /app

# System dependencies for psycopg2, hiredis, and health check
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for artifacts
RUN mkdir -p reports data/bhavcopy models backups

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
