import pytest
import asyncio
import uuid
import time
from httpx import AsyncClient

# Number of concurrent users to simulate
CONCURRENT_USERS = 1000 

@pytest.mark.asyncio
async def test_register_and_login_flow(async_client: AsyncClient):
    """
    Test the basic registration and login flow.
    """
    unique_id = str(uuid.uuid4())[:8]
    user_data = {
        "email": f"flow_test_{unique_id}@example.com",
        "password": "Password123!",
        "full_name": "Flow Test User",
        "username": f"flow_test_{unique_id}",
        "role": "student"
    }
    
    # Register
    reg_response = await async_client.post("/api/auth/users/register", json=user_data)
    assert reg_response.status_code == 200
    data = reg_response.json()
    assert data["email"] == user_data["email"]
    
    # Login
    login_data = {
        "email": user_data["email"],
        "password": user_data["password"]
    }
    login_response = await async_client.post("/api/auth/users/login", json=login_data)
    assert login_response.status_code == 200
    
    # Verify Cookie
    assert "access_token" in login_response.cookies

@pytest.mark.asyncio
async def test_concurrent_registrations(async_client: AsyncClient):
    """
    Simulate multiple users registering simultaneously.
    """
    start_time = time.time()
    
    async def register_one_user(index: int):
        unique_id = str(uuid.uuid4())[:8]
        user_data = {
            "email": f"user_{unique_id}_{index}@example.com",
            "password": "Password123!",
            "full_name": f"User {index}",
            "username": f"user_{unique_id}_{index}",
            "role": "student"
        }
        
        response = await async_client.post("/api/auth/users/register", json=user_data)
        return response.status_code

    # Create tasks
    tasks = [register_one_user(i) for i in range(CONCURRENT_USERS)]
    
    # Run concurrent tasks
    results = await asyncio.gather(*tasks)
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Assertions
    success_count = results.count(200)
    
    print(f"\nConcurrency Test Results:")
    print(f"Total Requests: {CONCURRENT_USERS}")
    print(f"Successful: {success_count}")
    print(f"Duration: {duration:.2f}s")
    print(f"Requests/sec: {CONCURRENT_USERS / duration:.2f}")

    assert success_count == CONCURRENT_USERS, f"Expected all {CONCURRENT_USERS} registrations to succeed, but got {success_count}"

@pytest.mark.asyncio
async def test_concurrent_logins(async_client: AsyncClient):
    """
    Simulate multiple users logging in simultaneously.
    """
    # Create a user first
    unique_id = str(uuid.uuid4())[:8]
    user_data = {
        "email": f"login_test_{unique_id}@example.com",
        "password": "Password123!",
        "full_name": "Login Test User",
        "username": f"login_test_{unique_id}",
        "role": "student"
    }
    reg_response = await async_client.post("/api/auth/users/register", json=user_data)
    assert reg_response.status_code == 200

    start_time = time.time()

    async def login_user():
        login_data = {
            "email": user_data["email"],
            "password": user_data["password"]
        }
        response = await async_client.post("/api/auth/users/login", json=login_data)
        return response.status_code

    # Hammer the login endpoint
    tasks = [login_user() for _ in range(CONCURRENT_USERS)]
    results = await asyncio.gather(*tasks)
    
    end_time = time.time()
    duration = end_time - start_time
    
    success_count = results.count(200)
    
    print(f"\nLogin Concurrency Results:")
    print(f"Total Logins: {CONCURRENT_USERS}")
    print(f"Successful: {success_count}")
    print(f"Duration: {duration:.2f}s")
    print(f"Requests/sec: {CONCURRENT_USERS / duration:.2f}")

    assert success_count == CONCURRENT_USERS
