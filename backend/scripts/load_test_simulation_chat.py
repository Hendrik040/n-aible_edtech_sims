#!/usr/bin/env python3
"""
Load test for actual simulation chat with LangChain agents
Simulates 30-40 students running simulations concurrently

This tests:
- LangChain agentic chain running 30-40 times simultaneously
- Database connection pool under real simulation load
- Memory and session management

Usage:
    python scripts/load_test_simulation_chat.py --users 30 --messages 5
    python scripts/load_test_simulation_chat.py --users 40 --messages 3
"""

import asyncio
import aiohttp
import argparse
import time
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import sys
from pathlib import Path
import re
import os
from urllib.parse import urlparse

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent))

# Configuration
BASE_URL = "http://localhost:8000"
DEFAULT_USERS = 30
DEFAULT_MESSAGES = 5
MAX_USERS = 1000  # Maximum users to prevent DoS
MAX_MESSAGES = 100  # Maximum messages per user

# Test messages to send (simulating student interactions)
# Note: These will be prefixed with @persona mentions
TEST_MESSAGES = [
    "Hello, I'd like to start the simulation",
    "Can you help me understand the situation?",
    "What should I do first?",
    "I need more information about this",
    "Let me think about this problem",
    "What are my options here?",
    "Can you provide some guidance?",
    "I'm ready to proceed",
]

async def get_scenario_personas(session: aiohttp.ClientSession, cookie: str, scenario_id: int) -> List[str]:
    """Get list of persona IDs for a scenario (for @ mentions)
    Returns persona IDs in the format used for @ mentions (lowercase, underscores)
    """
    try:
        headers = {"Cookie": cookie} if cookie else {}
        # Try the full scenario endpoint first
        async with session.get(
            f"{BASE_URL}/api/scenarios/{scenario_id}/full",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=60)  # Increased timeout for LangChain agent calls
        ) as response:
            if response.status == 200:
                data = await response.json()
                personas = data.get("personas", [])
                persona_ids = []
                print(f"[DEBUG] Found {len(personas)} personas in API response")
                for p in personas:
                    # Persona ID can be in different formats - check multiple locations
                    # First try the 'id' field (this is the actual persona ID used in @ mentions)
                    persona_id = p.get("id", "")
                    if persona_id:
                        persona_ids.append(persona_id)
                        print(f"[DEBUG] Added persona ID from 'id' field: {persona_id}")
                    else:
                        # Fallback: derive from name if id not available
                        name = p.get("identity", {}).get("name", "") or p.get("name", "")
                        if name:
                            persona_id = name.lower().replace(" ", "_").replace("'", "")
                            persona_ids.append(persona_id)
                            print(f"[DEBUG] Added persona ID from name: {persona_id} (from name: {name})")
                print(f"[DEBUG] Total persona IDs extracted: {len(persona_ids)}")
                return persona_ids
            else:
                print(f"[DEBUG] Failed to get scenario: status {response.status}")
    except Exception as e:
        print(f"[DEBUG] Error getting personas: {e}")
    return []

def validate_url(url: str, allow_localhost: bool = False) -> tuple[bool, Optional[str]]:
    """Validate URL to prevent SSRF attacks
    Returns: (is_valid, error_message)
    """
    try:
        parsed = urlparse(url)
        
        # Only allow http and https
        if parsed.scheme not in ['http', 'https']:
            return False, f"Invalid scheme: {parsed.scheme}. Only http/https allowed."
        
        hostname = parsed.hostname or ''
        
        # Block localhost and internal IPs (SSRF protection) unless explicitly allowed
        if not allow_localhost:
            if hostname in ['localhost', '127.0.0.1', '0.0.0.0']:
                return False, "Localhost URLs are not allowed for security reasons. Use --allow-localhost for development."
            
            # Block private IP ranges
            if hostname.startswith('192.168.') or hostname.startswith('10.') or hostname.startswith('172.'):
                return False, "Private IP ranges are not allowed for security reasons."
            
            # Block metadata endpoints (cloud provider metadata services)
            if 'metadata' in hostname.lower() or '169.254' in hostname:
                return False, "Metadata endpoints are not allowed for security reasons."
        
        return True, None
    except Exception as e:
        return False, f"Invalid URL format: {e}"

def format_message_with_persona(message: str, persona_id: Optional[str] = None) -> str:
    """Format message with @ mention if persona ID is provided"""
    if persona_id:
        return f"@{persona_id} {message}"
    return message

