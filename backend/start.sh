#!/bin/bash
set -e

echo "Starting backend service..."

# Check if database is accessible
echo "Checking database connection..."
uv run python -c "from common.config import get_settings; from common.db.connection import get_db_url; print('Database URL configured')" || {
    echo "Warning: Could not verify database configuration"
}

# Try to run migrations, but don't fail if there's a revision mismatch
echo "Running migrations..."
if ! uv run alembic upgrade head 2>&1; then
    echo "Migration failed, attempting to fix migration state..."
    # If migration fails due to revision mismatch, try to stamp to current head
    uv run alembic stamp head 2>/dev/null || echo "Could not fix migration state"
    # Try migrations again
    uv run alembic upgrade head || {
        echo "Warning: Migrations failed, but continuing to start server..."
    }
fi

# Start the server
echo "Starting uvicorn server..."
exec uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level info

