"""
Locust Load Testing for n-aible Platform
-----------------------------------------
Simulates realistic user behavior for demo preparation and performance testing.

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


class StudentUser(HttpUser):
    """
    Simulates a student user's behavior during the demo.

    Typical journey:
    1. Register (once)
    2. Login
    3. View dashboard
    4. Browse cohorts
    5. Check notifications
    6. Start simulation (occasionally)
    """

    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks (realistic human behavior)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Generate unique user data
        random_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        self.username = f"loadtest_{random_id}"
        self.email = f"{self.username}@loadtest.com"
        self.password = "LoadTest123!"
        self.full_name = f"Load Test User {random_id[:4]}"
        self.access_token = None
        self.user_registered = False

    def on_start(self):
        """Called when a user starts - register and login"""
        self.register()
        if self.user_registered:
            self.login()

    def register(self):
        """Register a new student user"""
        with self.client.post(
            "/api/auth/register",
            json={
                "email": self.email,
                "password": self.password,
                "full_name": self.full_name,
                "username": self.username,
                "role": "student"
            },
            catch_response=True,
            name="Register Student"
        ) as response:
            if response.status_code == 200:
                self.user_registered = True
                response.success()
            elif response.status_code == 400 and "already taken" in response.text:
                # User already exists, that's ok for load testing
                self.user_registered = True
                response.success()
            else:
                response.failure(f"Registration failed: {response.status_code}")

    def login(self):
        """Login with registered credentials"""
        with self.client.post(
            "/api/auth/login",
            json={
                "username": self.username,
                "password": self.password
            },
            catch_response=True,
            name="Login"
        ) as response:
            if response.status_code == 200:
                # Token is set in httpOnly cookie, no need to extract
                response.success()
            else:
                response.failure(f"Login failed: {response.status_code}")
                # Don't continue if login fails
                raise RescheduleTask()

    @task(10)
    def view_dashboard(self):
        """View student dashboard - most common action"""
        with self.client.get(
            "/api/auth/me",
            catch_response=True,
            name="View Dashboard (Auth Check)"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Dashboard load failed: {response.status_code}")

    @task(5)
    def get_notifications(self):
        """Check notifications - common action"""
        with self.client.get(
            "/api/student/notifications?limit=10&offset=0&unread_only=false",
            catch_response=True,
            name="Get Notifications"
        ) as response:
            if response.status_code in [200, 401]:  # 401 is ok if not fully auth'd
                response.success()
            else:
                response.failure(f"Notifications failed: {response.status_code}")

    @task(3)
    def get_cohorts(self):
        """View student cohorts"""
        with self.client.get(
            "/api/student/cohorts",
            catch_response=True,
            name="Get Student Cohorts"
        ) as response:
            if response.status_code in [200, 401]:
                response.success()
            else:
                response.failure(f"Cohorts failed: {response.status_code}")

    @task(2)
    def get_simulations(self):
        """View available simulations"""
        with self.client.get(
            "/api/student/simulation-instances",
            catch_response=True,
            name="Get Simulations"
        ) as response:
            if response.status_code in [200, 401]:
                response.success()
            else:
                response.failure(f"Simulations failed: {response.status_code}")


class ProfessorUser(HttpUser):
    """
    Simulates a professor user's behavior during the demo.

    Typical journey:
    1. Register (once)
    2. Login
    3. View dashboard
    4. Browse scenarios
    5. Check notifications
    6. Upload PDF (occasionally - this is heavy!)
    """

    wait_time = between(2, 5)  # Professors act slightly slower

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        random_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        self.username = f"prof_{random_id}"
        self.email = f"{self.username}@loadtest.com"
        self.password = "LoadTest123!"
        self.full_name = f"Prof {random_id[:4]}"
        self.access_token = None
        self.user_registered = False

    def on_start(self):
        """Called when a user starts"""
        self.register()
        if self.user_registered:
            self.login()

    def register(self):
        """Register a new professor user"""
        with self.client.post(
            "/api/auth/register",
            json={
                "email": self.email,
                "password": self.password,
                "full_name": self.full_name,
                "username": self.username,
                "role": "professor"
            },
            catch_response=True,
            name="Register Professor"
        ) as response:
            if response.status_code == 200:
                self.user_registered = True
                response.success()
            elif response.status_code == 400 and "already taken" in response.text:
                self.user_registered = True
                response.success()
            else:
                response.failure(f"Registration failed: {response.status_code}")

    def login(self):
        """Login with registered credentials"""
        with self.client.post(
            "/api/auth/login",
            json={
                "username": self.username,
                "password": self.password
            },
            catch_response=True,
            name="Login"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Login failed: {response.status_code}")
                raise RescheduleTask()

    @task(10)
    def view_dashboard(self):
        """View professor dashboard"""
        with self.client.get(
            "/api/auth/me",
            catch_response=True,
            name="View Dashboard (Auth Check)"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Dashboard failed: {response.status_code}")

    @task(5)
    def get_scenarios(self):
        """Get all scenarios (published + draft)"""
        with self.client.get(
            "/api/publishing/scenarios/?status=active",
            catch_response=True,
            name="Get Published Scenarios"
        ) as response:
            if response.status_code in [200, 401]:
                response.success()
            else:
                response.failure(f"Scenarios failed: {response.status_code}")

    @task(3)
    def get_cohorts(self):
        """View professor cohorts"""
        with self.client.get(
            "/api/professor/cohorts",
            catch_response=True,
            name="Get Professor Cohorts"
        ) as response:
            if response.status_code in [200, 401]:
                response.success()
            else:
                response.failure(f"Cohorts failed: {response.status_code}")

    @task(2)
    def get_notifications(self):
        """Check notifications"""
        with self.client.get(
            "/api/professor/notifications?limit=10&offset=0&unread_only=false",
            catch_response=True,
            name="Get Notifications"
        ) as response:
            if response.status_code in [200, 401]:
                response.success()
            else:
                response.failure(f"Notifications failed: {response.status_code}")


# Event handlers for reporting
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when the test starts"""
    print("\n" + "="*60)
    print("🚀 LOAD TEST STARTED")
    print("="*60)
    print(f"Target: {environment.host}")
    print(f"Users: {environment.runner.target_user_count if hasattr(environment.runner, 'target_user_count') else 'N/A'}")
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
