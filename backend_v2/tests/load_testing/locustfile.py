"""
Main Locust Entry Point - Combined Load Tests

This file provides access to ALL test scenarios.

USAGE:
======

1. Registration Load Test (100 new users signing up):
   locust --host https://your-backend.railway.app -f locustfile.py RegistrationLoadTestUser

2. Chat Load Test (existing users chatting):
   locust --host https://your-backend.railway.app -f locustfile.py ChatLoadTestUser

3. Full Journey Test (register + chat):
   locust --host https://your-backend.railway.app -f locustfile.py RegistrationAndChatUser

4. Mixed Load (50% registration, 50% chat) - default:
   locust --host https://your-backend.railway.app

WEB UI:
=======
   locust --host https://your-backend.railway.app
   # Open http://localhost:8089

HEADLESS (for CI/CD):
=====================
   locust --host https://your-backend.railway.app \\
     --headless -u 100 -r 2 -t 15m \\
     --html=reports/report.html

"""

import sys
import os

# Ensure current directory is in path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import all test user classes
from scenarios.chat_load_test import ChatLoadTestUser
from scenarios.registration_load_test import RegistrationLoadTestUser, RegistrationAndChatUser

# Make all user classes available to Locust
__all__ = [
    "ChatLoadTestUser",           # Existing users chatting
    "RegistrationLoadTestUser",   # New user registration only
    "RegistrationAndChatUser",    # Register then chat (full journey)
]
