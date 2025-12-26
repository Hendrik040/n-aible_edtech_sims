"""
Load Testing Framework for n-aible Backend

This module provides load testing capabilities using Locust to validate
the Railway deployment can handle 100+ concurrent users.

Usage:
    python -m tests.load_testing.run_tests smoke
    python -m tests.load_testing.run_tests full --url https://staging.railway.app
"""


