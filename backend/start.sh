#!/bin/bash
set -e

echo "Starting backend service..."
echo "Environment: ${ENVIRONMENT:-development}"
echo "PORT: ${PORT:-8000}"

# Sync uv environment to ensure all dependencies are available
# This is important because Railpack may install with pip, but we use uv run
echo "Syncing uv environment..."
uv sync

# Activate the uv virtual environment
# uv creates .venv by default, activate it so we can use python/uvicorn directly
if [ -d ".venv" ]; then
    echo "Activating uv virtual environment..."
    source .venv/bin/activate
else
    echo "WARNING: .venv directory not found, using uv run instead"


# Verify database URL is set (Railway provides this automatically)
if [ -z "$DATABASE_URL" ]; then
    echo "WARNING: DATABASE_URL environment variable is not set!"
    echo "This will default to SQLite, which may not work in production."
else
    echo "DATABASE_URL is set (length: ${#DATABASE_URL} characters)"
    # Don't print the full URL for security, but show the type
    if [[ "$DATABASE_URL" == postgresql* ]]; then
        echo "Database type: PostgreSQL"
    elif [[ "$DATABASE_URL" == sqlite* ]]; then
        echo "Database type: SQLite"
    else
        echo "Database type: Unknown"
    fi
fi

# Check current migration state
echo "Checking current migration state..."
# Use python directly if venv is activated, otherwise use uv run
if [ -n "$VIRTUAL_ENV" ]; then
    CURRENT_REV=$(python -m alembic current 2>&1 | grep -oP '^\s*\K[0-9a-f]+' || echo "none")
else
    CURRENT_REV=$(uv run alembic current 2>&1 | grep -oP '^\s*\K[0-9a-f]+' || echo "none")
fi

# If no current revision, check if schema exists and stamp appropriately
if [ "$CURRENT_REV" = "none" ] || ( [ -n "$VIRTUAL_ENV" ] && python -m alembic current 2>&1 | grep -q "Can't locate revision" ) || ( [ -z "$VIRTUAL_ENV" ] && uv run alembic current 2>&1 | grep -q "Can't locate revision" ); then
    echo "No migration version found. Checking database schema..."
    
    # Determine which revision to stamp based on existing schema
    if [ -n "$VIRTUAL_ENV" ]; then
        STAMP_REV=$(python -c "
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
    else
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
    fi
    
    if [ "$STAMP_REV" != "none" ] && [ "$STAMP_REV" != "error" ]; then
        echo "Stamping database to revision: $STAMP_REV (schema already exists)"
        if [ -n "$VIRTUAL_ENV" ]; then
            python -m alembic stamp "$STAMP_REV"
        else
            uv run alembic stamp "$STAMP_REV"
        fi
    elif [ "$STAMP_REV" = "error" ]; then
        echo "Warning: Could not inspect database. Proceeding with migrations..."
    fi
fi

# Run migrations
echo "Running migrations..."
if [ -n "$VIRTUAL_ENV" ]; then
    if ! python -m alembic upgrade head; then
        echo "ERROR: Migrations failed!"
        echo "This could be due to:"
        echo "  1. Database connection issues"
        echo "  2. Missing DATABASE_URL environment variable"
        echo "  3. Database schema conflicts"
        exit 1
    fi
else
    if ! uv run alembic upgrade head; then
        echo "ERROR: Migrations failed!"
        echo "This could be due to:"
        echo "  1. Database connection issues"
        echo "  2. Missing DATABASE_URL environment variable"
        echo "  3. Database schema conflicts"
        exit 1
    fi
fi
echo "Migrations completed successfully"

# Start the server
# Railway sets PORT environment variable, default to 8000 if not set
SERVER_PORT=${PORT:-8000}
echo "Starting uvicorn server on port $SERVER_PORT..."
echo "Server will be available at http://0.0.0.0:$SERVER_PORT"
echo "Health check endpoint: http://0.0.0.0:$SERVER_PORT/health"

# Use exec to replace shell process with uvicorn
# This ensures proper signal handling and process management
# Use python directly if venv is activated (more reliable than uv run)
if [ -n "$VIRTUAL_ENV" ]; then
    echo "Using activated virtual environment"
    exec python -m uvicorn app.main:app \
        --host 0.0.0.0 \
        --port $SERVER_PORT \
        --log-level info \
        --access-log \
        --timeout-keep-alive 5 \
        --timeout-graceful-shutdown 10
else
    echo "Using uv run (venv not activated)"
    exec uv run uvicorn app.main:app \
        --host 0.0.0.0 \
        --port $SERVER_PORT \
        --log-level info \
        --access-log \
        --timeout-keep-alive 5 \
        --timeout-graceful-shutdown 10
fi

