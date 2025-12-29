#!/usr/bin/env python3
"""
End-to-End Streaming Load Test

This test replicates the ACTUAL frontend user experience:
1. Login via API
2. Start simulation (creates user progress)
3. Send "begin" message via STREAMING endpoint
4. Send chat messages via STREAMING endpoint
5. Measure Time-To-First-Byte (TTFB) and total response time

The key difference from chat_load_test.py:
- Uses /api/simulation/linear-chat-stream (SSE streaming) like the real frontend
- Measures TTFB which is what users actually perceive
- Consumes the entire stream to measure complete response time

Run:
    locust -f scenarios/e2e_streaming_test.py --headless -u 10 -r 2 -t 2m
"""

import json
import logging
import time
import random
from typing import Optional
from datetime import datetime, timedelta

from locust import HttpUser, task, between, events

# Import shared config
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import get_config, LoadTestConfig

logger = logging.getLogger("e2e_streaming_test")
logging.basicConfig(level=logging.INFO)

# Get configuration
config = get_config()


class E2EStreamingUser(HttpUser):
    """
    Simulates a real user experience with streaming responses.
    
    This user:
    1. Logs in
    2. Starts a simulation
    3. Sends "begin" to start the conversation
    4. Sends multiple chat messages, consuming the full stream each time
    5. Measures both TTFB and total response time
    """
    
    wait_time = between(config.min_wait, config.max_wait)
    host = config.base_url
    
    # User state
    user_number: int = 0
    logged_in: bool = False  # Changed: track login status, not token
    user_progress_id: Optional[int] = None
    current_scene_id: Optional[int] = None
    simulation_started: bool = False
    messages_sent: int = 0
    max_messages_per_session: int = 10
    
    # Sample messages to send
    SAMPLE_MESSAGES = [
        "Hello! Can you tell me more about the situation?",
        "What are the main challenges we're facing here?",
        "How do you think we should approach this problem?",
        "That's interesting. Can you elaborate on that point?",
        "What would you recommend as the next step?",
        "Are there any concerns you have about this approach?",
        "How does that affect your day-to-day work?",
        "What resources would you need to implement this?",
        "Can you give me a specific example?",
        "What would success look like in this scenario?",
    ]
    
    def on_start(self):
        """Called when a simulated user starts."""
        # Assign unique user number
        self.user_number = random.randint(1, config.test_user_count)
        self.email = f"{config.test_user_prefix}{self.user_number}{config.test_user_domain}"
        
        logger.info(f"[E2E] User {self.user_number}: Starting with email {self.email}")
        
        # Login
        if not self._login():
            logger.error(f"[E2E] User {self.user_number}: Login failed")
            # Don't stop the whole test - just mark this user as not ready
            return
        
        # Start simulation
        self._start_simulation()
    
    def _login(self) -> bool:
        """
        Login via cookie-based authentication.
        
        IMPORTANT: Your backend uses HTTP-only cookies for auth.
        - Response body has access_token="" (empty)
        - Real token is set via Set-Cookie header
        - Locust's self.client (requests.Session) auto-handles cookies
        """
        try:
            with self.client.post(
                "/api/auth/users/login",
                json={
                    "email": self.email,
                    "password": config.test_password
                },
                name="[E2E] Login",
                catch_response=True
            ) as response:
                if response.status_code == 200:
                    # Success! Cookie is automatically stored by Locust's session
                    self.logged_in = True
                    logger.info(f"[E2E] User {self.user_number}: ✓ Logged in (cookie auth)")
                    response.success()
                    return True
                else:
                    # Log the error response body for debugging
                    try:
                        error_body = response.text[:200]
                    except:
                        error_body = "Unable to read error body"
                    response.failure(f"Login failed: {response.status_code}")
                    logger.error(f"[E2E] User {self.user_number}: Login failed: {response.status_code} - {error_body}")
                    return False
        except Exception as e:
            logger.error(f"[E2E] User {self.user_number}: Login exception: {e}")
            return False
    
    def _get_headers(self) -> dict:
        """Get headers for requests. Auth is handled via cookies automatically."""
        return {
            "Content-Type": "application/json",
            "Accept": "text/event-stream"
        }
    
    def _start_simulation(self):
        """Start a new simulation session."""
        if not self.logged_in:
            return
        
        try:
            with self.client.post(
                "/api/simulation/start",
                json={"simulation_id": config.simulation_id},
                headers=self._get_headers(),
                name="[E2E] Start Simulation",
                catch_response=True
            ) as response:
                if response.status_code == 200:
                    data = response.json()
                    self.user_progress_id = data.get("user_progress_id")
                    self.current_scene_id = data.get("current_scene", {}).get("id")
                    self.simulation_started = True
                    self.messages_sent = 0
                    
                    logger.info(
                        f"[E2E] User {self.user_number}: ✓ Started simulation | "
                        f"progress_id={self.user_progress_id}, scene_id={self.current_scene_id}"
                    )
                    response.success()
                else:
                    error_msg = f"Start failed: {response.status_code}"
                    response.failure(error_msg)
                    logger.error(f"[E2E] User {self.user_number}: {error_msg}")
                    self.simulation_started = False
        except Exception as e:
            logger.error(f"[E2E] User {self.user_number}: Start simulation exception: {e}")
            self.simulation_started = False
    
    def _send_streaming_message(self, message: str, request_name: str) -> bool:
        """
        Send a message via the streaming endpoint and consume the full response.
        
        Measures:
        - TTFB (Time To First Byte): When the first chunk arrives
        - Total time: When the entire stream is consumed
        
        Returns True if successful, False otherwise.
        """
        if not self.logged_in or not self.user_progress_id:
            return False
        
        start_time = time.time()
        ttfb = None
        total_response = ""
        chunk_count = 0
        
        try:
            # Make streaming request
            with self.client.post(
                "/api/simulation/linear-chat-stream",
                json={
                    "simulation_id": config.simulation_id,
                    "user_id": 1,  # Backend extracts from token anyway
                    "scene_id": self.current_scene_id,
                    "message": message,
                    "user_progress_id": self.user_progress_id
                },
                headers=self._get_headers(),
                name=request_name,
                catch_response=True,
                stream=True  # Enable streaming
            ) as response:
                if response.status_code != 200:
                    response.failure(f"Stream failed: {response.status_code}")
                    return False
                
                # Consume the stream
                for chunk in response.iter_lines():
                    if chunk:
                        chunk_count += 1
                        
                        # Record TTFB on first chunk
                        if ttfb is None:
                            ttfb = (time.time() - start_time) * 1000  # ms
                        
                        # Decode chunk
                        try:
                            chunk_str = chunk.decode('utf-8') if isinstance(chunk, bytes) else chunk
                            if chunk_str.startswith("data: "):
                                data = json.loads(chunk_str[6:])
                                content = data.get("content", "")
                                total_response += content
                                
                                # Check for completion
                                if data.get("done", False):
                                    break
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            pass
                
                total_time = (time.time() - start_time) * 1000  # ms
                
                # Log metrics
                if ttfb:
                    ttfb_status = "✓" if ttfb < 1000 else "⚠" if ttfb < 3000 else "✗"
                    logger.info(
                        f"[E2E] User {self.user_number}: {request_name} | "
                        f"TTFB={ttfb:.0f}ms {ttfb_status} | Total={total_time:.0f}ms | "
                        f"Chunks={chunk_count} | Chars={len(total_response)}"
                    )
                    
                    # Fire custom TTFB event for tracking
                    events.request.fire(
                        request_type="STREAM_TTFB",
                        name=f"{request_name} (TTFB)",
                        response_time=ttfb,
                        response_length=0,
                        exception=None,
                        context={}
                    )
                
                response.success()
                return True
                
        except Exception as e:
            logger.error(f"[E2E] User {self.user_number}: Stream exception: {e}")
            return False
    
    @task(1)
    def send_begin_message(self):
        """Send the 'begin' message to start the conversation."""
        # If not logged in, try to login first
        if not self.logged_in:
            if not self._login():
                return
        
        if not self.simulation_started:
            self._start_simulation()
            return
        
        if self.messages_sent == 0:
            logger.info(f"[E2E] User {self.user_number}: → Sending 'begin' message...")
            success = self._send_streaming_message("begin", "[E2E] Chat Begin (Stream)")
            if success:
                self.messages_sent += 1
    
    @task(10)
    def send_chat_message(self):
        """Send a regular chat message."""
        # Skip if not logged in or simulation not started
        if not self.logged_in or not self.simulation_started:
            return
        
        # Ensure begin was sent first
        if self.messages_sent == 0:
            self.send_begin_message()
            return
        
        # Check if session should be restarted
        if self.messages_sent >= self.max_messages_per_session:
            logger.info(f"[E2E] User {self.user_number}: ↻ Session complete - restarting")
            self._start_simulation()
            return
        
        # Send a chat message
        message = random.choice(self.SAMPLE_MESSAGES)
        logger.info(
            f"[E2E] User {self.user_number}: → Sending message #{self.messages_sent}: "
            f"'{message[:40]}...'"
        )
        
        success = self._send_streaming_message(message, "[E2E] Chat Message (Stream)")
        if success:
            self.messages_sent += 1


