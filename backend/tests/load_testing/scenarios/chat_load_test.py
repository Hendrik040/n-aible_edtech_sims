"""
Chat Load Test Scenario

Main Locust file for testing chat simulation under load.

Usage:
    DEBUG_MODE=true python -m locust -f scenarios/chat_load_test.py \
        --headless -u 100 -r 10 -t 5m ChatLoadTestUser

This scenario simulates 100 concurrent students using the chat feature.

Prerequisites:
1. Configure TEST_SIMULATION_ID in loadtest.env to a published simulation
2. Register test users first using the registration test or have pre-existing users
3. Ensure the simulation is accessible to the test users
"""

import logging
import sys
import os
import time

# Add parent directory to path for imports when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from locust import events, tag

from user_behaviors.chat_user import ChatSimulationUser
from config import get_config, LoadTestConfig, set_config

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
    
    # Set host at class level from config
    host = get_config().target_url
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


# ============================================================
# EVENT HANDLERS
# ============================================================

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    config = get_config()
    set_config(config)  # Ensure config is available globally
    
    # Reset stats
    environment.runner.stats.reset_all()
    
    logger.info("=" * 60)
    logger.info("CHAT SIMULATION LOAD TEST STARTING")
    logger.info("=" * 60)
    logger.info(f"  Target: {config.target_url}")
    logger.info(f"  Max Users: {config.max_users}")
    logger.info(f"  Spawn Rate: {config.spawn_rate}/s")
    logger.info(f"  Run Time: {config.run_time}")
    logger.info(f"  Simulation ID: {config.simulation_id}")
    logger.info(f"  Chat Timeout: {config.chat_timeout}s")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Test Flow per User:")
    logger.info("  1. Login with test credentials")
    logger.info("  2. Start simulation (POST /api/simulation/start)")
    logger.info("  3. Send 'begin' message")
    logger.info("  4. Send ~10 chat messages with AI persona")
    logger.info("  5. Repeat")
    logger.info("")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("CHAT SIMULATION LOAD TEST COMPLETE")
    logger.info("=" * 60)
    
    # Print summary statistics
    stats = environment.stats
    logger.info(f"  Total Requests: {stats.total.num_requests}")
    logger.info(f"  Total Failures: {stats.total.num_failures}")
    
    if stats.total.num_requests > 0:
        failure_rate = (stats.total.num_failures / stats.total.num_requests) * 100
        logger.info(f"  Failure Rate: {failure_rate:.2f}%")
        logger.info(f"  Avg Response Time: {stats.total.avg_response_time:.0f}ms")
        
        # Get percentiles safely
        try:
            p95 = stats.total.get_response_time_percentile(0.95)
            p99 = stats.total.get_response_time_percentile(0.99)
            logger.info(f"  P95 Response Time: {p95:.0f}ms")
            logger.info(f"  P99 Response Time: {p99:.0f}ms")
        except Exception:
            pass
    
    # Print per-endpoint stats
    logger.info("")
    logger.info("Per-Endpoint Statistics:")
    logger.info("-" * 60)
    
    # Chat message stats
    chat_stats = stats.get("[Chat] Send Message", "POST")
    if chat_stats and chat_stats.num_requests > 0:
        logger.info("  [Chat] Send Message:")
        logger.info(f"    Requests: {chat_stats.num_requests}")
        logger.info(f"    Failures: {chat_stats.num_failures}")
        logger.info(f"    Avg Time: {chat_stats.avg_response_time:.0f}ms")
        logger.info(f"    Min Time: {chat_stats.min_response_time:.0f}ms")
        logger.info(f"    Max Time: {chat_stats.max_response_time:.0f}ms")
    
    # Begin message stats
    begin_stats = stats.get("[Chat] Begin", "POST")
    if begin_stats and begin_stats.num_requests > 0:
        logger.info("  [Chat] Begin:")
        logger.info(f"    Requests: {begin_stats.num_requests}")
        logger.info(f"    Avg Time: {begin_stats.avg_response_time:.0f}ms")
    
    # Start simulation stats
    start_stats = stats.get("[Sim] Start Simulation", "POST")
    if start_stats and start_stats.num_requests > 0:
        logger.info("  [Sim] Start Simulation:")
        logger.info(f"    Requests: {start_stats.num_requests}")
        logger.info(f"    Avg Time: {start_stats.avg_response_time:.0f}ms")
    
    logger.info("=" * 60)


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, context, exception, start_time, **kwargs):
    """Called on every request (for detailed logging in debug mode)."""
    config = get_config()
    
    if config.verbose:
        timestamp = time.strftime('%H:%M:%S')
        if exception:
            logger.warning(f"[{timestamp}] [FAILED] {request_type} {name}: {exception}")
        elif response_time > 5000:  # Log slow requests (>5s)
            logger.warning(f"[{timestamp}] [SLOW] {request_type} {name}: {response_time:.0f}ms")


# ============================================================
# STANDALONE EXECUTION
# ============================================================

if __name__ == "__main__":
    # Allow running directly with: python -m scenarios.chat_load_test
    import sys
    
    # Add parent directory to path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from locust.main import main
    
    # Set default arguments if not provided
    if len(sys.argv) == 1:
        sys.argv.extend([
            "-f", __file__,
            "--headless",
            "-u", "10",   # 10 users for quick test
            "-r", "2",    # spawn rate
            "-t", "2m",   # 2 minutes
            "ChatLoadTestUser",
        ])
    
    main()
