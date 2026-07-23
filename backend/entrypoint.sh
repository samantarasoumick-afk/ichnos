#!/bin/sh
# Applies any pending Alembic migrations, then starts the API server.
# Runs on every container start - a no-op on an up-to-date database,
# so it's safe to leave in place rather than requiring a manual
# migration step before every deploy.
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting Ichnos backend..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
