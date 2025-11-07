#!/bin/bash
# Quick script to run the backend with virtual environment activated

cd "$(dirname "$0")"

# Activate virtual environment
source venv/bin/activate

# Check if uvicorn is installed
if ! command -v uvicorn &> /dev/null; then
    echo "❌ uvicorn not found. Installing dependencies..."
    pip install -r requirements.txt
fi

# Run with reload for development
echo "🚀 Starting FastAPI server with debugging enabled..."
echo "📝 Watch for [PUBLISH], [SAVE], [SCENE_UPDATE], [SCENE_DELETE] logs"
echo ""

python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

