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


# =============================================================================
# REGION TO URL MAPPING
# =============================================================================
# Maps region codes to their backend URLs
# User only needs to set TARGET_REGION - URL is auto-resolved
REGION_URLS = {
    "EU": "https://backend-europe.up.railway.app",
    "US-DEV": "https://backend-development-0519.up.railway.app",
    "US-EXP": "https://backend-experimental-246c.up.railway.app",
    "US-PROD": None,  # TBD - will be added when production is ready
    "US-STAG": "https://backend-staging-815c.up.railway.app",
}

VALID_REGIONS = list(REGION_URLS.keys())


def get_url_for_region(region: str) -> str:
    """
    Get the backend URL for a given region.
    
    Args:
        region: One of EU, US-DEV, US-EXP, US-PROD, US-STAG
        
    Returns:
        The backend URL for that region
        
    Raises:
        ValueError: If region is invalid or not yet configured
    """
    if region not in REGION_URLS:
        raise ValueError(
            f"Invalid region: '{region}'. "
            f"Valid options: {VALID_REGIONS}"
        )
    
    url = REGION_URLS[region]
    if url is None:
        raise ValueError(
            f"Region '{region}' is not yet configured. "
            f"Currently available: {[r for r, u in REGION_URLS.items() if u]}"
        )
    
    return url


def get_simulation_id_for_region(region: str) -> int:
    """
    Get the simulation ID for a given region.
    Falls back to TEST_SIMULATION_ID if no region-specific ID is set.
    
    Region-specific env vars:
        TEST_SIMULATION_ID_EU
        TEST_SIMULATION_ID_US_DEV  (note: hyphen becomes underscore)
        TEST_SIMULATION_ID_US_EXP
    """
    # Convert region to env var format: "US-DEV" -> "US_DEV"
    region_key = region.replace("-", "_")
    env_key = f"TEST_SIMULATION_ID_{region_key}"
    
    # Try region-specific first
    region_sim_id = os.getenv(env_key)
    if region_sim_id:
        try:
            return int(region_sim_id)
        except ValueError:
            pass
    
    # Fall back to default
    return _env_int("TEST_SIMULATION_ID", 1)

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
    target_region: str = "US-DEV"  # Region drives the URL
    base_url: str = ""  # Auto-resolved from region (or manual override)
    environment: str = "staging"
    test_runner_location: str = "Unknown"  # Where tests are run from
    
    # Legacy API regions (old codebase with different routes)
    # These regions use /users/login instead of /api/auth/users/login
    LEGACY_API_REGIONS: tuple = ("US-STAG",)
    
    @property
    def is_legacy_api(self) -> bool:
        """Check if target region uses legacy API routes (old codebase).
        
        Legacy routes:
        - /users/login instead of /api/auth/users/login
        - /users/register instead of /api/auth/users/register
        
        US-STAG runs the old codebase (prev/) with different endpoint structure.
        """
        return self.target_region in self.LEGACY_API_REGIONS
    
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
        # Get target region (drives the URL)
        target_region = _env_str("TARGET_REGION", "US-DEV")
        
        # URL can be overridden manually, otherwise auto-resolve from region
        manual_url = _env_str("LOAD_TEST_URL", "")
        if manual_url and manual_url != "http://localhost:8000":
            # Manual override provided
            base_url = manual_url
        else:
            # Auto-resolve from region
            try:
                base_url = get_url_for_region(target_region)
            except ValueError as e:
                print(f"⚠ {e}")
                base_url = ""
        
        # Get simulation ID for this region (supports per-region IDs)
        simulation_id = get_simulation_id_for_region(target_region)
        
        return cls(
            target_region=target_region,
            base_url=base_url,
            environment=_env_str("LOAD_TEST_ENVIRONMENT", "staging"),
            test_runner_location=_env_str("TEST_RUNNER_LOCATION", "Unknown"),
            test_user_prefix=_env_str("TEST_USER_PREFIX", "loadtest_user_"),
            test_user_domain=_env_str("TEST_USER_DOMAIN", "@test.com"),
            test_password=_env_str("TEST_USER_PASSWORD", "testpassword123"),
            test_user_count=_env_int("TEST_USER_COUNT", 100),
            simulation_id=simulation_id,
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
        
        if self.target_region not in VALID_REGIONS:
            errors.append(f"Invalid TARGET_REGION: '{self.target_region}'. Valid: {VALID_REGIONS}")
        
        if not self.base_url:
            errors.append(f"No URL configured for region '{self.target_region}'. Check TARGET_REGION or set LOAD_TEST_URL manually.")
        
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
        print(f"  Target Region:   {self.target_region}")
        print(f"  Target URL:      {self.base_url}")
        print(f"  Simulation ID:   {self.simulation_id}")
        print(f"  Runner Location: {self.test_runner_location}")
        print(f"  Environment:     {self.environment}")
        print(f"  Max Users:       {self.max_users}")
        print(f"  Spawn Rate:      {self.spawn_rate}/s")
        print(f"  Run Time:        {self.run_time}")
        print(f"  Simulation ID:   {self.simulation_id}")
        print(f"  Test Users:      {self.test_user_prefix}1-{self.test_user_count}{self.test_user_domain}")
        print("=" * 60 + "\n")
    
    # Convenience aliases for consistency
    @property
    def target_url(self) -> str:
        """Alias for base_url."""
        return self.base_url
    
    @property
    def simulation_instance_id(self) -> int:
        """Alias for simulation_id."""
        return self.simulation_id
    
    @property
    def test_user_password(self) -> str:
        """Alias for test_password."""
        return self.test_password
    
    @property
    def debug(self) -> bool:
        """Alias for verbose."""
        return self.verbose
    
    def get_test_user_email(self, user_number: int) -> str:
        """Get email for a specific test user number."""
        return f"{self.test_user_prefix}{user_number}{self.test_user_domain}"


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
    "REGION_URLS",
    "VALID_REGIONS",
    "get_url_for_region",
]

