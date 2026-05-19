import json
import os
import random
import time
from typing import Any, Dict, Optional

from locust import HttpUser, between, task
from locust.exception import RescheduleTask


def _env_int(name: str, default: int) -> int:
    """Parse an int env var with a safe default."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
SIMULATION_ID = _env_int("SIMULATION_ID", 1)

# Locust user mix (relative weights)
STUDENT_WEIGHT = _env_int("STUDENT_WEIGHT", 9)
# PROFESSOR_WEIGHT will be set after credentials are loaded (see below)
PROFESSOR_WEIGHT_ENV = _env_int("PROFESSOR_WEIGHT", 1)

# Auth for dedicated load-test users
# Support multiple accounts for load testing (comma-separated)
# Example: LOADTEST_STUDENT_EMAILS="student1@test.com,student2@test.com,student3@test.com"
STUDENT_EMAILS = [e.strip() for e in os.getenv("LOADTEST_STUDENT_EMAILS", os.getenv("LOADTEST_STUDENT_EMAIL", "")).split(",") if e.strip()]
STUDENT_PASSWORDS = [p.strip() for p in os.getenv("LOADTEST_STUDENT_PASSWORDS", os.getenv("LOADTEST_STUDENT_PASSWORD", "")).split(",") if p.strip()]
PROFESSOR_EMAILS = [e.strip() for e in os.getenv("LOADTEST_PROFESSOR_EMAILS", os.getenv("LOADTEST_PROFESSOR_EMAIL", "")).split(",") if e.strip()]
PROFESSOR_PASSWORDS = [p.strip() for p in os.getenv("LOADTEST_PROFESSOR_PASSWORDS", os.getenv("LOADTEST_PROFESSOR_PASSWORD", "")).split(",") if p.strip()]

# Fallback to single account for backward compatibility
if not STUDENT_EMAILS and os.getenv("LOADTEST_STUDENT_EMAIL"):
    STUDENT_EMAILS = [os.getenv("LOADTEST_STUDENT_EMAIL")]
if not STUDENT_PASSWORDS and os.getenv("LOADTEST_STUDENT_PASSWORD"):
    STUDENT_PASSWORDS = [os.getenv("LOADTEST_STUDENT_PASSWORD")]
if not PROFESSOR_EMAILS and os.getenv("LOADTEST_PROFESSOR_EMAIL"):
    PROFESSOR_EMAILS = [os.getenv("LOADTEST_PROFESSOR_EMAIL")]
if not PROFESSOR_PASSWORDS and os.getenv("LOADTEST_PROFESSOR_PASSWORD"):
    PROFESSOR_PASSWORDS = [os.getenv("LOADTEST_PROFESSOR_PASSWORD")]

# Persona handle to exercise in messages (e.g. @nick_elliott)
DEFAULT_PERSONA_HANDLE = os.getenv("LOADTEST_PERSONA_HANDLE", "@nick_elliott")

# Set PROFESSOR_WEIGHT to 0 if no professor credentials provided (students only)
# This prevents ProfessorUser from spawning when we only want students
PROFESSOR_WEIGHT = 0 if (not PROFESSOR_EMAILS or not PROFESSOR_PASSWORDS) else PROFESSOR_WEIGHT_ENV

# Debug logging for professor user setup
print(f"\n{'='*70}")
print("PROFESSOR USER SETUP DEBUG:")
print(f"{'='*70}")
print(f"PROFESSOR_EMAILS: {PROFESSOR_EMAILS}")
print(f"PROFESSOR_PASSWORDS: {'SET' if PROFESSOR_PASSWORDS else 'NOT SET'} (length: {len(PROFESSOR_PASSWORDS)})")
print(f"PROFESSOR_WEIGHT_ENV: {PROFESSOR_WEIGHT_ENV}")
print(f"PROFESSOR_WEIGHT (calculated): {PROFESSOR_WEIGHT}")
print(f"Will define ProfessorUser class: {bool(PROFESSOR_EMAILS and PROFESSOR_PASSWORDS)}")
print(f"{'='*70}\n")

# Account availability check - warn if insufficient accounts for load testing
if STUDENT_EMAILS:
    num_student_accounts = len(STUDENT_EMAILS)
    print(f"\n{'='*70}")
    print("LOAD TEST CONFIGURATION CHECK")
    print(f"{'='*70}")
    print(f"✓ Found {num_student_accounts} student account(s):")
    for i, email in enumerate(STUDENT_EMAILS[:5], 1):  # Show first 5
        print(f"  {i}. {email}")
    if num_student_accounts > 5:
        print(f"  ... and {num_student_accounts - 5} more")
    print("\n⚠️  IMPORTANT: When running Locust, limit the number of users to")
    print(f"   match or be less than the number of accounts ({num_student_accounts}).")
    print("   Otherwise, multiple Locust users will share the same accounts,")
    print("   causing conflicts and retries.")
    print(f"\n   Example: locust --users {num_student_accounts} --spawn-rate 5")
    print("   Or create more accounts using: python create_test_accounts.py")
    print(f"{'='*70}\n")
else:
    print("\n⚠️  WARNING: No student accounts configured!")
    print("   Set LOADTEST_STUDENT_EMAILS and LOADTEST_STUDENT_PASSWORDS environment variables.\n")


class BaseSimulationUser(HttpUser):
    """
    Base Locust user that:
    - Authenticates via /users/login
    - For students: Gets simulation instances, starts via instance unique_id
    - For professors: Starts simulation directly via /api/simulation/start
    - Stores user_progress_id and current_scene_id for chat tasks
    """

    host = BASE_URL
    token: Optional[str] = None
    user_progress_id: Optional[int] = None
    current_scene_id: Optional[int] = None
    instance_unique_id: Optional[str] = None  # For student instances
    _begin_sent: bool = False  # Track whether "begin" has been sent for this simulation

    # Subclasses must override these
    login_email: str = ""
    login_password: str = ""
    # Per-instance account selection (set in on_start)
    _selected_email: Optional[str] = None
    _selected_password: Optional[str] = None
    
    def _log(self, message: str) -> None:
        # Simple, low-volume logging to Locust console
        self.environment.events.request.fire(
            request_type="LOG",
            name="log",
            response_time=0,
            response_length=0,
            exception=None,
            context={"user_class": self.__class__.__name__, "message": message},
        )

    abstract = True  # prevent Locust from instantiating this base class
    
    # Class-level counter for account distribution
    _user_counter = 0
    _counter_lock = None  # Will be initialized on first use
    
    # Class-level tracking for concurrent simulations
    _active_simulations = 0
    _simulation_lock = None  # Will be initialized on first use
    _simulation_start_times: Dict[str, float] = {}  # unique_id -> timestamp
    
    def _increment_active_simulations(self, unique_id: str) -> None:
        """Increment active simulation counter and log."""
        try:
            from gevent.lock import Semaphore
            if BaseSimulationUser._simulation_lock is None:
                BaseSimulationUser._simulation_lock = Semaphore(1)
        except ImportError:
            import threading
            if BaseSimulationUser._simulation_lock is None:
                BaseSimulationUser._simulation_lock = threading.Lock()
        
        BaseSimulationUser._simulation_lock.acquire()
        try:
            BaseSimulationUser._active_simulations += 1
            BaseSimulationUser._simulation_start_times[unique_id] = time.time()
            active_count = BaseSimulationUser._active_simulations
        finally:
            BaseSimulationUser._simulation_lock.release()
        
        self._log(f"🚀 [CONCURRENT: {active_count}] Started simulation: {unique_id}")
    
    @classmethod
    def get_active_simulation_count(cls) -> int:
        """Get current count of active simulations."""
        return cls._active_simulations
    
    @classmethod
    def get_simulation_stats(cls) -> Dict[str, Any]:
        """Get statistics about active simulations."""
        try:
            from gevent.lock import Semaphore
            if BaseSimulationUser._simulation_lock is None:
                BaseSimulationUser._simulation_lock = Semaphore(1)
        except ImportError:
            import threading
            if BaseSimulationUser._simulation_lock is None:
                BaseSimulationUser._simulation_lock = threading.Lock()
        
        BaseSimulationUser._simulation_lock.acquire()
        try:
            active_count = BaseSimulationUser._active_simulations
            total_started = len(BaseSimulationUser._simulation_start_times)
            # Calculate average duration for active simulations
            now = time.time()
            durations = [now - start_time for start_time in BaseSimulationUser._simulation_start_times.values()]
            avg_duration = sum(durations) / len(durations) if durations else 0
        finally:
            BaseSimulationUser._simulation_lock.release()
        
        return {
            "active_simulations": active_count,
            "total_started": total_started,
            "avg_duration_seconds": avg_duration
        }

    def on_start(self) -> None:
        """Configure HTTP client with proper headers and select account."""
        # Set default headers to ensure proper HTTP request formatting
        # This helps avoid 'Invalid HTTP request received' warnings from uvicorn
        self.client.headers.update({
            "User-Agent": "Locust/load-test",
            "Connection": "keep-alive",
        })
        
        # Select an account using round-robin distribution
        # This distributes accounts evenly across all Locust users to avoid race conditions
        # Each Locust user gets a unique account (modulo number of accounts)
        if isinstance(self.login_email, list) and len(self.login_email) > 0:
            # Use a gevent-safe counter to assign accounts
            # This ensures each user instance gets a different account
            # Locust uses gevent (greenlets), so we use gevent's lock
            try:
                from gevent.lock import Semaphore
                if BaseSimulationUser._counter_lock is None:
                    BaseSimulationUser._counter_lock = Semaphore(1)
            except ImportError:
                # Fallback if gevent not available (shouldn't happen with Locust)
                import threading
                if BaseSimulationUser._counter_lock is None:
                    BaseSimulationUser._counter_lock = threading.Lock()
            
            BaseSimulationUser._counter_lock.acquire()
            try:
                idx = BaseSimulationUser._user_counter % len(self.login_email)
                BaseSimulationUser._user_counter += 1
            finally:
                BaseSimulationUser._counter_lock.release()
            
            self._selected_email = self.login_email[idx]
            self._selected_password = self.login_password[idx] if isinstance(self.login_password, list) and idx < len(self.login_password) else self.login_password
            
            self._log(f"User assigned account {idx}: {self._selected_email}")
            
            # Warn if there aren't enough accounts (some users will share accounts)
            total_users = getattr(self.environment, 'runner', None)
            if total_users and hasattr(total_users, 'user_count'):
                if total_users.user_count > len(self.login_email):
                    self._log(
                        f"⚠️  CRITICAL: Only {len(self.login_email)} account(s) available but "
                        f"{total_users.user_count} Locust user(s) spawned! "
                        f"Multiple users are sharing the same accounts, causing conflicts. "
                        f"Either create more accounts or limit users to {len(self.login_email)}."
                    )
        elif self.login_email and self.login_password:
            self._selected_email = self.login_email
            self._selected_password = self.login_password
        else:
            # Misconfiguration – fail fast so you notice
            raise RescheduleTask(f"Missing credentials for {self.__class__.__name__}")

        self._authenticate()
        # Subclasses will override _start_simulation to handle their specific flow
        # Retry simulation start up to 3 times if it fails
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self._start_simulation()
                # Verify that simulation was actually started
                if self.user_progress_id:
                    self._log(f"✓ Simulation started successfully: user_progress_id={self.user_progress_id}")
                    break
                else:
                    if attempt < max_retries - 1:
                        self._log(f"⚠️ Simulation start attempt {attempt + 1} did not set user_progress_id, retrying...")
                        time.sleep(1)  # Brief delay before retry
                    else:
                        self._log(f"❌ Failed to start simulation after {max_retries} attempts - user_progress_id is None")
            except RescheduleTask as e:
                if attempt < max_retries - 1:
                    self._log(f"⚠️ Simulation start attempt {attempt + 1} failed: {e}, retrying...")
                    time.sleep(1)  # Brief delay before retry
                else:
                    self._log(f"❌ Failed to start simulation after {max_retries} attempts: {e}")
                    raise
            except Exception as e:
                self._log(f"❌ Unexpected error starting simulation: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                else:
                    raise

    # --- Helpers ---------------------------------------------------------

    def _authenticate(self) -> None:
        """Authenticate and set Authorization header."""
        payload = {"email": self._selected_email, "password": self._selected_password}
        
        # Debug: Log the full URL being used
        full_url = f"{self.host}/api/auth/users/login"
        self._log(f"🔍 Attempting login to: {full_url} with email: {self._selected_email}")

        with self.client.post(
            "/api/auth/users/login",
            json=payload,
            name="auth_login",
            catch_response=True,
        ) as resp:
            # Debug: Log response details
            self._log(f"🔍 Login response: status={resp.status_code}, url={resp.url if hasattr(resp, 'url') else 'N/A'}")
            if resp.text:
                # Log first 200 chars of response
                self._log(f"🔍 Response body: {resp.text[:200]}")
            
            if resp.status_code != 200:
                error_msg = f"Login failed ({resp.status_code}): {resp.text[:500] if resp.text else 'No response body'}"
                self._log(f"❌ {error_msg}")
                resp.failure(error_msg)
                raise RescheduleTask("Login failed")

            # Our API primarily uses an HttpOnly cookie for auth.
            # As long as login returns 200, the cookie is stored on the session
            # and will be sent automatically on subsequent requests.
            # The access_token field may be empty, so we don't require it here.
            self._log(f"✅ Login successful for: {self._selected_email}")
            resp.success()

    def _start_simulation(self) -> None:
        """
        Base implementation - subclasses should override.
        For professors: calls /api/simulation/start directly
        For students: gets instances and starts via instance unique_id
        """
        # Default: direct simulation start (for professors/backward compatibility)
        payload = {"simulation_id": SIMULATION_ID}

        with self.client.post(
            "/api/simulation/start",
            json=payload,
            name="simulation_start",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(
                    f"start_simulation failed ({resp.status_code}): {resp.text}"
                )
                raise RescheduleTask("start_simulation failed")

            try:
                data = resp.json()
            except Exception as exc:  # noqa: BLE001
                resp.failure(f"start_simulation JSON parse error: {exc}")
                raise RescheduleTask("start_simulation JSON parse error") from exc

            self.user_progress_id = data.get("user_progress_id")
            current_scene = data.get("current_scene") or {}
            self.current_scene_id = current_scene.get("id")

            if not self.user_progress_id:
                resp.failure("Missing user_progress_id in start_simulation response")
                raise RescheduleTask("Missing user_progress_id")

            resp.success()

    def _stream_chat(
        self,
        message: str,
        scene_id: Optional[int] = None,
        name: str = "simulation_linear_chat_stream",
        max_events: int = 512,
        timeout_seconds: int = 120,
    ) -> Dict[str, Any]:
        """
        Call /api/simulation/linear-chat-stream and stream until:
        - an event with {"done": true} is seen, OR
        - max_events is reached, OR
        - timeout occurs.

        If the request is queued (HTTP 202), poll for job completion.

        Returns the last parsed JSON payload (if any).
        """
        if not self.user_progress_id:
            raise RescheduleTask("user_progress_id not set before streaming chat")

        body: Dict[str, Any] = {
            "user_progress_id": self.user_progress_id,
            "message": message,
        }
        if scene_id is not None:
            body["scene_id"] = scene_id

        start_time = time.time()
        last_payload: Dict[str, Any] = {}

        with self.client.post(
            "/api/simulation/linear-chat-stream",
            json=body,
            name=name,
            stream=True,
            timeout=timeout_seconds,
            catch_response=True,
        ) as resp:
            # Handle queued requests (HTTP 202)
            if resp.status_code == 202:
                try:
                    # For 202 responses, try to parse JSON directly
                    # Locust's response object should handle this even with stream=True
                    try:
                        queued_response = resp.json()
                    except (AttributeError, ValueError, json.JSONDecodeError):
                        # Fallback: read content manually
                        response_content = b""
                        try:
                            for chunk in resp.iter_content(chunk_size=8192):
                                if chunk:
                                    response_content += chunk
                            response_text = response_content.decode('utf-8')
                            queued_response = json.loads(response_text)
                        except Exception as e:
                            resp.failure(f"linear-chat-stream HTTP 202: failed to parse response: {str(e)[:200]}")
                            return last_payload
                    
                    job_id = queued_response.get("job_id")
                    if not job_id:
                        resp.failure("linear-chat-stream HTTP 202: missing job_id in response")
                        return last_payload
                    
                    # Poll for job completion
                    poll_start = time.time()
                    poll_interval = 0.5  # Poll every 500ms
                    max_poll_time = timeout_seconds - 5  # Reserve 5 seconds for result retrieval
                    
                    while time.time() - poll_start < max_poll_time:
                        status_resp = self.client.get(
                            f"/api/simulation/job/{job_id}/status",
                            name="get_job_status",
                            catch_response=True,
                        )
                        
                        if status_resp.status_code != 200:
                            status_resp.failure(f"get_job_status HTTP {status_resp.status_code}")
                            time.sleep(poll_interval)
                            continue
                        
                        status_data = status_resp.json()
                        job_status = status_data.get("status")
                        
                        if job_status == "completed":
                            # Get the result
                            result_resp = self.client.get(
                                f"/api/simulation/job/{job_id}/result",
                                name="get_job_result",
                                catch_response=True,
                            )
                            
                            if result_resp.status_code == 200:
                                result_data = result_resp.json()
                                # Verify the result contains success indicator
                                if result_data.get("success") is True:
                                    # Result contains chunks (SSE-formatted strings) and success flag
                                    chunks = result_data.get("chunks", [])
                                    if not chunks:
                                        error_msg = f"Job {job_id} completed but has no response chunks"
                                        self._log(f"❌ {error_msg}")
                                        resp.failure(error_msg)
                                        return last_payload
                                    
                                    # Verify that we got a persona response (not just orchestrator)
                                    # Parse chunks to check for persona responses
                                    has_persona_response = False
                                    for chunk in chunks:
                                        if isinstance(chunk, str) and chunk.startswith("data: "):
                                            try:
                                                chunk_data = json.loads(chunk[6:].strip())
                                                # Check if this is a persona response (has persona_name and persona_id)
                                                if isinstance(chunk_data, dict):
                                                    persona_name = chunk_data.get("persona_name")
                                                    persona_id = chunk_data.get("persona_id")
                                                    # Persona responses have a persona_name that's not "ChatOrchestrator"
                                                    if persona_name and persona_name != "ChatOrchestrator" and persona_id:
                                                        has_persona_response = True
                                                        break
                                            except (json.JSONDecodeError, KeyError):
                                                continue
                                    
                                    if has_persona_response:
                                        # Log that we got a persona response
                                        if random.random() < 0.1:  # Log ~10% of successful responses
                                            self._log(f"✓ Got persona response for job {job_id}: {len(chunks)} chunks")
                                    else:
                                        # No persona response found - log warning but don't fail (might be orchestrator response)
                                        if random.random() < 0.2:  # Log ~20% of non-persona responses
                                            self._log(f"⚠️ Job {job_id} completed but no persona response found in {len(chunks)} chunks")
                                    
                                    last_payload = {"done": True, "success": True}
                                    resp.success()
                                    return last_payload
                                else:
                                    error_msg = f"Job {job_id} completed but result indicates failure: {result_data}"
                                    self._log(f"❌ {error_msg}")
                                    resp.failure(error_msg)
                                    return last_payload
                            else:
                                error_msg = f"Failed to get job result: HTTP {result_resp.status_code}, response: {result_resp.text[:200]}"
                                self._log(f"❌ {error_msg}")
                                result_resp.failure(f"get_job_result HTTP {result_resp.status_code}")
                                resp.failure(error_msg)
                                return last_payload
                        
                        elif job_status == "failed":
                            error_msg = status_data.get("error", "Job failed")
                            self._log(f"❌ Job {job_id} failed: {error_msg}")
                            resp.failure(f"Job {job_id} failed: {error_msg}")
                            return last_payload
                        
                        elif job_status in ["pending", "processing"]:
                            # Continue polling
                            time.sleep(poll_interval)
                            continue
                        
                        else:
                            # Unknown status
                            time.sleep(poll_interval)
                            continue
                    
                    # Timeout while polling - log the last status we saw
                    last_status = status_data.get("status") if 'status_data' in locals() else "unknown"
                    self._log(f"⏱️ Job {job_id} did not complete within timeout (last status: {last_status})")
                    resp.failure(f"Job {job_id} did not complete within timeout (last status: {last_status})")
                    return last_payload
                    
                except Exception as exc:  # noqa: BLE001
                    resp.failure(f"linear-chat-stream error handling queued request: {exc}")
                    return last_payload
            
            # Handle direct streaming (HTTP 200)
            elif resp.status_code != 200:
                resp.failure(
                    f"linear-chat-stream HTTP {resp.status_code}: {resp.text}"
                )
                return last_payload

            # Stream the response
            events_seen = 0
            try:
                for raw_line in resp.iter_lines():
                    # Respect timeout at streaming level too
                    if time.time() - start_time > timeout_seconds:
                        resp.failure("linear-chat-stream timeout while reading")
                        break

                    if not raw_line:
                        continue

                    try:
                        line = raw_line.decode("utf-8").strip()
                    except Exception:  # noqa: BLE001
                        continue

                    if not line.startswith("data:"):
                        continue

                    data_str = line[len("data:") :].strip()
                    if not data_str:
                        continue

                    try:
                        payload = json.loads(data_str)
                    except Exception:
                        # Ignore non-JSON data frames (e.g. keep-alives)
                        continue

                    last_payload = payload
                    events_seen += 1

                    # Convention from plan: stop when done == true
                    if isinstance(payload, dict) and payload.get("done") is True:
                        # Verify we got a persona response (not just orchestrator)
                        persona_name = payload.get("persona_name")
                        persona_id = payload.get("persona_id")
                        if persona_name and persona_name != "ChatOrchestrator" and persona_id:
                            # Got a persona response - log occasionally
                            if random.random() < 0.1:  # Log ~10% of persona responses
                                self._log(f"✓ Got persona response: {persona_name} (job completed via direct stream)")
                        break

                    if events_seen >= max_events:
                        break

                resp.success()
            except Exception as exc:  # noqa: BLE001
                resp.failure(f"linear-chat-stream error: {exc}")

        return last_payload


class StudentUser(BaseSimulationUser):
    """
    Simulates a typical student running through a simulation with moderate think time.
    
    Flow:
    1. Authenticate
    2. Get student simulation instances (from cohort assignments)
    3. Start simulation via instance unique_id
    4. Chat using user_progress_id
    """

    weight = STUDENT_WEIGHT

    # Always use list format for account distribution
    # This ensures the round-robin logic in on_start() works correctly
    login_email = STUDENT_EMAILS if STUDENT_EMAILS else []
    login_password = STUDENT_PASSWORDS if STUDENT_PASSWORDS else []
    wait_time = between(2, 5)
    
    def _start_simulation(self) -> None:
        """Get student simulation instances and start via instance unique_id."""
        # Step 1: Get student's simulation instances
        # Note: endpoint is /student-simulation-instances (no /api prefix based on router definition)
        with self.client.get(
            "/student-simulation-instances",
            name="get_student_instances",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(
                    f"get_student_instances failed ({resp.status_code}): {resp.text}"
                )
                raise RescheduleTask("get_student_instances failed")
            
            try:
                instances = resp.json()
                # DEBUG: Log raw response to see what instances were returned
                self._log(f"[DEBUG] API returned {len(instances)} instance(s) for {self._selected_email}")
                if instances:
                    for i, inst in enumerate(instances):
                        self._log(f"  Instance {i}: unique_id={inst.get('unique_id')}, student_id={inst.get('student_id')}, status={inst.get('status')}")
            except Exception as exc:  # noqa: BLE001
                resp.failure(f"get_student_instances JSON parse error: {exc}")
                raise RescheduleTask("get_student_instances JSON parse error") from exc
            
            if not instances or len(instances) == 0:
                error_msg = "No simulation instances found for student. Make sure student is in a cohort with assigned simulations."
                self._log(f"ERROR: {error_msg}")
                resp.failure(error_msg)
                raise RescheduleTask("No simulation instances found")
            
            # CRITICAL: Validate that all instances belong to this student
            student_id_from_response = None
            for instance in instances:
                instance_student_id = instance.get("student_id")
                if instance_student_id:
                    if student_id_from_response is None:
                        student_id_from_response = instance_student_id
                    elif instance_student_id != student_id_from_response:
                        error_msg = f"CRITICAL: Found instances with different student_ids! This should never happen. Instance student_ids: {[inst.get('student_id') for inst in instances]}"
                        self._log(f"ERROR: {error_msg}")
                        resp.failure(error_msg)
                        raise RescheduleTask("Instance student_id mismatch")
            
            # Log all available instances for debugging
            instance_list = [f"{inst.get('unique_id')} (status={inst.get('status')})" for inst in instances]
            self._log(f"Student {self._selected_email} has {len(instances)} instance(s): {', '.join(instance_list)}")
            
            # Use the first available instance (or filter by status if needed)
            # Prefer instances that are not_started or in_progress
            available_instance = None
            for instance in instances:
                status = instance.get("status", "")
                if status in ["not_started", "in_progress"]:
                    available_instance = instance
                    break
            
            # Fallback to first instance if no not_started/in_progress found
            if not available_instance:
                available_instance = instances[0]
            
            self.instance_unique_id = available_instance.get("unique_id")
            instance_id_from_response = available_instance.get("id")
            status_from_response = available_instance.get("status")
            student_id_from_instance = available_instance.get("student_id")
            
            if not self.instance_unique_id:
                error_msg = f"Instance missing unique_id. Instance data: {available_instance}"
                self._log(f"ERROR: {error_msg}")
                resp.failure(error_msg)
                raise RescheduleTask("Instance missing unique_id")
            
            # CRITICAL VALIDATION: Log which instance was selected
            # This should be unique per student - if you see duplicates in logs, there's a problem
            self._log(f"✓ SELECTED: Student {self._selected_email} (student_id={student_id_from_instance}) -> instance unique_id={self.instance_unique_id} (id={instance_id_from_response}, status={status_from_response})")
            resp.success()
        
        # Step 2: Start simulation via instance unique_id
        # Note: endpoint is /student-simulation-instances (no /api prefix based on router definition)
        with self.client.post(
            f"/student-simulation-instances/{self.instance_unique_id}/start-simulation",
            name="start_simulation_from_instance",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                error_text = resp.text[:500] if resp.text else "No error message"
                error_msg = f"start_simulation_from_instance failed ({resp.status_code}): {error_text}"
                self._log(f"ERROR: {error_msg}")
                resp.failure(error_msg)
                raise RescheduleTask(f"start_simulation_from_instance failed: {resp.status_code}")
            
            try:
                data = resp.json()
            except Exception as exc:  # noqa: BLE001
                resp.failure(f"start_simulation_from_instance JSON parse error: {exc}")
                raise RescheduleTask("start_simulation_from_instance JSON parse error") from exc
            
            self.user_progress_id = data.get("user_progress_id")
            current_scene = data.get("current_scene") or {}
            self.current_scene_id = current_scene.get("id")
            is_resuming = data.get("is_resuming", False)
            
            if not self.user_progress_id:
                error_msg = "Missing user_progress_id in start_simulation_from_instance response"
                self._log(f"❌ {error_msg} - Response data: {data}")
                resp.failure(error_msg)
                raise RescheduleTask(error_msg)
            
            action = "Resumed" if is_resuming else "Started"
            self._log(f"✓ {action} simulation for {self._selected_email}: instance={self.instance_unique_id}, user_progress_id={self.user_progress_id}, scene_id={self.current_scene_id}")
            
            # CRITICAL: Verify that the simulation was actually created
            # Check if we can retrieve the simulation to confirm it exists
            if not is_resuming:
                # For new simulations, verify the user_progress_id is valid
                # Note: This is optional verification - if it fails, we still proceed
                try:
                    verify_resp = self.client.get(
                        f"/api/simulation/progress/{self.user_progress_id}",
                        name="verify_user_progress",
                        catch_response=True,
                    )
                    if verify_resp.status_code == 200:
                        verify_data = verify_resp.json()
                        self._log(f"✓ Verified simulation exists: user_progress_id={self.user_progress_id}, simulation_id={verify_data.get('simulation_id')}, status={verify_data.get('simulation_status')}")
                        verify_resp.success()
                    else:
                        # Log warning but don't fail - simulation might still be valid
                        self._log(f"⚠️ Warning: Could not verify simulation after creation: HTTP {verify_resp.status_code} (simulation may still be valid)")
                        verify_resp.failure(f"Could not verify user_progress_id={self.user_progress_id}")
                except Exception as e:
                    # Don't fail if verification fails - simulation might still be valid
                    self._log(f"⚠️ Warning: Exception during simulation verification: {e} (simulation may still be valid)")
            
            # Track active simulation for concurrent monitoring
            if not is_resuming:  # Only track new starts, not resumes
                unique_tracking_id = f"{self._selected_email}:{self.instance_unique_id}"
                self._increment_active_simulations(unique_tracking_id)
                # Reset begin flag for new simulations (not resumes)
                self._begin_sent = False
            
            resp.success()

    @task
    def student_chat_flow(self) -> None:
        """
        Loop of student messages:
        - ALWAYS send "begin" first to start the simulation
        - Then send persona-directed questions.
        """
        if not self.user_progress_id:
            # Try to recover by starting simulation again
            self._start_simulation()
            # If still no user_progress_id, skip this task
            if not self.user_progress_id:
                return

        # ALWAYS send "begin" first if it hasn't been sent yet
        if not self._begin_sent:
            message = "begin"
        else:
            # All messages should include @mentions to personas
            templates = [
                f"{DEFAULT_PERSONA_HANDLE} what should I focus on next?",
                f"{DEFAULT_PERSONA_HANDLE} can you clarify the main risks?",
                f"{DEFAULT_PERSONA_HANDLE} what are the trade-offs I should consider here?",
                f"{DEFAULT_PERSONA_HANDLE} how would you summarize the current situation?",
            ]
            message = random.choice(templates)

        # Log chat activity (only occasionally to avoid spam)
        if random.random() < 0.1:  # Log ~10% of messages
            self._log(f"💬 Chat activity (user_progress_id={self.user_progress_id}, active_sims={self.get_active_simulation_count()})")
        
        last_payload = self._stream_chat(
            message=message,
            scene_id=self.current_scene_id,
            name="student_linear_chat_stream",
        )
        
        # Mark "begin" as sent if we just sent it and got a successful response
        # If it fails, keep _begin_sent=False so we can retry next time
        if message == "begin":
            if last_payload:
                # Check if the response indicates success (either done=True or success=True)
                if isinstance(last_payload, dict) and (last_payload.get("done") is True or last_payload.get("success") is True):
                    self._begin_sent = True
                    self._log(f"✓ 'begin' command sent successfully for user_progress_id={self.user_progress_id}")
                    # Add a small delay to ensure simulation state is fully persisted
                    # before sending the next message
                    time.sleep(0.5)
                else:
                    # Response doesn't indicate success - keep _begin_sent=False to retry
                    self._log(f"⚠️ 'begin' command response unclear: {last_payload}")
            else:
                # No response payload - keep _begin_sent=False to retry
                self._log("⚠️ 'begin' command sent but no response payload received")
    
    @task(1)  # Low weight - runs occasionally
    def log_concurrent_stats(self) -> None:
        """Periodically log concurrent simulation statistics."""
        stats = self.get_simulation_stats()
        self._log(
            f"📊 [STATS] Active simulations: {stats['active_simulations']}, "
            f"Total started: {stats['total_started']}, "
            f"Avg duration: {stats['avg_duration_seconds']:.1f}s"
        )


# Only define ProfessorUser if credentials are provided
# This prevents Locust from trying to spawn it when we only want students
if PROFESSOR_EMAILS and PROFESSOR_PASSWORDS:
    class ProfessorUser(BaseSimulationUser):
        """
        Simulates a professor using the dashboard and playground:
        - Dashboard: Gets cohorts list (tests cached endpoint)
        - Playground: Uses simulation chat for testing
        """

        weight = PROFESSOR_WEIGHT

        # Use list of accounts if multiple provided, otherwise single account
        # Always use list format for account distribution (like StudentUser)
        login_email = PROFESSOR_EMAILS if PROFESSOR_EMAILS else []
        login_password = PROFESSOR_PASSWORDS if PROFESSOR_PASSWORDS else []
        wait_time = between(1, 3)
        
        # Store cohort data for follow-up requests
        cohorts: list = []
        selected_cohort_id: Optional[str] = None

        def _start_simulation(self) -> None:
            """
            Override to skip simulation start for professors in on_start().
            Professors don't need to start simulations for dashboard tasks.
            The professor_playground_flow task will call _start_simulation() if needed.
            """
            # No-op for professors - they'll start simulations in professor_playground_flow if needed
            pass

        def on_start(self) -> None:
            """Override on_start to call parent which handles authentication"""
            # Call parent on_start which handles authentication (and will call our overridden _start_simulation)
            BaseSimulationUser.on_start(self)

        @task(3)  # Higher weight - this is the main dashboard action
        def get_professor_cohorts(self) -> None:
            """Get professor cohorts - tests the cached endpoint we optimized"""
            with self.client.get(
                "/professor/cohorts",
                name="get_professor_cohorts",
                catch_response=True,
            ) as resp:
                if resp.status_code != 200:
                    resp.failure(
                        f"get_professor_cohorts failed ({resp.status_code}): {resp.text[:500]}"
                    )
                    return
                
                try:
                    self.cohorts = resp.json()
                    self._log(f"✓ Got {len(self.cohorts)} cohort(s) for professor {self._selected_email}")
                    
                    # Store first cohort ID for potential follow-up requests
                    if self.cohorts and len(self.cohorts) > 0:
                        self.selected_cohort_id = self.cohorts[0].get("unique_id") or self.cohorts[0].get("id")
                    
                    resp.success()
                except Exception as exc:
                    resp.failure(f"get_professor_cohorts JSON parse error: {exc}")

        @task(1)  # Lower weight - conditional on having cohorts
        def get_professor_cohort_details(self) -> None:
            """Get details for a specific cohort"""
            if not self.selected_cohort_id:
                # Try to get cohorts first
                self.get_professor_cohorts()
            
            if not self.selected_cohort_id:
                # Still no cohort ID, skip this task
                return
            
            with self.client.get(
                f"/professor/cohorts/{self.selected_cohort_id}",
                name="get_professor_cohort_details",
                catch_response=True,
            ) as resp:
                if resp.status_code == 404:
                    # Cohort might have been deleted, reset and skip
                    self.selected_cohort_id = None
                    resp.success()  # Not a failure, just not available
                    return
                elif resp.status_code != 200:
                    resp.failure(
                        f"get_professor_cohort_details failed ({resp.status_code}): {resp.text[:500]}"
                    )
                    return
                
                try:
                    cohort_data = resp.json()
                    self._log(f"✓ Got cohort details for {self.selected_cohort_id}")
                    resp.success()
                except Exception as exc:
                    resp.failure(f"get_professor_cohort_details JSON parse error: {exc}")

        @task(2)  # Medium weight - professor playground flow
        def professor_playground_flow(self) -> None:
            """Professor using simulation playground for testing"""
            if not self.user_progress_id:
                # Call base class _start_simulation directly since we override it to be a no-op for on_start()
                BaseSimulationUser._start_simulation(self)

            complex_prompts = [
                (
                    f"{DEFAULT_PERSONA_HANDLE} provide a detailed analysis of the "
                    "strategic risks inherent in our current position. Include at "
                    "least three concrete recommendations."
                ),
                (
                    f"{DEFAULT_PERSONA_HANDLE} assume you are preparing teaching notes "
                    "for this scene. What key learning objectives should students hit "
                    "by the end of this interaction?"
                ),
                (
                    f"{DEFAULT_PERSONA_HANDLE} critique the student's last response "
                    "with a focus on depth of reasoning and stakeholder awareness."
                ),
            ]

            message = random.choice(complex_prompts)

            self._stream_chat(
                message=message,
                scene_id=self.current_scene_id,
                name="professor_linear_chat_stream",
            )

