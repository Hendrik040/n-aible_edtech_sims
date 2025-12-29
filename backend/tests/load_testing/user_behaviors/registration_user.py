"""
Registration user behavior for load testing the signup flow.
Generates random users and registers them, then optionally proceeds to use the platform.
"""

import sys
import os
import random
import string
import time
from datetime import datetime
from typing import Optional, Dict, Any
from locust import task, between
from locust.exception import StopUser


def timestamp() -> str:
    """Return current timestamp in HH:MM:SS.mmm format for logging."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from user_behaviors.base import BaseLoadTestUser
from config import get_config


def generate_random_string(length: int = 8) -> str:
    """Generate a random alphanumeric string."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def generate_random_name() -> str:
    """Generate a realistic-looking random name."""
    first_names = [
        "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Quinn", "Avery",
        "Cameron", "Blake", "Drew", "Sage", "Reese", "Finley", "Emery", "Dakota",
        "Jamie", "Charlie", "Sam", "Max", "Robin", "Lee", "Pat", "Chris",
        "Emma", "Liam", "Olivia", "Noah", "Ava", "Oliver", "Sophia", "Lucas"
    ]
    last_names = [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
        "Davis", "Rodriguez", "Martinez", "Anderson", "Taylor", "Thomas", "Moore",
        "Jackson", "Martin", "Lee", "Thompson", "White", "Harris", "Clark", "Lewis"
    ]
    return f"{random.choice(first_names)} {random.choice(last_names)}"


class RegistrationUser(BaseLoadTestUser):
    """
    User that registers a new account with random credentials.
    
    Use this to test:
    - Registration endpoint under load
    - 100 simultaneous signups
    - Full user journey: register -> explore -> chat
    """
    
    wait_time = between(2, 5)
    
    # Override to skip login on start
    def on_start(self):
        """Register a new user instead of logging in."""
        self._assign_user_number()
        if self.config.debug:
            print(f"[{timestamp()}] [DEBUG] User {self._user_number}: Starting registration flow")
        self._register_new_user()
        if self.config.debug:
            print(f"[{timestamp()}] [DEBUG] User {self._user_number}: Registration complete, entering task loop")
    
    def _generate_credentials(self) -> Dict[str, str]:
        """
        Generate predictable credentials that match what chat test expects.
        
        Uses the same email format as BaseLoadTestUser._get_test_credentials()
        so that users created here can be logged into by the chat test.
        
        Email pattern: {prefix}{user_number}{domain}
        Example: loadtest_user_opt1@testnew.com, loadtest_user_opt2@testnew.com, etc.
        """
        # Use the same format as BaseLoadTestUser._get_test_credentials()
        # This creates predictable emails like: loadtest_user_opt1@testnew.com
        email = self.config.get_test_user_email(self._user_number)
        
        return {
            "email": email,
            "username": f"lt_user_{self._user_number}",
            "password": self.config.test_user_password,  # Use SAME password from config
            "full_name": generate_random_name(),
        }
    
    def _register_new_user(self):
        """Register a new user with random credentials."""
        creds = self._generate_credentials()
        self.user_email = creds["email"]
        self._generated_password = creds["password"]
        
        register_data = {
            "email": creds["email"],
            "username": creds["username"],
            "password": creds["password"],
            "full_name": creds["full_name"],
            "role": "student",  # Default to student for load testing
            "profile_public": True,
            "allow_contact": False,  # Don't spam test users
        }
        
<<<<<<< HEAD
        # Debug: show full URL
        # Router structure: /api/auth (wiring) + /users (module router) + /register
        endpoint = "/api/auth/users/register"
        full_url = f"{self.host}{endpoint}"
        request_start = time.time()
        print(f"[{timestamp()}] [REGISTER] → Sending request to: {full_url}")
=======
        # Use correct endpoint based on codebase (legacy vs new)
        # Legacy (US-STAG): /users/register
        # New (US-EXP, US-DEV, EU): /api/auth/users/register
        endpoint = "/users/register" if self.config.is_legacy_api else "/api/auth/users/register"
        full_url = f"{self.host}{endpoint}"
        request_start = time.time()
        print(f"[{timestamp()}] [REGISTER] → Sending request to: {full_url} (legacy={self.config.is_legacy_api})")
