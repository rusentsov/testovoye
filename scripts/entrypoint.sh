#!/bin/sh
set -e

if [ "$1" = "api" ]; then
  alembic upgrade head
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
elif [ "$1" = "consumer" ]; then
  exec python -m app.consumer.main
else
  exec "$@"
fi
