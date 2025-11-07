#!/bin/bash

echo "🚀 Starting Railway deployment..."

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if PORT is set, default to 8000
PORT=${PORT:-8000}
echo "📡 Using PORT: $PORT"

# Try to run migrations, but don't fail if they do
echo "🔄 Running database migrations..."
cd database
if alembic upgrade head 2>&1; then
    echo "✅ Database migrations completed successfully"
else
    MIGRATION_EXIT_CODE=$?
    echo "⚠️  Database migrations failed with exit code $MIGRATION_EXIT_CODE"
    echo "⚠️  Continuing startup - app will start but may have database issues"
    echo "⚠️  Check your DATABASE_URL and database permissions"
fi
cd ..

# Start the application (this should always run)
echo "🚀 Starting FastAPI application on port $PORT..."
exec python -m uvicorn main:app --host 0.0.0.0 --port "$PORT" --workers 1

