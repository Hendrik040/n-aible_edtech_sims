#!/bin/bash
set -e

echo "Starting backend service..."

# Check current migration state
echo "Checking current migration state..."
CURRENT_REV=$(uv run alembic current 2>&1 | grep -oP '^\s*\K[0-9a-f]+' || echo "none")

# If no current revision, check if schema exists and stamp appropriately
if [ "$CURRENT_REV" = "none" ] || uv run alembic current 2>&1 | grep -q "Can't locate revision"; then
    echo "No migration version found. Checking database schema..."
    
    # Determine which revision to stamp based on existing schema
    STAMP_REV=$(uv run python -c "
from sqlalchemy import create_engine, inspect
from common.config import get_settings
try:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    if 'users' in tables:
        columns = [col['name'] for col in inspector.get_columns('users')]
        # Check if second migration columns exist
        if 'profile_public' in columns and 'google_id' in columns:
            print('d8d9e0ec814b')  # Second migration (head)
        else:
            print('176865001670')  # First migration
    else:
        print('none')  # No schema, start fresh
except Exception as e:
    print('error')
" 2>/dev/null || echo "error")
    
    if [ "$STAMP_REV" != "none" ] && [ "$STAMP_REV" != "error" ]; then
        echo "Stamping database to revision: $STAMP_REV (schema already exists)"
        uv run alembic stamp "$STAMP_REV"
    elif [ "$STAMP_REV" = "error" ]; then
        echo "Warning: Could not inspect database. Proceeding with migrations..."
    fi
fi

# Run migrations
echo "Running migrations..."
uv run alembic upgrade head

# Start the server
# Railway sets PORT environment variable, default to 8000 if not set
SERVER_PORT=${PORT:-8000}
echo "Starting uvicorn server on port $SERVER_PORT..."
exec uv run uvicorn app.main:app --host 0.0.0.0 --port $SERVER_PORT --log-level info

