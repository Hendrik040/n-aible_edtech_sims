"""
Load Testing Configuration

Manages environment-specific settings for load tests.
Loads configuration from loadtest.env file in this directory.
"""
import os
import sys
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

# Try to import dotenv, but don't fail if not installed
try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False
    print("Warning: python-dotenv not installed. Install with: pip install python-dotenv")

# Get the directory where this config file is located
CONFIG_DIR = Path(__file__).parent

# Load environment variables from loadtest.env
ENV_FILE = CONFIG_DIR / "loadtest.env"
if HAS_DOTENV and ENV_FILE.exists():
    load_dotenv(ENV_FILE)
    print(f"✓ Loaded configuration from {ENV_FILE}")
elif HAS_DOTENV:
    # Try .env as fallback
    FALLBACK_ENV = CONFIG_DIR / ".env"
    if FALLBACK_ENV.exists():
        load_dotenv(FALLBACK_ENV)
        print(f"✓ Loaded configuration from {FALLBACK_ENV}")
    else:
        print(f"⚠ No loadtest.env found at {ENV_FILE}")
        print(f"  Copy loadtest.env.example to loadtest.env and configure it.")


def _env_str(key: str, default: str = "") -> str:
    """Get string from environment."""
    return os.getenv(key, default)


def _env_int(key: str, default: int = 0) -> int:
    """Get integer from environment."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(key: str, default: float = 0.0) -> float:
    """Get float from environment."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    """Get boolean from environment."""
    value = os.getenv(key, "").lower()
    if value in ("true", "1", "yes", "on"):
        return True
    elif value in ("false", "0", "no", "off"):
        return False
    return default


@dataclass
class LoadTestConfig:
    """Configuration for load testing."""
    
    # Target environment
    base_url: str = ""
    environment: str = "staging"
    
    # Authentication
    test_user_prefix: str = "loadtest_user_"
    test_user_domain: str = "@test.com"
    test_password: str = "testpassword123"
    test_user_count: int = 100
    
    # Test data
    simulation_id: int = 1
    cohort_id: int = 1
    
    # Timing (seconds between requests)
    min_wait: float = 5.0
    max_wait: float = 15.0
    
    # Load parameters
    max_users: int = 100
    spawn_rate: float = 2.0
    run_time: str = "15m"
    
    # Timeouts
    login_timeout: int = 10
    chat_timeout: int = 60
    grading_timeout: int = 120
    poll_timeout: int = 10
    
    # Reporting
    generate_html: bool = True
    generate_csv: bool = True
    reports_dir: str = "reports"
    
    # Advanced
    verbose: bool = False
    max_error_rate: float = 10.0
    log_failures: bool = True
    
    @classmethod
    def from_env(cls) -> "LoadTestConfig":
        """Create config from environment variables."""
        return cls(
            base_url=_env_str("LOAD_TEST_URL", "http://localhost:8000"),
            environment=_env_str("LOAD_TEST_ENVIRONMENT", "staging"),
            test_user_prefix=_env_str("TEST_USER_PREFIX", "loadtest_user_"),
            test_user_domain=_env_str("TEST_USER_DOMAIN", "@test.com"),
            test_password=_env_str("TEST_USER_PASSWORD", "testpassword123"),
            test_user_count=_env_int("TEST_USER_COUNT", 100),
            simulation_id=_env_int("TEST_SIMULATION_ID", 1),
            cohort_id=_env_int("TEST_COHORT_ID", 1),
            min_wait=_env_float("MIN_WAIT_TIME", 5.0),
            max_wait=_env_float("MAX_WAIT_TIME", 15.0),
            max_users=_env_int("DEFAULT_USERS", 100),
            spawn_rate=_env_float("DEFAULT_SPAWN_RATE", 2.0),
            run_time=_env_str("DEFAULT_RUN_TIME", "15m"),
            login_timeout=_env_int("LOGIN_TIMEOUT", 10),
            chat_timeout=_env_int("CHAT_TIMEOUT", 60),
            grading_timeout=_env_int("GRADING_TIMEOUT", 120),
            poll_timeout=_env_int("POLL_TIMEOUT", 10),
            generate_html=_env_bool("GENERATE_HTML_REPORT", True),
            generate_csv=_env_bool("GENERATE_CSV_REPORT", True),
            reports_dir=_env_str("REPORTS_DIR", "reports"),
            verbose=_env_bool("VERBOSE", False),
            max_error_rate=_env_float("MAX_ERROR_RATE", 10.0),
            log_failures=_env_bool("LOG_FAILURES", True),
        )
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        if not self.base_url:
            errors.append("LOAD_TEST_URL is not set")
        
        if self.environment == "production":
            errors.append("Cannot run load tests against production!")
        
        if self.max_users <= 0:
            errors.append("DEFAULT_USERS must be positive")
        
        if self.spawn_rate <= 0:
            errors.append("DEFAULT_SPAWN_RATE must be positive")
        
        if not self.test_password:
            errors.append("TEST_USER_PASSWORD is not set")
        
        return errors
    
    def print_summary(self):
        """Print configuration summary."""
        print("\n" + "=" * 60)
        print("LOAD TEST CONFIGURATION")
        print("=" * 60)
        print(f"  Target URL:      {self.base_url}")
        print(f"  Environment:     {self.environment}")
        print(f"  Max Users:       {self.max_users}")
        print(f"  Spawn Rate:      {self.spawn_rate}/s")
        print(f"  Run Time:        {self.run_time}")
        print(f"  Simulation ID:   {self.simulation_id}")
        print(f"  Test Users:      {self.test_user_prefix}1-{self.test_user_count}{self.test_user_domain}")
        print("=" * 60 + "\n")


# Pre-configured test profiles
PROFILES = {
    "smoke": LoadTestConfig(
        max_users=5,
        spawn_rate=1.0,
        run_time="2m",
        min_wait=3.0,
        max_wait=10.0,
    ),
    "ramp": LoadTestConfig(
        max_users=50,
        spawn_rate=0.5,
        run_time="10m",
        min_wait=5.0,
        max_wait=15.0,
    ),
    "full": LoadTestConfig(
        max_users=100,
        spawn_rate=2.0,
        run_time="15m",
        min_wait=5.0,
        max_wait=15.0,
    ),
    "stress": LoadTestConfig(
        max_users=150,
        spawn_rate=5.0,
        run_time="5m",
        min_wait=2.0,
        max_wait=5.0,
    ),
}


def get_config(profile: str = "full") -> LoadTestConfig:
    """
    Get configuration for a test profile.
    
    Merges profile defaults with environment variables.
    
    Args:
        profile: One of "smoke", "ramp", "full", "stress"
        
    Returns:
        LoadTestConfig instance
    """
    # Start with environment config
    config = LoadTestConfig.from_env()
    
    # Get profile defaults
    profile_config = PROFILES.get(profile)
    if profile_config:
        # Override with profile-specific values
        config.max_users = profile_config.max_users
        config.spawn_rate = profile_config.spawn_rate
        config.run_time = profile_config.run_time
        config.min_wait = profile_config.min_wait
        config.max_wait = profile_config.max_wait
    
    return config


# Module-level config instance (lazy loaded)
_config: Optional[LoadTestConfig] = None


def get_current_config() -> LoadTestConfig:
    """Get the current configuration (cached)."""
    global _config
    if _config is None:
        _config = LoadTestConfig.from_env()
    return _config


def set_config(config: LoadTestConfig):
    """Set the current configuration."""
    global _config
    _config = config


# For convenient imports
__all__ = [
    "LoadTestConfig",
    "PROFILES",
    "get_config",
    "get_current_config",
    "set_config",
    "CONFIG_DIR",
]

