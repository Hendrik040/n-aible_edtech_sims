"""
Environment detection utilities
"""
import os
from typing import Optional


def is_production() -> bool:
    """
    Check if the application is running in production environment.
    
    Returns:
        bool: True if in production, False otherwise
    """
    # Check multiple environment variables for production detection
    env_vars = [
        'ENVIRONMENT',
        'ENV', 
        'FLASK_ENV',
        'APP_ENV'
    ]
    
    for env_var in env_vars:
        value = os.getenv(env_var, '').lower()
        if value == 'production':
            return True
    
    # Check for DEBUG setting as secondary source
    try:
        from database.connection import settings
        return not getattr(settings, 'DEBUG', True)
    except ImportError:
        # If settings can't be imported, assume development
        return False


def get_environment() -> str:
    """
    Get the current environment name.
    
    Returns:
        str: Environment name (production, development, etc.)
    """
    if is_production():
        return 'production'
    else:
        return 'development'
