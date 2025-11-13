#!/usr/bin/env python3
"""
Load Testing Script for AI Agent Education Platform
Simulates multiple concurrent users going through the platform

Usage:
    python scripts/load_test.py --users 50 --endpoint simulation-instances
    python scripts/load_test.py --users 30 --endpoint login --duration 60
    python scripts/load_test.py --users 40 --endpoint full-flow --scenario-id 1
"""

import asyncio
import aiohttp
import argparse
import time
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import random
import sys
import os
from pathlib import Path
from urllib.parse import urlparse

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent))

# Configuration
BASE_URL = "http://localhost:8000"  # Change to production URL for production testing
DEFAULT_USERS = 30
DEFAULT_DURATION = 30  # seconds
MAX_USERS = 1000  # Maximum users to prevent DoS

# Test user credentials (you'll need to create these in your database)
# For testing, you can create users via the register endpoint or directly in the database
# Generate test users programmatically if needed
def generate_test_users(count: int) -> List[Dict[str, str]]:
    """Generate test user credentials"""
    users = []
    for i in range(1, count + 1):
        users.append({
            "email": f"teststudent{i}@test.com",
            "password": "testpass123"
        })
    return users

# Default test users (expand as needed)
TEST_USERS = generate_test_users(50)  # Generate 50 test users

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

