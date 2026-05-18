#!/bin/sh
# -------------------------------------------------------
# AtlasPure API entrypoint
# Runs Alembic migrations then starts uvicorn.
# A migration failure is logged but does NOT abort startup
# so the server always comes up (endpoints like
# /api/redirects/setup-table can recover missing tables).
# -------------------------------------------------------

echo "=== AtlasPure API startup ==="

echo "[1/2] Running database migrations..."
if alembic upgrade head; then
    echo "      Migrations applied successfully."
else
    echo "      WARNING: alembic upgrade head failed."
    echo "      The server will still start. If the 'redirects' table"
    echo "      is missing, call GET /api/redirects/setup-table once"
    echo "      to create it without needing terminal access."
fi

echo "[2/2] Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
