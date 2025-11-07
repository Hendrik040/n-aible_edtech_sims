#!/bin/bash

echo "🚀 Starting Railway deployment..."

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Railway automatically provides PORT environment variable
# Use it if set, otherwise default to 8000 (for local development)
if [ -z "$PORT" ]; then
    echo "⚠️  PORT environment variable not set, defaulting to 8000"
    PORT=8000
else
    echo "✅ PORT environment variable found: $PORT"
fi
echo "📡 Starting application on port: $PORT"

# Run database migrations - this is critical for the app to work
echo "🔄 Running database migrations..."
cd database

# Run migrations and capture output
MIGRATION_OUTPUT=$(alembic upgrade head 2>&1)
MIGRATION_EXIT_CODE=$?

if [ $MIGRATION_EXIT_CODE -eq 0 ]; then
    echo "✅ Database migrations completed successfully"
    echo "$MIGRATION_OUTPUT" | tail -20  # Show last 20 lines of migration output
else
    echo "❌ Database migrations failed with exit code $MIGRATION_EXIT_CODE"
    echo "Migration output:"
    echo "$MIGRATION_OUTPUT"
    echo ""
    echo "⚠️  CRITICAL: Migrations failed! The application may not work correctly."
    echo "⚠️  Please check:"
    echo "   1. DATABASE_URL is set correctly"
    echo "   2. Database is accessible"
    echo "   3. Database user has proper permissions"
    echo "   4. No conflicting migrations"
    echo ""
    echo "⚠️  Continuing startup anyway, but expect database errors..."
fi
cd ..

# Start the application (this should always run)
echo "🚀 Starting FastAPI application on port $PORT..."
exec python -m uvicorn main:app --host 0.0.0.0 --port "$PORT" --workers 1