class LoadTestResults:
    """Track load test results"""
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.response_times = []
        self.errors = []
        self.start_time = None
        self.end_time = None
        
    def add_result(self, success: bool, response_time: float, error: Optional[str] = None):
        self.total_requests += 1
        if success:
            self.successful_requests += 1
            self.response_times.append(response_time)
        else:
            self.failed_requests += 1
            if error:
                self.errors.append(error)
    
    def get_stats(self) -> Dict[str, Any]:
        duration = (self.end_time - self.start_time).total_seconds() if self.end_time and self.start_time else 0.0
        requests_per_second = self.total_requests / duration if duration > 0 else 0.0
        
        if not self.response_times:
            return {
                "total": self.total_requests,
                "success": self.successful_requests,
                "failed": self.failed_requests,
                "success_rate": 0.0,
                "avg_response_time": 0.0,
                "min_response_time": 0.0,
                "max_response_time": 0.0,
                "p95_response_time": 0.0,
                "p99_response_time": 0.0,
                "duration": duration,
                "requests_per_second": requests_per_second,
            }
        
        sorted_times = sorted(self.response_times)
        return {
            "total": self.total_requests,
            "success": self.successful_requests,
            "failed": self.failed_requests,
            "success_rate": (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0.0,
            "avg_response_time": sum(self.response_times) / len(self.response_times),
            "min_response_time": min(self.response_times),
            "max_response_time": max(self.response_times),
            "p95_response_time": sorted_times[int(len(sorted_times) * 0.95)] if sorted_times else 0.0,
            "p99_response_time": sorted_times[int(len(sorted_times) * 0.99)] if sorted_times else 0.0,
            "duration": duration,
            "requests_per_second": requests_per_second,
        }

async def login_user(session: aiohttp.ClientSession, email: str, password: str) -> tuple[Optional[str], Optional[str]]:
    """Login a user and return (cookie string, error_message)
    
    Extracts the cookie from the response to manually set it in subsequent requests
    """
    start_time = time.time()
    try:
        async with session.post(
            f"{BASE_URL}/users/login",
            json={"email": email, "password": password},
            allow_redirects=False,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            if response.status == 200:
                # Read response to ensure it completes
                await response.read()
                # Extract cookie from response headers
                cookie_header = response.headers.get('Set-Cookie', '')
                if 'access_token=' in cookie_header:
                    # Extract the cookie value
                    cookie_parts = cookie_header.split(';')
                    access_token_part = [p for p in cookie_parts if 'access_token=' in p]
                    if access_token_part:
                        cookie_value = access_token_part[0].split('access_token=')[1].split(';')[0]
                        return (f"access_token={cookie_value}", None)
                # Fallback: try to get from cookie jar
                for cookie in session.cookie_jar:
                    if cookie.key == 'access_token':
                        return (f"access_token={cookie.value}", None)
                return (None, "No cookie found in response")
            else:
                # Try to read error message
                try:
                    error_data = await response.json()
                    error_msg = error_data.get("detail", f"Status {response.status}")
                except:
                    error_msg = f"Status {response.status}"
                return (None, error_msg)
    except asyncio.TimeoutError:
        return (None, "Timeout")
    except Exception as e:
        return (None, str(e))

async def test_simulation_instances(session: aiohttp.ClientSession, cookie: str, user_id: int) -> Dict[str, Any]:
    """Test getting student simulation instances"""
    start_time = time.time()
    try:
        headers = {"Cookie": cookie} if cookie else {}
        async with session.get(
            f"{BASE_URL}/student-simulation-instances/",
            headers=headers,
            allow_redirects=False
        ) as response:
            response_time = time.time() - start_time
            data = await response.json() if response.status == 200 else None
            return {
                "success": response.status == 200,
                "status": response.status,
                "response_time": response_time,
                "data_length": len(data) if data else 0,
                "error": None if response.status == 200 else f"Status {response.status}"
            }
    except Exception as e:
        response_time = time.time() - start_time
        return {
            "success": False,
            "status": 0,
            "response_time": response_time,
            "data_length": 0,
            "error": str(e)
        }

async def test_start_simulation(session: aiohttp.ClientSession, cookie: str, instance_id: str, user_id: int) -> Dict[str, Any]:
    """Test starting a simulation"""
    start_time = time.time()
    try:
        headers = {"Cookie": cookie} if cookie else {}
        async with session.post(
            f"{BASE_URL}/student-simulation-instances/{instance_id}/start-simulation",
            headers=headers,
            allow_redirects=False
        ) as response:
            response_time = time.time() - start_time
            data = await response.json() if response.status == 200 else None
            return {
                "success": response.status == 200,
                "status": response.status,
                "response_time": response_time,
                "error": None if response.status == 200 else f"Status {response.status}"
            }
    except Exception as e:
        response_time = time.time() - start_time
        return {
            "success": False,
            "status": 0,
            "response_time": response_time,
            "error": str(e)
        }

async def test_get_current_user(session: aiohttp.ClientSession, cookie: str, user_id: int) -> Dict[str, Any]:
    """Test getting current user (authentication check)"""
    start_time = time.time()
    try:
        headers = {"Cookie": cookie} if cookie else {}
        async with session.get(
            f"{BASE_URL}/users/me",
            headers=headers,
            allow_redirects=False
        ) as response:
            response_time = time.time() - start_time
            data = await response.json() if response.status == 200 else None
            return {
                "success": response.status == 200,
                "status": response.status,
                "response_time": response_time,
                "error": None if response.status == 200 else f"Status {response.status}"
            }
    except Exception as e:
        response_time = time.time() - start_time
        return {
            "success": False,
            "status": 0,
            "response_time": response_time,
            "error": str(e)
        }

async def simulate_user_flow(session: aiohttp.ClientSession, user_creds: Dict[str, str], user_id: int, results: LoadTestResults):
    """Simulate a complete user flow"""
    # Step 1: Login
    cookie, error = await login_user(session, user_creds["email"], user_creds["password"])
    if not cookie:
        results.add_result(False, 0.0, error or "Login failed")
        return
    
    # Step 2: Get current user (verify auth)
    user_result = await test_get_current_user(session, cookie, user_id)
    results.add_result(user_result["success"], user_result["response_time"], user_result["error"])
    
    # Step 3: Get simulation instances (the endpoint we optimized)
    instances_result = await test_simulation_instances(session, cookie, user_id)
    results.add_result(instances_result["success"], instances_result["response_time"], instances_result["error"])
    
    # Step 4: If instances exist, try to start one
    if instances_result.get("data_length", 0) > 0:
        # In a real scenario, we'd parse the instance ID from the response
        # For now, we'll skip this or use a known instance ID
        pass

async def run_load_test(
    num_users: int,
    endpoint: str,
    duration: Optional[int] = None,
    scenario_id: Optional[int] = None
):
    """Run load test with specified parameters"""
    results = LoadTestResults()
    results.start_time = datetime.now()
    
    print(f"🚀 Starting load test:")
    print(f"   Users: {num_users}")
    print(f"   Endpoint: {endpoint}")
    print(f"   Duration: {duration}s" if duration else "   Duration: Until complete")
    print(f"   Base URL: {BASE_URL}")
    print()
    
    async with aiohttp.ClientSession() as session:
        if endpoint == "login":
            # Test login endpoint
            tasks = []
            for i in range(num_users):
                user_creds = TEST_USERS[i % len(TEST_USERS)]
                task = login_user(session, user_creds["email"], user_creds["password"])
                tasks.append(task)
            
            start = time.time()
            login_results = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.time() - start
            
            for i, result in enumerate(login_results):
                if isinstance(result, Exception):
                    results.add_result(False, elapsed / num_users, str(result))
                else:
                    cookie, error = result
                    success = cookie is not None
                    response_time = elapsed / num_users if num_users > 0 else 0
                    results.add_result(success, response_time, error)
        
        elif endpoint == "simulation-instances":
            # Test simulation instances endpoint (the one we optimized)
            # First, login all users and get their cookies
            login_tasks = []
            for i in range(num_users):
                user_creds = TEST_USERS[i % len(TEST_USERS)]
                task = login_user(session, user_creds["email"], user_creds["password"])
                login_tasks.append(task)
            
            login_results = await asyncio.gather(*login_tasks, return_exceptions=True)
            cookies = []
            for result in login_results:
                if isinstance(result, Exception):
                    cookies.append(None)
                else:
                    cookie, error = result
                    cookies.append(cookie if cookie else None)
            
            # Then test the endpoint concurrently with cookies
            tasks = []
            for i, cookie in enumerate(cookies):
                if cookie:
                    task = test_simulation_instances(session, cookie, i)
                    tasks.append(task)
            
            start = time.time()
            instance_results = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.time() - start
            
            for result in instance_results:
                if isinstance(result, Exception):
                    results.add_result(False, 0.0, str(result))
                else:
                    results.add_result(result["success"], result["response_time"], result.get("error"))
        
        elif endpoint == "full-flow":
            # Simulate complete user flow
            tasks = []
            for i in range(num_users):
                user_creds = TEST_USERS[i % len(TEST_USERS)]
                task = simulate_user_flow(session, user_creds, i, results)
                tasks.append(task)
            
            await asyncio.gather(*tasks, return_exceptions=True)
        
        elif endpoint == "concurrent-login":
            # Test concurrent logins (stress test)
            if duration:
                end_time = time.time() + duration
                while time.time() < end_time:
                    tasks = []
                    for i in range(min(num_users, 10)):  # Batch of 10 at a time
                        user_creds = TEST_USERS[i % len(TEST_USERS)]
                        task = login_user(session, user_creds["email"], user_creds["password"])
                        tasks.append(task)
                    
                    login_results = await asyncio.gather(*tasks, return_exceptions=True)
                    for result in login_results:
                        if isinstance(result, Exception):
                            results.add_result(False, 0.1, str(result))
                        else:
                            cookie, error = result
                            success = cookie is not None
                            results.add_result(success, 0.1, error)
                    
                    await asyncio.sleep(0.5)  # Small delay between batches
            else:
                # Single burst
                tasks = []
                for i in range(num_users):
                    user_creds = TEST_USERS[i % len(TEST_USERS)]
                    task = login_user(session, user_creds["email"], user_creds["password"])
                    tasks.append(task)
                
                start = time.time()
                login_results = await asyncio.gather(*tasks, return_exceptions=True)
                elapsed = time.time() - start
                
                for result in login_results:
                    if isinstance(result, Exception):
                        results.add_result(False, elapsed / num_users, str(result))
                    else:
                        cookie, error = result
                        success = cookie is not None
                        results.add_result(success, elapsed / num_users, error)
    
    results.end_time = datetime.now()
    
    # Print results
    stats = results.get_stats()
    print("\n" + "="*60)
    print("📊 LOAD TEST RESULTS")
    print("="*60)
    print(f"Total Requests: {stats['total']}")
    print(f"Successful: {stats['success']} ({stats['success_rate']:.2f}%)")
    print(f"Failed: {stats['failed']}")
    print(f"Duration: {stats['duration']:.2f}s")
    print(f"Requests/Second: {stats['requests_per_second']:.2f}")
    print()
    print("Response Times:")
    print(f"  Average: {stats['avg_response_time']:.3f}s")
    print(f"  Min: {stats['min_response_time']:.3f}s")
    print(f"  Max: {stats['max_response_time']:.3f}s")
    print(f"  P95: {stats['p95_response_time']:.3f}s")
    print(f"  P99: {stats['p99_response_time']:.3f}s")
    print()
    
    if results.errors:
        print(f"Errors ({len(results.errors)}):")
        error_counts = {}
        for error in results.errors[:10]:  # Show first 10
            error_counts[error] = error_counts.get(error, 0) + 1
        for error, count in error_counts.items():
            print(f"  {error}: {count}x")
        if len(results.errors) > 10:
            print(f"  ... and {len(results.errors) - 10} more errors")
    
    print("="*60)
    
    # Check for issues
    if stats['success_rate'] < 95:
        print("⚠️  WARNING: Success rate below 95%")
    if stats['avg_response_time'] > 2.0:
        print("⚠️  WARNING: Average response time above 2 seconds")
    if stats['p95_response_time'] > 5.0:
        print("⚠️  WARNING: P95 response time above 5 seconds")
    
    return stats

def main():
    global BASE_URL
    
    parser = argparse.ArgumentParser(description="Load test the AI Agent Education Platform")
    parser.add_argument("--users", type=int, default=DEFAULT_USERS, help="Number of concurrent users")
    parser.add_argument("--endpoint", type=str, default="simulation-instances",
                        choices=["login", "simulation-instances", "full-flow", "concurrent-login"],
                        help="Endpoint to test")
    parser.add_argument("--duration", type=int, default=None, help="Test duration in seconds (for concurrent-login)")
    parser.add_argument("--url", type=str, default=BASE_URL, help="Base URL to test")
    parser.add_argument("--scenario-id", type=int, default=None, help="Scenario ID for testing")
    parser.add_argument("--allow-localhost", action="store_true", help="Allow localhost URLs (development only)")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt for non-localhost URLs")
    
    args = parser.parse_args()
    
    # Input validation
    if args.users < 1 or args.users > MAX_USERS:
        print(f"❌ Error: Number of users must be between 1 and {MAX_USERS}")
        sys.exit(1)
    
    if args.scenario_id is not None and args.scenario_id < 1:
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
    if not is_localhost and not args.allow_localhost and not args.yes:
        print("⚠️  WARNING: You are about to run load tests against a non-localhost URL!")
        print(f"   Target: {BASE_URL}")
        response = input("   Are you sure you want to continue? (yes/no): ")
        if response.lower() != 'yes':
            print("❌ Cancelled.")
            sys.exit(0)
    
    print("🧪 Load Testing Tool for AI Agent Education Platform")
    print(f"Testing: {BASE_URL}")
    print()
    
    asyncio.run(run_load_test(
        num_users=args.users,
        endpoint=args.endpoint,
        duration=args.duration,
        scenario_id=args.scenario_id
    ))

if __name__ == "__main__":
    main()