class SimulationLoadTestResults:
    """Track simulation load test results"""
    def __init__(self):
        self.total_simulations = 0
        self.successful_simulations = 0
        self.failed_simulations = 0
        self.total_messages = 0
        self.successful_messages = 0
        self.failed_messages = 0
        self.message_response_times = []
        self.start_time = None
        self.end_time = None
        self.errors = []
        
    def get_stats(self) -> Dict[str, Any]:
        duration = (self.end_time - self.start_time).total_seconds() if self.end_time and self.start_time else 0.0
        messages_per_second = self.total_messages / duration if duration > 0 else 0.0
        
        sorted_times = sorted(self.message_response_times) if self.message_response_times else []
        
        return {
            "total_simulations": self.total_simulations,
            "successful_simulations": self.successful_simulations,
            "failed_simulations": self.failed_simulations,
            "simulation_success_rate": (self.successful_simulations / self.total_simulations * 100) if self.total_simulations > 0 else 0.0,
            "total_messages": self.total_messages,
            "successful_messages": self.successful_messages,
            "failed_messages": self.failed_messages,
            "message_success_rate": (self.successful_messages / self.total_messages * 100) if self.total_messages > 0 else 0.0,
            "avg_message_response_time": sum(self.message_response_times) / len(self.message_response_times) if self.message_response_times else 0.0,
            "min_message_response_time": min(self.message_response_times) if self.message_response_times else 0.0,
            "max_message_response_time": max(self.message_response_times) if self.message_response_times else 0.0,
            "p95_message_response_time": sorted_times[int(len(sorted_times) * 0.95)] if sorted_times and len(sorted_times) > 0 else 0.0,
            "p99_message_response_time": sorted_times[int(len(sorted_times) * 0.99)] if sorted_times and len(sorted_times) > 0 else 0.0,
            "duration": duration,
            "messages_per_second": messages_per_second,
        }

async def login_user(session: aiohttp.ClientSession, email: str, password: str) -> tuple[Optional[str], Optional[str]]:
    """Login a user and return cookie string"""
    try:
        async with session.post(
            f"{BASE_URL}/users/login",
            json={"email": email, "password": password},
            allow_redirects=False,
            timeout=aiohttp.ClientTimeout(total=30)  # Increased timeout for high concurrency
        ) as response:
            if response.status == 200:
                await response.read()
                cookie_header = response.headers.get('Set-Cookie', '')
                if 'access_token=' in cookie_header:
                    cookie_parts = cookie_header.split(';')
                    access_token_part = [p for p in cookie_parts if 'access_token=' in p]
                    if access_token_part:
                        cookie_value = access_token_part[0].split('access_token=')[1].split(';')[0]
                        return (f"access_token={cookie_value}", None)
                for cookie in session.cookie_jar:
                    if cookie.key == 'access_token':
                        return (f"access_token={cookie.value}", None)
                return (None, "No cookie found")
            else:
                try:
                    error_data = await response.json()
                    error_msg = error_data.get("detail", f"Status {response.status}")
                except:
                    error_msg = f"Status {response.status}"
                return (None, error_msg)
    except Exception as e:
        return (None, str(e))

async def get_user_simulation_instance(session: aiohttp.ClientSession, cookie: str) -> Optional[Dict[str, Any]]:
    """Get the user's simulation instance"""
    try:
        headers = {"Cookie": cookie} if cookie else {}
        async with session.get(
            f"{BASE_URL}/student-simulation-instances/",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=60)  # Increased timeout for LangChain agent calls
        ) as response:
            if response.status == 200:
                data = await response.json()
                if data and len(data) > 0:
                    return data[0]  # Return first simulation instance
                return None
            return None
    except Exception as e:
        return None

