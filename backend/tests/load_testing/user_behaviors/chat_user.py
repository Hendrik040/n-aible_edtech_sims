"""
Chat user behavior for load testing the simulation chat experience.
Simulates realistic student interactions with AI personas.
"""

import sys
import os
import random
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
from locust import task, between
from locust.exception import StopUser

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from user_behaviors.base import BaseLoadTestUser
from config import get_config


def timestamp() -> str:
    """Return current timestamp in HH:MM:SS.mmm format for logging."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def format_response_time(seconds: float) -> str:
    """Format response time with UX assessment."""
    ms = seconds * 1000
    if ms < 500:
        return f"{ms:.0f}ms ✓ (excellent)"
    elif ms < 1000:
        return f"{ms:.0f}ms ✓ (good)"
    elif ms < 2000:
        return f"{ms:.0f}ms ⚠ (acceptable)"
    elif ms < 5000:
        return f"{ms:.0f}ms ⚠ (slow)"
    else:
        return f"{ms:.0f}ms ✗ (poor UX)"


# Sample messages that simulate realistic student interactions
STUDENT_MESSAGES = [
    # Opening messages (after "begin")
    "Hi, I'd like to discuss the current situation.",
    "Hello! Can you tell me more about your perspective?",
    "Good morning, I'm here to learn about your experience.",
    
    # Follow-up questions
    "That's interesting. Can you elaborate on that point?",
    "How does that affect your daily work?",
    "What challenges do you face with this approach?",
    "Could you give me a specific example?",
    
    # Probing questions
    "What would you change if you could?",
    "How do you think we could improve this situation?",
    "What's the most important thing I should understand?",
    "Are there any concerns you haven't mentioned yet?",
    
    # Closing messages
    "Thank you for sharing your insights.",
    "This has been very helpful. Any final thoughts?",
    "I appreciate your time. Is there anything else?",
]


class ChatSimulationUser(BaseLoadTestUser):
    """
    Simulates a student using the chat simulation feature.
    
    Flow:
    1. Login (handled by base class)
    2. Start simulation → Get user_progress_id
    3. Send "begin" to initialize the simulation
    4. Send multiple chat messages with realistic timing
    5. Optionally end simulation
    
    API Endpoints Used:
    - POST /api/simulation/start (start simulation)
    - POST /api/simulation/linear-chat (send messages - non-streaming for testing)
    """
    
    # Realistic timing: students read responses and think before replying
    wait_time = between(5, 15)
    
    # Track simulation state
    user_progress_id: Optional[int] = None
    current_scene_id: Optional[int] = None
    simulation_started: bool = False
    messages_sent: int = 0
    max_messages_per_session: int = 10
    
    def on_start(self):
        """Initialize user, login, and start simulation."""
        super().on_start()
        self._start_simulation()
    
    def _start_simulation(self):
        """Start a new simulation and get user_progress_id."""
        config = get_config()
        simulation_id = config.simulation_id
        
        print(f"[{timestamp()}] [SIM] User {self._user_number}: → Starting simulation {simulation_id}...")
        start_time = time.time()
        
        with self.client.post(
            "/api/simulation/start",
            json={"simulation_id": simulation_id},
            headers=self._get_auth_headers(),
            name="[Sim] Start Simulation",
            catch_response=True,
            timeout=30
        ) as response:
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                self.user_progress_id = data.get("user_progress_id")
                
                # Get current scene info
                current_scene = data.get("current_scene", {})
                self.current_scene_id = current_scene.get("id")
                
                response.success()
                
                print(f"[{timestamp()}] [SIM] User {self._user_number}: ← Started simulation | "
                      f"progress_id={self.user_progress_id} | {format_response_time(response_time)}")
                
                # Send "begin" to initialize the chat
                self._send_begin_message()
                
            elif response.status_code == 404:
                response.failure(f"Simulation {simulation_id} not found")
                print(f"[{timestamp()}] [SIM] User {self._user_number}: ✗ Simulation {simulation_id} not found! "
                      "Configure TEST_SIMULATION_ID in loadtest.env")
                raise StopUser()
            else:
                print(f"[{timestamp()}] [SIM] User {self._user_number}: ✗ Start failed: "
                      f"{response.status_code} | {response.text[:150]}")
                response.failure(f"Start failed: {response.status_code} - {response.text[:200]}")
                raise StopUser()
    
    def _send_begin_message(self):
        """Send the 'begin' message to start the simulation chat."""
        if not self.user_progress_id:
            return
        
        config = get_config()
        print(f"[{timestamp()}] [CHAT] User {self._user_number}: → Sending 'begin' message...")
        start_time = time.time()
        
        with self.client.post(
            "/api/simulation/linear-chat",
            json={
                "user_progress_id": self.user_progress_id,
                "message": "begin",
                "scene_id": self.current_scene_id,
            },
            headers=self._get_auth_headers(),
            name="[Chat] Begin",
            catch_response=True,
            timeout=config.chat_timeout
        ) as response:
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                self.simulation_started = True
                response.success()
                
                print(f"[{timestamp()}] [CHAT] User {self._user_number}: ← 'begin' response received | "
                      f"{format_response_time(response_time)}")
            else:
                response.failure(f"Begin failed: {response.status_code}")
                print(f"[{timestamp()}] [CHAT] User {self._user_number}: ✗ 'begin' FAILED: "
                      f"{response.status_code} | {response.text[:150]}")
    
    @task(10)  # Weight: most common action
    def send_chat_message(self):
        """Send a chat message to the simulation persona."""
        if not self.simulation_started or not self.user_progress_id:
            # Try to start simulation if not started
            if not self.user_progress_id:
                self._start_simulation()
            return
        
        if self.messages_sent >= self.max_messages_per_session:
            # Reset for next round - simulate user starting over
            print(f"[{timestamp()}] [CHAT] User {self._user_number}: ↻ Session complete ({self.max_messages_per_session} messages) - starting new session")
            self.messages_sent = 0
            self._start_simulation()  # Start fresh simulation
            return
        
        # Select a contextually appropriate message
        message = self._select_message()
        config = get_config()
        
        # Build the chat request
        chat_payload = {
            "user_progress_id": self.user_progress_id,
            "message": message,
        }
        
        if self.current_scene_id:
            chat_payload["scene_id"] = self.current_scene_id
        
        # Show truncated message for logging
        msg_preview = message[:30] + "..." if len(message) > 30 else message
        print(f"[{timestamp()}] [CHAT] User {self._user_number}: → Sending msg #{self.messages_sent + 1}: \"{msg_preview}\"")
        
        # Send message and measure response time
        start_time = time.time()
        
        with self.client.post(
            "/api/simulation/linear-chat",
            json=chat_payload,
            headers=self._get_auth_headers(),
            name="[Chat] Send Message",
            catch_response=True,
            timeout=config.chat_timeout
        ) as response:
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                response.success()
                self.messages_sent += 1
                
                # Update scene if changed
                data = response.json()
                if data.get("scene_id"):
                    self.current_scene_id = data.get("scene_id")
                
                print(f"[{timestamp()}] [CHAT] User {self._user_number}: ← AI response #{self.messages_sent} | "
                      f"{format_response_time(response_time)}")
            
            elif response.status_code == 429:
                # Rate limited - back off
                print(f"[{timestamp()}] [CHAT] User {self._user_number}: ⚠ Rate limited! Backing off 10-20s")
                response.failure("Rate limited")
                self.think(10, 20)
            
            elif response.status_code in (502, 503, 504):
                # Server overloaded
                print(f"[{timestamp()}] [CHAT] User {self._user_number}: ⚠ Server error {response.status_code}! Backing off 5-10s")
                response.failure(f"Server error: {response.status_code}")
                self.think(5, 10)
            
            elif response.status_code == 404:
                # Session may have expired
                print(f"[{timestamp()}] [CHAT] User {self._user_number}: ⚠ Session expired - will restart")
                response.failure("Session not found")
                self.simulation_started = False
                self.user_progress_id = None
            
            else:
                print(f"[{timestamp()}] [CHAT] User {self._user_number}: ✗ Chat FAILED: "
                      f"{response.status_code} | {response.text[:100]}")
                response.failure(f"Chat failed: {response.status_code} - {response.text[:100]}")
    
    # Note: check_progress task removed - endpoint doesn't exist in current API
    # If you want to add progress checking, implement the endpoint first
    
    def _select_message(self) -> str:
        """Select an appropriate message based on conversation progress."""
        if self.messages_sent == 0:
            # Opening message
            return random.choice(STUDENT_MESSAGES[:3])
        elif self.messages_sent >= self.max_messages_per_session - 2:
            # Closing messages
            return random.choice(STUDENT_MESSAGES[-3:])
        else:
            # Middle of conversation
            return random.choice(STUDENT_MESSAGES[3:-3])
    
    def think(self, min_sec: float, max_sec: float):
        """Simulate user thinking/reading time."""
        time.sleep(random.uniform(min_sec, max_sec))