>>>>>>> f704b47 (feat(load-testing): support old codebase comparison with US-STAG region)
        
        with self.client.post(
            endpoint,
            json=register_data,
            headers={"Content-Type": "application/json"},
            name="[Auth] Register",
            catch_response=True
        ) as response:
            # Calculate request duration
            request_duration = (time.time() - request_start) * 1000  # Convert to ms
            
            # Always log for debugging during development
            print(f"[{timestamp()}] [REGISTER] ← Response: {response.status_code} in {request_duration:.0f}ms | Email: {creds['email']}")
            if response.status_code not in (200, 201):
                print(f"[{timestamp()}] [REGISTER] Error body: {response.text[:500]}")
            
            if response.status_code in (200, 201):
                data = response.json()
                self.user_id = data.get("id")
                response.success()
                
                # Now login to get access token
                self._login_after_register(creds["email"], creds["password"])
                
                print(f"[{timestamp()}] [REGISTER] ✓ Complete: {creds['email']} (total: {request_duration:.0f}ms)")
            
            elif response.status_code == 400:
                # Email/username already exists - this is expected if running after a previous test
                error_text = response.text.lower()
                if "already" in error_text or "exists" in error_text or "taken" in error_text:
                    print(f"[{timestamp()}] [REGISTER] ℹ User already exists: {creds['email']} - logging in instead")
                    response.success()  # Not a failure, just duplicate
                    self._login_after_register(creds["email"], creds["password"])
                else:
                    print(f"[{timestamp()}] [REGISTER] ✗ Bad request (400): {response.text[:300]}")
                    response.failure(f"Registration failed: {response.status_code}")
                    raise StopUser()
            
            elif response.status_code == 422:
                # Validation error - log details
                print(f"[{timestamp()}] [REGISTER] ✗ Validation error (422): {response.text}")
                response.failure(f"Validation error: {response.status_code}")
                raise StopUser()
            
            else:
                error_msg = f"Registration failed: {response.status_code}"
                response.failure(error_msg)
                raise StopUser()
    
    def _login_after_register(self, email: str, password: str):
        """Login immediately after registration to get access token."""
        login_data = {
            "email": email,
            "password": password,
        }
        
<<<<<<< HEAD
        login_start = time.time()
        print(f"[{timestamp()}] [LOGIN] → Sending login request for: {email}")
        
        with self.client.post(
            "/api/auth/users/login",
=======
        # Use correct endpoint based on codebase (legacy vs new)
        login_endpoint = "/users/login" if self.config.is_legacy_api else "/api/auth/users/login"
        
        login_start = time.time()
        print(f"[{timestamp()}] [LOGIN] → Sending login request for: {email} (endpoint: {login_endpoint})")
        
        with self.client.post(
            login_endpoint,
>>>>>>> f704b47 (feat(load-testing): support old codebase comparison with US-STAG region)
            json=login_data,
            headers={"Content-Type": "application/json"},
            name="[Auth] Login (post-register)",
            catch_response=True
        ) as response:
            login_duration = (time.time() - login_start) * 1000  # Convert to ms
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access_token")
                self.user_id = data.get("user_id") or data.get("id")
                response.success()
                print(f"[{timestamp()}] [LOGIN] ← Response: 200 in {login_duration:.0f}ms | ✓ Logged in: {email}")
            else:
                # Registration succeeded but login failed - log details for debugging
                print(f"[{timestamp()}] [LOGIN] ← Response: {response.status_code} in {login_duration:.0f}ms | ✗ FAILED: {email}")
                print(f"[{timestamp()}] [LOGIN] Error body: {response.text[:500]}")
                response.failure(f"Post-register login failed: {response.status_code}")
                raise StopUser()
        
    @task(1)
    def do_nothing(self):
        """
        Placeholder task that does nothing.
        
        Locust requires at least one @task method to run.
        This keeps the user "alive" after registration without making extra requests.
        """
        # User just waits after registration - simulates reading the welcome page
        pass


class RegistrationThenChatUser(RegistrationUser):
    """
    User that registers, then immediately starts chatting.
    
    Combines registration load test with chat load test.
    Realistic scenario: new user signs up and starts using the simulation.
    """
    
    wait_time = between(3, 8)
    
    # Import chat functionality
    simulation_instance_id: Optional[int] = None
    persona_id: Optional[int] = None
    messages_sent: int = 0
    max_messages_per_session: int = 5  # Fewer messages for new users
    
    def on_start(self):
        """Register and then load a simulation."""
        super().on_start()
        self._load_simulation_for_new_user()
    
    def _load_simulation_for_new_user(self):
        """Get a simulation for the newly registered user."""
        config = get_config()
        self.simulation_instance_id = config.simulation_instance_id
        
        # Try to access the simulation
        sim_data = self._api_get(
            f"/api/simulation/instances/{self.simulation_instance_id}",
            name="[Sim] Get Instance (new user)"
        )
        
        if sim_data:
            personas = sim_data.get("personas", [])
            if personas:
                self.persona_id = personas[0].get("id")
    
    @task(10)
    def send_chat_message(self):
        """Send a chat message (imported from chat_user logic)."""
        if not self.simulation_instance_id:
            return
        
        if self.messages_sent >= self.max_messages_per_session:
            self.messages_sent = 0
            self.think(5, 10)
            return
        
        # Simple messages for new users
        messages = [
            "Hi, I'm new here. Can you help me understand?",
            "What should I know about this situation?",
            "Can you explain your perspective?",
            "Thank you, that's helpful!",
        ]
        
        chat_payload = {
            "message": random.choice(messages),
            "simulation_instance_id": self.simulation_instance_id,
        }
        
        if self.persona_id:
            chat_payload["persona_id"] = self.persona_id
        
        with self.client.post(
            "/api/simulation/chat",
            json=chat_payload,
            headers=self._get_auth_headers(),
            name="[Chat] Send Message (new user)",
            catch_response=True,
            timeout=60
        ) as response:
            if response.status_code == 200:
                response.success()
                self.messages_sent += 1
            elif response.status_code == 429:
                response.failure("Rate limited")
                self.think(10, 20)
            else:
                response.failure(f"Chat failed: {response.status_code}")