async def start_simulation(session: aiohttp.ClientSession, cookie: str, scenario_id: int) -> Optional[int]:
    """Start a simulation and return user_progress_id"""
    try:
        headers = {"Cookie": cookie} if cookie else {}
        async with session.post(
            f"{BASE_URL}/api/simulation/start",
            json={"scenario_id": scenario_id},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("user_progress_id")
            return None
    except Exception as e:
        return None

async def send_simulation_message(
    session: aiohttp.ClientSession,
    cookie: str,
    user_progress_id: int,
    scene_id: Optional[int],
    message: str
) -> Dict[str, Any]:
    """Send a message to the simulation (triggers LangChain agent)"""
    start_time = time.time()
    try:
        headers = {"Cookie": cookie} if cookie else {}
        payload = {
            "user_progress_id": user_progress_id,
            "message": message
        }
        if scene_id:
            payload["scene_id"] = scene_id
        
        async with session.post(
            f"{BASE_URL}/api/simulation/linear-chat",
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=120)  # Longer timeout for LangChain processing (2 minutes)
        ) as response:
            response_time = time.time() - start_time
            if response.status == 200:
                data = await response.json()
                return {
                    "success": True,
                    "response_time": response_time,
                    "response": data,
                    "error": None
                }
            else:
                try:
                    error_data = await response.json()
                    error_msg = error_data.get("detail", str(error_data))
                    # Check for specific error types
                    error_str = str(error_data)
                    if "rate limit" in error_str.lower() or "429" in error_str:
                        error_type = "RateLimit"
                    elif "timeout" in error_str.lower():
                        error_type = "Timeout"
                    elif "connection" in error_str.lower():
                        error_type = "Connection"
                    elif "database" in error_str.lower() or "pool" in error_str.lower():
                        error_type = "Database"
                    else:
                        error_type = "Other"
                    error_msg = f"{error_type}: {error_msg}"
                except:
                    error_text = await response.text()
                    error_msg = error_text[:200]
                return {
                    "success": False,
                    "response_time": response_time,
                    "response": None,
                    "error": f"Status {response.status}: {error_msg}"
                }
    except asyncio.TimeoutError:
        return {
            "success": False,
            "response_time": time.time() - start_time,
            "response": None,
            "error": "Timeout"
        }
    except Exception as e:
        return {
            "success": False,
            "response_time": time.time() - start_time,
            "response": None,
            "error": str(e)
        }

