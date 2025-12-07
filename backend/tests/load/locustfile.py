"""
Locust Load Testing for n-aible Platform (feature/test-suite-auth branch)
-----------------------------------------
Simplified load testing for the new modular architecture.
Only tests implemented endpoints: authentication and registration.

Run tests:
    # Demo scenario (60 concurrent users)
    locust -f tests/load/locustfile.py --users 60 --spawn-rate 10 --run-time 5m --headless

    # Registration stress test (200 concurrent users)
    locust -f tests/load/locustfile.py --users 200 --spawn-rate 20 --run-time 3m --headless

    # Interactive mode with Web UI
    locust -f tests/load/locustfile.py
    # Then open http://localhost:8089
"""

import random
import string
from locust import HttpUser, task, between, events
from locust.exception import RescheduleTask


class AuthUser(HttpUser):
    """
    Simulates a user testing the authentication system.

    Typical journey:
    1. Register (once)
    2. Login
    3. Check auth status
    4. Logout (occasionally)
    """

    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Generate unique user data
        random_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        self.username = f"loadtest_{random_id}"
        self.email = f"{self.username}@loadtest.com"
        self.password = "LoadTest123!"
        self.full_name = f"Load Test User {random_id[:4]}"
        self.role = random.choice(["student", "professor"])
        self.user_registered = False
        self.logged_in = False

    def on_start(self):
        """Called when a user starts - register and login"""
        self.register()
        if self.user_registered:
            self.login()

    def register(self):
        """Register a new user"""
        with self.client.post(
            "/api/auth/users/register",
            json={
                "email": self.email,
                "password": self.password,
                "full_name": self.full_name,
                "username": self.username,
                "role": self.role
            },
            catch_response=True,
            name="Register User"
        ) as response:
            if response.status_code == 200:
                self.user_registered = True
                self.logged_in = True  # Registration also logs in (sets cookie)
                response.success()
            elif response.status_code == 400 and "already" in response.text.lower():
                # User already exists, that's ok for load testing
                self.user_registered = True
                response.success()
            else:
                response.failure(f"Registration failed: {response.status_code} - {response.text}")

    def login(self):
        """Login with registered credentials"""
        with self.client.post(
            "/api/auth/users/login",
            json={
                "email": self.email,
                "password": self.password
            },
            catch_response=True,
            name="Login"
        ) as response:
            if response.status_code == 200:
                self.logged_in = True
                response.success()
            else:
                response.failure(f"Login failed: {response.status_code} - {response.text}")
                # Don't continue if login fails
                raise RescheduleTask()

    @task(10)
    def check_auth_status(self):
        """Check authentication status - most common action"""
        if not self.logged_in:
            return

        with self.client.get(
            "/api/auth/users/status",
            catch_response=True,
            name="Check Auth Status"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Auth status check failed: {response.status_code}")

    @task(2)
    def logout_and_login(self):
        """Occasionally logout and login again to test the full flow"""
        if not self.logged_in:
            return

        # Logout
        with self.client.post(
            "/api/auth/users/logout",
            catch_response=True,
            name="Logout"
        ) as response:
            if response.status_code == 200:
                self.logged_in = False
                response.success()
            else:
                response.failure(f"Logout failed: {response.status_code}")
                return

        # Login again
        self.login()

    @task(1)
    def check_email(self):
        """Test email checking endpoint"""
        with self.client.post(
            "/api/auth/users/check-email",
            json={"email": self.email},
            catch_response=True,
            name="Check Email Exists"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Check email failed: {response.status_code}")


# Event handlers for reporting
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when the test starts"""
    print("\n" + "="*60)
    print("🚀 LOAD TEST STARTED (AUTH MODULE ONLY)")
    print("="*60)
    print(f"Target: {environment.host}")
    print(f"Users: {environment.runner.target_user_count if hasattr(environment.runner, 'target_user_count') else 'N/A'}")
    print("Testing: Authentication endpoints only")
    print("="*60 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when the test stops - print summary"""
    print("\n" + "="*60)
    print("🏁 LOAD TEST COMPLETED")
    print("="*60)

    stats = environment.stats
    total_requests = stats.total.num_requests
    total_failures = stats.total.num_failures

    if total_requests > 0:
        success_rate = ((total_requests - total_failures) / total_requests) * 100
        print(f"Total Requests: {total_requests}")
        print(f"Failures: {total_failures}")
        print(f"Success Rate: {success_rate:.2f}%")
        print(f"Average Response Time: {stats.total.avg_response_time:.2f}ms")
        print(f"Max Response Time: {stats.total.max_response_time:.2f}ms")
        print(f"Requests/sec: {stats.total.total_rps:.2f}")

        # Connection pool analysis (estimate)
        concurrent_requests = environment.runner.user_count if hasattr(environment.runner, 'user_count') else 0
        estimated_connections = concurrent_requests * 2  # Rough estimate
        print(f"\nEstimated Peak Connections: ~{estimated_connections} (User count × 2)")

        if estimated_connections > 120:
            print("⚠️  Peak connections may have exceeded 80% pool capacity (120/150)")

        print("="*60 + "\n")

        # Recommendations
        if success_rate < 95:
            print("⚠️  SUCCESS RATE LOW - Check connection pool and database capacity")
        elif stats.total.avg_response_time > 2000:
            print("⚠️  RESPONSE TIMES HIGH - Consider optimizing queries or increasing resources")
        else:
            print("✅ Performance looks good! System handled load well.")
    else:
        print("No requests were made")

    print("\n")
