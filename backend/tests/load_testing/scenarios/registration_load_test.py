"""
Registration Load Test Scenario

Tests the platform's ability to handle mass user registration.
Simulates 100 users signing up simultaneously.

Run with: locust -f scenarios/registration_load_test.py
"""

import sys
import os
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from locust import events, tag

from user_behaviors.registration_user import RegistrationUser, RegistrationThenChatUser
from config import get_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# TEST USER CLASSES
# ============================================================

@tag("registration", "auth")
class RegistrationLoadTestUser(RegistrationUser):
    """
    Load test user for registration only.
    
    Tests: Can your system handle 100 users signing up at once?
    """
    
    host = None
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.host:
            config = get_config()
            self.host = config.target_url


@tag("registration", "chat", "full-journey")
class RegistrationAndChatUser(RegistrationThenChatUser):
    """
    Load test user that registers then chats.
    
    Tests: Full new user journey - signup to first conversation.
    """
    
    host = None
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.host:
            config = get_config()
            self.host = config.target_url


# ============================================================
# EVENT HANDLERS
# ============================================================

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    config = get_config()
    logger.info("=" * 60)
    logger.info("REGISTRATION LOAD TEST STARTING")
    logger.info("=" * 60)
    logger.info(f"  Target: {config.target_url}")
    logger.info(f"  Max Users: {config.max_users}")
    logger.info(f"  Spawn Rate: {config.spawn_rate}/s")
    logger.info(f"  Test: Mass user registration")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    logger.info("=" * 60)
    logger.info("REGISTRATION LOAD TEST COMPLETE")
    logger.info("=" * 60)
    
    stats = environment.stats
    
    # Find registration stats
    reg_stats = stats.get("[Auth] Register", None)
    login_stats = stats.get("[Auth] Login (post-register)", None)
    
    logger.info(f"  Total Requests: {stats.total.num_requests}")
    logger.info(f"  Total Failures: {stats.total.num_failures}")
    
    if reg_stats:
        logger.info(f"  Registrations: {reg_stats.num_requests} "
                   f"(failed: {reg_stats.num_failures})")
        if reg_stats.num_requests > 0:
            logger.info(f"  Avg Registration Time: {reg_stats.avg_response_time:.0f}ms")
    
    if stats.total.num_requests > 0:
        failure_rate = (stats.total.num_failures / stats.total.num_requests) * 100
        logger.info(f"  Overall Failure Rate: {failure_rate:.2f}%")
    
    logger.info("=" * 60)


# ============================================================
# STANDALONE EXECUTION
# ============================================================

if __name__ == "__main__":
    from locust.main import main
    import sys
    
    sys.argv.extend([
        "-f", __file__,
        "--headless",
        "-u", "10",
        "-r", "2",
        "-t", "1m",
    ])
    
    main()