async def run_student_simulation(
    session: aiohttp.ClientSession,
    email: str,
    password: str,
    scenario_id: int,
    num_messages: int,
    results: SimulationLoadTestResults
):
    """Run a complete simulation for one student"""
    # Step 1: Login
    cookie, error = await login_user(session, email, password)
    if not cookie:
        results.failed_simulations += 1
        results.errors.append(f"Login failed for {email}: {error}")
        return
    
    # Step 2: Get personas for the scenario (needed for @ mentions)
    personas = await get_scenario_personas(session, cookie, scenario_id)
    if not personas:
        # Fallback: Use known persona IDs for common scenarios (for load testing)
        # These are the actual persona IDs used in @ mentions
        if scenario_id == 1:
            personas = ['rahul_ashok', 'nick_elliott', 'robert_chan', 'stephen_spurlock', 
                        'pam_lawry', 'elisabeth_fournier', 'jamal', 'ahmed_nazr', 'praveen_devilal']
            print(f"[DEBUG] Using hardcoded personas for scenario 1: {len(personas)} personas")
        # Add more scenarios as needed
    
    # Step 3: Always start a fresh simulation (this ensures proper initialization)
    user_progress_id = await start_simulation(session, cookie, scenario_id)
    if not user_progress_id:
        results.failed_simulations += 1
        results.errors.append(f"Failed to start simulation for {email}")
        return
    
    # Get the scene_id from the start response or first message
    scene_id = None  # Will be set by first response
    
    results.total_simulations += 1
    results.successful_simulations += 1
    
    # Step 4: Send "begin" message first to start the simulation
    results.total_messages += 1
    begin_result = await send_simulation_message(session, cookie, user_progress_id, scene_id, "begin")
    
    if begin_result["success"]:
        results.successful_messages += 1
        results.message_response_times.append(begin_result["response_time"])
        # Update scene_id from response if available
        if begin_result.get("response") and begin_result["response"].get("scene_id"):
            scene_id = begin_result["response"]["scene_id"]
        # Try to extract personas from begin response if we don't have them
        # The begin response contains the full scenario with personas
        if not personas and begin_result.get("response"):
            response_data = begin_result["response"]
            print(f"[DEBUG] Begin response keys: {list(response_data.keys())}")
            
            # Check multiple possible locations for persona data
            scenario_data = None
            if "scenario" in response_data:
                scenario_data = response_data["scenario"]
                print(f"[DEBUG] Found scenario in response, keys: {list(scenario_data.keys()) if isinstance(scenario_data, dict) else 'not a dict'}")
            elif "orchestrator_data" in response_data:
                scenario_data = response_data["orchestrator_data"]
                print(f"[DEBUG] Found orchestrator_data in response")
            
            if scenario_data and isinstance(scenario_data, dict):
                if "personas" in scenario_data:
                    personas_list = scenario_data["personas"]
                    print(f"[DEBUG] Found {len(personas_list)} personas in scenario_data")
                    for p in personas_list:
                        # Try to get persona ID directly first (this is the format used in @ mentions)
                        persona_id = p.get("id", "")
                        if persona_id and persona_id not in personas:
                            personas.append(persona_id)
                            print(f"[DEBUG] Extracted persona ID from begin response: {persona_id}")
                        else:
                            # Fallback: derive from name
                            name = p.get("identity", {}).get("name", "") if isinstance(p.get("identity"), dict) else p.get("name", "")
                            if name:
                                persona_id = name.lower().replace(" ", "_").replace("'", "")
                                if persona_id not in personas:
                                    personas.append(persona_id)
                                    print(f"[DEBUG] Extracted persona ID from name in begin response: {persona_id}")
            
            if personas:
                print(f"[DEBUG] Successfully extracted {len(personas)} personas from begin response: {personas}")
            else:
                print(f"[DEBUG] No personas extracted from begin response")
    else:
        results.failed_messages += 1
        error_msg = begin_result.get('error', 'Unknown error')
        results.errors.append(f"Begin message failed for {email}: {error_msg}")
        print(f"  ❌ {email} (begin): {error_msg}")
        return  # Can't continue if begin fails
    
    # Step 5: Send additional messages to simulation with @ mentions (triggers LangChain agents)
    for i in range(num_messages - 1):  # -1 because we already sent "begin"
        base_message = TEST_MESSAGES[i % len(TEST_MESSAGES)]
        
        # Format message with @ mention to a persona
        if personas:
            # Rotate through personas or use first one
            persona_id = personas[i % len(personas)]
            message = format_message_with_persona(base_message, persona_id)
        else:
            # If we still don't have personas, try to get them from the begin response
            # or use a generic message that will trigger orchestrator response
            # Don't use @all as it doesn't match any persona and won't trigger LangChain
            print(f"  ⚠️  {email}: No personas found, skipping @ mention for message {i+1}")
            message = base_message  # Send without @ mention - will use orchestrator
        
        results.total_messages += 1
        
        result = await send_simulation_message(session, cookie, user_progress_id, scene_id, message)
        
        if result["success"]:
            results.successful_messages += 1
            results.message_response_times.append(result["response_time"])
            # Update scene_id from response if available
            if result.get("response") and result["response"].get("scene_id"):
                scene_id = result["response"]["scene_id"]
        else:
            results.failed_messages += 1
            error_msg = result.get('error', 'Unknown error')
            results.errors.append(f"Message failed for {email}: {error_msg}")
            print(f"  ❌ {email}: {error_msg}")  # Print error immediately for debugging
            # Continue with next message even if one fails