# ============================================================================
# Test Lifecycle Events
# ============================================================================

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    logger.info("\n" + "=" * 60)
    logger.info("E2E STREAMING LOAD TEST STARTING")
    logger.info("=" * 60)
    logger.info(f"  Target:      {config.base_url}")
    logger.info(f"  Region:      {config.target_region}")
    logger.info(f"  Simulation:  {config.simulation_id}")
    logger.info(f"  Test Users:  {config.test_user_count}")
    logger.info(f"  Endpoint:    /api/simulation/linear-chat-stream (STREAMING)")
    logger.info("=" * 60)
    logger.info("")
    logger.info("This test measures:")
    logger.info("  - TTFB (Time To First Byte): When user sees first response")
    logger.info("  - Total Time: When entire response is received")
    logger.info("  - Stream consumption for realistic load")
    logger.info("")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    stats = environment.stats
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("E2E STREAMING LOAD TEST COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Total Requests: {stats.total.num_requests}")
    logger.info(f"  Total Failures: {stats.total.num_failures}")
    logger.info(f"  Failure Rate: {stats.total.fail_ratio * 100:.2f}%")
    logger.info(f"  Avg Response Time: {stats.total.avg_response_time:.0f}ms")
    logger.info(f"  P95 Response Time: {stats.total.get_response_time_percentile(0.95):.0f}ms")
    logger.info(f"  P99 Response Time: {stats.total.get_response_time_percentile(0.99):.0f}ms")
    logger.info("")
    
    # Print per-endpoint stats
    logger.info("Per-Endpoint Statistics:")
    logger.info("-" * 60)
    for name, entry in sorted(stats.entries.items()):
        if entry.num_requests > 0:
            logger.info(f"  {name[1]}:")  # name is (method, name) tuple
            logger.info(f"    Requests: {entry.num_requests}")
            logger.info(f"    Failures: {entry.num_failures}")
            logger.info(f"    Avg Time: {entry.avg_response_time:.0f}ms")
            logger.info(f"    P95 Time: {entry.get_response_time_percentile(0.95):.0f}ms")
    logger.info("=" * 60)


# Allow running directly
if __name__ == "__main__":
    import os
    os.system(f"locust -f {__file__} --headless -u 10 -r 2 -t 2m --html=reports/e2e_streaming_test.html")

