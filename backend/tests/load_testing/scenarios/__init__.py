"""
Load Test Scenarios

Each scenario file can be run independently with Locust.
"""
from .chat_load_test import ChatLoadTestUser

__all__ = ["ChatLoadTestUser"]