async def run_load_test(num_users: int, num_messages: int, scenario_id: int):
    """Run load test with multiple students running simulations"""
    results = SimulationLoadTestResults()
    results.start_time = datetime.now()
    
    print("🧪 Simulation Load Test - LangChain Agentic Chain")
    print("=" * 60)
    print(f"Testing: {BASE_URL}")
    print(f"Users: {num_users}")
    print(f"Messages per user: {num_messages}")
    print(f"Scenario ID: {scenario_id}")
    print(f"Total LangChain agent calls: {num_users * num_messages}")
    print()
    
    # Get test users from database
    from database.connection import get_db_session
    from database.models import User
    
    with get_db_session() as db:
        test_users = db.query(User).filter(
            User.email.like('teststudent%@test.com')
        ).limit(num_users).all()
        
        if len(test_users) < num_users:
            print(f"⚠️  Warning: Only {len(test_users)} test users available, requested {num_users}")
        
        # Get password from environment or use default (for test users only)
        test_password = os.getenv("TEST_USER_PASSWORD", "testpass123")
        user_creds = [
            {"email": user.email, "password": test_password}
            for user in test_users
        ]
    
    print(f"👥 Using {len(user_creds)} test users")
    print(f"🚀 Starting concurrent simulations...")
    print()
    
    # Run all simulations concurrently
    async with aiohttp.ClientSession() as session:
        tasks = []
        for creds in user_creds:
            task = run_student_simulation(
                session,
                creds["email"],
                creds["password"],
                scenario_id,
                num_messages,
                results
            )
            tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    results.end_time = datetime.now()
    
    # Print results
    stats = results.get_stats()
    print("=" * 60)
    print("📊 SIMULATION LOAD TEST RESULTS")
    print("=" * 60)
    print(f"Simulations:")
    print(f"  Total: {stats['total_simulations']}")
    print(f"  Successful: {stats['successful_simulations']} ({stats['simulation_success_rate']:.2f}%)")
    print(f"  Failed: {stats['failed_simulations']}")
    print()
    print(f"Messages (LangChain Agent Calls):")
    print(f"  Total: {stats['total_messages']}")
    print(f"  Successful: {stats['successful_messages']} ({stats['message_success_rate']:.2f}%)")
    print(f"  Failed: {stats['failed_messages']}")
    print()
    print(f"Response Times:")
    print(f"  Average: {stats['avg_message_response_time']:.3f}s")
    print(f"  Min: {stats['min_message_response_time']:.3f}s")
    print(f"  Max: {stats['max_message_response_time']:.3f}s")
    print(f"  P95: {stats['p95_message_response_time']:.3f}s")
    print(f"  P99: {stats['p99_message_response_time']:.3f}s")
    print()
    print(f"Throughput:")
    print(f"  Duration: {stats['duration']:.2f}s")
    print(f"  Messages/Second: {stats['messages_per_second']:.2f}")
    print()
    
    if results.errors:
        print(f"Errors ({len(results.errors)}):")
        error_counts = {}
        for error in results.errors[:10]:
            error_type = str(error).split(':')[0] if ':' in str(error) else str(error)
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
        for error_type, count in error_counts.items():
            print(f"  {error_type}: {count}x")
        if len(results.errors) > 10:
            print(f"  ... and {len(results.errors) - 10} more errors")
        print()
    
    print("=" * 60)
    
    # Check for issues
    if stats['simulation_success_rate'] < 95:
        print("⚠️  WARNING: Simulation success rate below 95%")
    if stats['message_success_rate'] < 95:
        print("⚠️  WARNING: Message success rate below 95%")
    if stats['avg_message_response_time'] > 10.0:
        print("⚠️  WARNING: Average response time above 10 seconds")
    if stats['p95_message_response_time'] > 20.0:
        print("⚠️  WARNING: P95 response time above 20 seconds")
    
    return stats

def main():
    global BASE_URL
    
    parser = argparse.ArgumentParser(description="Load test simulation chat with LangChain agents")
    parser.add_argument("--users", type=int, default=DEFAULT_USERS, help="Number of concurrent students")
    parser.add_argument("--messages", type=int, default=DEFAULT_MESSAGES, help="Messages per student")
    parser.add_argument("--scenario-id", type=int, default=1, help="Scenario ID to use")
    parser.add_argument("--url", type=str, default=BASE_URL, help="Base URL to test")
    parser.add_argument("--allow-localhost", action="store_true", help="Allow localhost URLs (development only)")
    
    args = parser.parse_args()
    
    # Input validation
    if args.users < 1 or args.users > MAX_USERS:
        print(f"❌ Error: Number of users must be between 1 and {MAX_USERS}")
        sys.exit(1)
    
    if args.messages < 1 or args.messages > MAX_MESSAGES:
        print(f"❌ Error: Number of messages must be between 1 and {MAX_MESSAGES}")
        sys.exit(1)
    
    if args.scenario_id < 1:
        print(f"❌ Error: Scenario ID must be a positive integer")
        sys.exit(1)
    
    # Auto-allow localhost if default URL is used
    is_localhost = args.url == "http://localhost:8000" or args.url.startswith("http://localhost")
    allow_localhost = args.allow_localhost or is_localhost
    
    # URL validation (SSRF protection)
    is_valid, error = validate_url(args.url, allow_localhost=allow_localhost)
    if not is_valid:
        print(f"❌ Security Error: {error}")
        if 'localhost' in error:
            print("   Use --allow-localhost flag for development only")
        sys.exit(1)
    
    BASE_URL = args.url
    
    # Production warning
    if not is_localhost and not args.allow_localhost:
        print("⚠️  WARNING: You are about to run load tests against a non-localhost URL!")
        print(f"   Target: {BASE_URL}")
        response = input("   Are you sure you want to continue? (yes/no): ")
        if response.lower() != 'yes':
            print("❌ Cancelled.")
            sys.exit(0)
    
    asyncio.run(run_load_test(args.users, args.messages, args.scenario_id))

if __name__ == "__main__":
    main()

