#!/bin/sh
# Applies any pending Alembic migrations, then starts the API server.
# Runs on every container start - a no-op on an up-to-date database,
# so it's safe to leave in place rather than requiring a manual
# migration step before every deploy.
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting DatFe backend..."
# --proxy-headers/--forwarded-allow-ips: this backend is only ever
# reached through the frontend/nginx layer (never exposed directly -
# see docker-compose.yml), so it's safe to trust X-Forwarded-* headers
# from any peer here; this makes uvicorn report the real client scheme
# (https behind the tunnel) correctly.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
