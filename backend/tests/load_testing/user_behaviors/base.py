"""
Base user behavior class for load testing.
Handles authentication, session management, and common HTTP patterns.
"""

import sys
import os
import time
import random
from typing import Optional, Dict, Any
from locust import HttpUser, between, events
from locust.exception import StopUser

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_config


class BaseLoadTestUser(HttpUser):
    """
    Base class for all load test users.
    
    Provides:
    - Automatic authentication on start
    - Session token management
    - Common request headers
    - Error handling and retry logic
    - Think time between requests
    """
    
    # Default wait time between tasks (2-5 seconds simulates real user behavior)
    wait_time = between(2, 5)
    
    # Will be set from config
    abstract = True  # Don't instantiate this class directly
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = get_config()
        self.access_token: Optional[str] = None
        self.user_id: Optional[str] = None
        self.user_email: Optional[str] = None
        self._user_number: Optional[int] = None
    
    def on_start(self):
        """Called when a simulated user starts. Handles login."""
        self._assign_user_number()
        self._login()
    
    def on_stop(self):
        """Called when a simulated user stops. Cleanup."""
        self.access_token = None
        self.user_id = None
    
    def _assign_user_number(self):
        """Assign a unique user number for this virtual user."""
        # Use a simple counter approach - each user gets next available number
        if not hasattr(BaseLoadTestUser, '_user_counter'):
            BaseLoadTestUser._user_counter = 0
        
        BaseLoadTestUser._user_counter += 1
        self._user_number = (BaseLoadTestUser._user_counter % self.config.max_users) + 1
    
    def _get_test_credentials(self) -> tuple[str, str]:
        """Get email/password for this test user."""
        email = self.config.get_test_user_email(self._user_number)
        password = self.config.test_user_password
        return email, password
    
    def _login(self):
        """Authenticate and store the access token."""
        email, password = self._get_test_credentials()
        self.user_email = email
        
        # JSON login format (matches /api/auth/users/login endpoint)
        login_data = {
            "email": email,
            "password": password,
        }
        
        with self.client.post(
            "/api/auth/users/login",
            json=login_data,  # JSON body
            headers={"Content-Type": "application/json"},
            name="[Auth] Login",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access_token")
                self.user_id = data.get("user_id") or data.get("id")
                response.success()
                
                if self.config.debug:
                    print(f"[DEBUG] User {self._user_number} logged in: {email}")
            else:
                # Log the failure but don't crash - mark as failed request
                error_msg = f"Login failed: {response.status_code}"
                if self.config.debug:
                    print(f"[DEBUG] {error_msg} for {email}: {response.text[:200]}")
                response.failure(error_msg)
                # Stop this user if login fails
                raise StopUser()
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get headers with authentication token."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers
    
    def _api_get(
        self, 
        endpoint: str, 
        name: Optional[str] = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Make authenticated GET request."""
        with self.client.get(
            endpoint,
            headers=self._get_auth_headers(),
            name=name or endpoint,
            catch_response=True,
            **kwargs
        ) as response:
            if response.status_code == 200:
                response.success()
                return response.json()
            else:
                response.failure(f"GET {endpoint}: {response.status_code}")
                return None
    
    def _api_post(
        self,
        endpoint: str,
        json_data: Dict[str, Any],
        name: Optional[str] = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Make authenticated POST request."""
        with self.client.post(
            endpoint,
            json=json_data,
            headers=self._get_auth_headers(),
            name=name or endpoint,
            catch_response=True,
            **kwargs
        ) as response:
            if response.status_code in (200, 201):
                response.success()
                try:
                    return response.json()
                except:
                    return {"status": "ok"}
            else:
                response.failure(f"POST {endpoint}: {response.status_code}")
                return None
    
    def think(self, min_seconds: float = 1.0, max_seconds: float = 3.0):
        """Simulate user thinking/reading time."""
        time.sleep(random.uniform(min_seconds, max_seconds))

