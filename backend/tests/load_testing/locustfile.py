"""
Main Locust Entry Point

This is the default file Locust looks for when running.
Run from backend/tests/load_testing/ with:

    locust --host https://your-backend.railway.app

Or with full 100-user test:

    locust --host https://your-backend.railway.app -u 100 -r 2 -t 15m --headless

Web UI mode (interactive):
    
    locust --host https://your-backend.railway.app
    # Then open http://localhost:8089

"""

# Import and re-export the main test user class
from scenarios.chat_load_test import ChatLoadTestUser

# This makes ChatLoadTestUser available to Locust
__all__ = ["ChatLoadTestUser"]

