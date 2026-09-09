#!/bin/sh
set -e

echo "Applying database migrations..."
alembic upgrade head

echo "Starting Zaply API on port ${PORT:-8000}..."
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-1}" \
  --proxy-headers \
  --forwarded-allow-ips "*"
