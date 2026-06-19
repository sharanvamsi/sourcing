# FastAPI backend image. Build context is the REPO ROOT (not backend/) because
# backend/main.py imports shared modules from the root (db_manager, experiment_*,
# email_service). Point the Railway service's Dockerfile path at backend/Dockerfile
# while leaving its Root Directory at the repo root.
#
#   docker build -f backend/Dockerfile -t aba-backend .
FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 + cryptography
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install root deps (used by the shared modules) and the FastAPI-specific deps
COPY requirements.txt ./requirements.txt
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r backend/requirements.txt

# App code
COPY . .

EXPOSE 8000

# Railway provides $PORT; default to 8000 for local runs
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
