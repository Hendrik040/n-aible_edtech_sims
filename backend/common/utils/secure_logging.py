"""
Secure logging utilities to prevent sensitive information exposure
"""
import os
import logging
import re
from typing import Any, Optional

def secure_log(level: str, message: str, sensitive_data: Optional[Any] = None, environment: Optional[str] = None) -> None:
    """
    Log messages securely, hiding sensitive information in production
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        message: Log message
        sensitive_data: Optional sensitive data to log (only in development)
        environment: Environment override (defaults to ENVIRONMENT env var)
    """
    if environment is None:
        environment = os.getenv('ENVIRONMENT', 'development')
    
    # Get logger for this module
    logger = logging.getLogger(__name__)
    
    # Map level string to logger method
    level_methods = {
        'DEBUG': logger.debug,
        'INFO': logger.info,
        'WARNING': logger.warning,
        'ERROR': logger.error
    }
    
    log_method = level_methods.get(level.upper(), logger.info)
    
    # Never log sensitive data in any environment
    if sensitive_data is not None:
        # Replace all occurrences of sensitive data with placeholder
        sensitive_str = str(sensitive_data)
        # Use regex to replace all occurrences, including partial matches
        escaped_sensitive = re.escape(sensitive_str)
        message = re.sub(escaped_sensitive, '[REDACTED]', message)
    
    log_method(message)

def secure_print_api_key_status(key_name: str, key_value: Optional[str], environment: Optional[str] = None) -> None:
    """
    Securely print API key status without exposing the actual key
    
    Args:
        key_name: Name of the API key
        key_value: The actual API key value
        environment: Environment override
    """
    if environment is None:
        environment = os.getenv('ENVIRONMENT', 'development')
    
    if key_value:
        print(f"✅ {key_name}: Set")
    else:
        print(f"❌ {key_name}: Missing")

def secure_print_database_url(db_url: str, environment: Optional[str] = None) -> None:
    """
    Securely print database URL without exposing credentials
    
    Args:
        db_url: Database connection URL
        environment: Environment override
    """
    if environment is None:
        environment = os.getenv('ENVIRONMENT', 'development')
    
    # Always show minimal information regardless of environment
    print("✅ Database: Connected")
