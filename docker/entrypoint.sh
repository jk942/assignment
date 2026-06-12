#!/bin/bash
set -e

# Extract DB host and port from DATABASE_URL
# Typical format: postgresql://postgres:postgres@db:5432/transactions
# We fallback to host 'db' and port '5432' if parsing fails or defaults
DB_HOST="db"
DB_PORT="5432"

if [ "$1" = "web" ]; then
  echo "Waiting for postgres at $DB_HOST:$DB_PORT..."
  while ! nc -z "$DB_HOST" "$DB_PORT"; do
    sleep 0.5
  done
  echo "PostgreSQL is up and running!"

  echo "Running Alembic migrations..."
  alembic upgrade head

  echo "Starting FastAPI Application..."
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000

elif [ "$1" = "worker" ]; then
  echo "Waiting for redis at redis:6379..."
  while ! nc -z redis 6379; do
    sleep 0.5
  done
  echo "Redis is up and running!"

  echo "Waiting for postgres at $DB_HOST:$DB_PORT..."
  while ! nc -z "$DB_HOST" "$DB_PORT"; do
    sleep 0.5
  done
  echo "PostgreSQL is up and running!"

  echo "Starting Celery Worker..."
  exec celery -A app.core.celery_app.celery_app worker --loglevel=info

else
  # If a custom command is provided, execute it
  exec "$@"
fi
