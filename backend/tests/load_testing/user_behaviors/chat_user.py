"""
Chat user behavior for load testing the simulation chat experience.
Simulates realistic student interactions with AI personas.
"""

import random
import time
from typing import Optional, List, Dict, Any
from locust import task, between

from .base import BaseLoadTestUser
from ..config import get_config


# Sample messages that simulate realistic student interactions
STUDENT_MESSAGES = [
    # Opening messages
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
    2. Get available simulation instance
    3. Load simulation context
    4. Send multiple chat messages with realistic timing
    5. Optionally end simulation
    """
    
    # Realistic timing: students read responses and think before replying
    wait_time = between(3, 8)
    
    # Track simulation state
    simulation_instance_id: Optional[int] = None
    persona_id: Optional[int] = None
    messages_sent: int = 0
    max_messages_per_session: int = 10
    
    def on_start(self):
        """Initialize user and load simulation."""
        super().on_start()
        self._load_simulation_instance()
    
    def _load_simulation_instance(self):
        """Get or create a simulation instance for this user."""
        config = get_config()
        
        # Use configured simulation ID
        self.simulation_instance_id = config.simulation_instance_id
        
        # Fetch simulation details to get persona
        sim_data = self._api_get(
            f"/simulation/instances/{self.simulation_instance_id}",
            name="[Sim] Get Instance"
        )
        
        if sim_data:
            # Extract persona ID from simulation data
            personas = sim_data.get("personas", [])
            if personas:
                self.persona_id = personas[0].get("id")
            
            if config.debug:
                print(f"[DEBUG] User {self._user_number} loaded simulation {self.simulation_instance_id}")
        else:
            # Try to get any available instance for this user
            instances = self._api_get(
                "/simulation/instances/my",
                name="[Sim] List My Instances"
            )
            if instances and len(instances) > 0:
                self.simulation_instance_id = instances[0].get("id")
                self.persona_id = instances[0].get("personas", [{}])[0].get("id")
    
    @task(10)  # Weight: most common action
    def send_chat_message(self):
        """Send a chat message to the simulation persona."""
        if not self.simulation_instance_id:
            self._load_simulation_instance()
            return
        
        if self.messages_sent >= self.max_messages_per_session:
            # Reset for next round
            self.messages_sent = 0
            self.think(5, 10)  # Longer pause between "sessions"
            return
        
        # Select a contextually appropriate message
        message = self._select_message()
        
        # Build the chat request
        chat_payload = {
            "message": message,
            "simulation_instance_id": self.simulation_instance_id,
        }
        
        if self.persona_id:
            chat_payload["persona_id"] = self.persona_id
        
        # Send message and measure response time
        start_time = time.time()
        
        with self.client.post(
            "/simulation/chat",
            json=chat_payload,
            headers=self._get_auth_headers(),
            name="[Chat] Send Message",
            catch_response=True,
            timeout=60  # Chat can take time due to AI processing
        ) as response:
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                response.success()
                self.messages_sent += 1
                
                if get_config().debug:
                    print(f"[DEBUG] User {self._user_number} sent message #{self.messages_sent} "
                          f"(response: {response_time:.2f}s)")
            
            elif response.status_code == 429:
                # Rate limited - back off
                response.failure("Rate limited")
                self.think(10, 20)
            
            elif response.status_code in (502, 503, 504):
                # Server overloaded
                response.failure(f"Server error: {response.status_code}")
                self.think(5, 10)
            
            else:
                response.failure(f"Chat failed: {response.status_code} - {response.text[:100]}")
    
    @task(2)  # Less frequent
    def get_chat_history(self):
        """Fetch chat history (simulates user scrolling up)."""
        if not self.simulation_instance_id:
            return
        
        self._api_get(
            f"/simulation/instances/{self.simulation_instance_id}/messages",
            name="[Chat] Get History"
        )
    
    @task(1)  # Rare
    def check_simulation_status(self):
        """Check simulation status/progress."""
        if not self.simulation_instance_id:
            return
        
        self._api_get(
            f"/simulation/instances/{self.simulation_instance_id}/status",
            name="[Sim] Check Status"
        )
    
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

