"""
Chat Load Test Scenario

Main Locust file for testing chat simulation under load.
Run with: locust -f scenarios/chat_load_test.py

This scenario simulates 100 concurrent students using the chat feature.
"""

import logging
from locust import events, tag

from ..user_behaviors.chat_user import ChatSimulationUser
from ..config import get_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# TEST USER CLASS
# ============================================================

@tag("chat", "simulation")
class ChatLoadTestUser(ChatSimulationUser):
    """
    Load test user for chat simulation.
    
    Inherits all behavior from ChatSimulationUser.
    This class is what Locust will instantiate.
    """
    
    # Override host from config
    host = None  # Will be set from config or CLI
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set host from config if not provided via CLI
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
    logger.info("LOAD TEST STARTING")
    logger.info("=" * 60)
    logger.info(f"  Target: {config.target_url}")
    logger.info(f"  Max Users: {config.max_users}")
    logger.info(f"  Spawn Rate: {config.spawn_rate}/s")
    logger.info(f"  Run Time: {config.run_time}")
    logger.info(f"  Simulation ID: {config.simulation_instance_id}")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    logger.info("=" * 60)
    logger.info("LOAD TEST COMPLETE")
    logger.info("=" * 60)
    
    # Print summary statistics
    stats = environment.stats
    logger.info(f"  Total Requests: {stats.total.num_requests}")
    logger.info(f"  Total Failures: {stats.total.num_failures}")
    
    if stats.total.num_requests > 0:
        failure_rate = (stats.total.num_failures / stats.total.num_requests) * 100
        logger.info(f"  Failure Rate: {failure_rate:.2f}%")
        logger.info(f"  Avg Response Time: {stats.total.avg_response_time:.0f}ms")
        logger.info(f"  P95 Response Time: {stats.total.get_response_time_percentile(0.95):.0f}ms")
        logger.info(f"  P99 Response Time: {stats.total.get_response_time_percentile(0.99):.0f}ms")
    
    logger.info("=" * 60)


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, context, exception, **kwargs):
    """Called on every request (for detailed logging in debug mode)."""
    config = get_config()
    if config.debug and exception:
        logger.warning(f"[FAILED] {request_type} {name}: {exception}")


# ============================================================
# STANDALONE EXECUTION
# ============================================================

if __name__ == "__main__":
    # Allow running directly with: python -m scenarios.chat_load_test
    import os
    import sys
    
    # Add parent directory to path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from locust.main import main
    
    # Set default arguments if not provided
    sys.argv.extend([
        "-f", __file__,
        "--headless",
        "-u", "10",  # 10 users for quick test
        "-r", "2",   # spawn rate
        "-t", "1m",  # 1 minute
    ])
    
    main()

