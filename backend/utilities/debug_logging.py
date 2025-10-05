"""
Debug logging utility with environment-based controls
Only logs in development mode to prevent sensitive information exposure in production
"""
import os
import logging

# Get logger
logger = logging.getLogger(__name__)

def is_development() -> bool:
    """Check if we're in development mode"""
    return os.getenv('ENVIRONMENT', 'development').lower() in ['development', 'dev', 'local']

def debug_log(message: str, *args, **kwargs):
    """Debug log that only outputs in development mode"""
    if is_development():
        print(f"[DEBUG] {message}", *args, **kwargs)

def debug_logger(message: str, *args, **kwargs):
    """Debug logger that only outputs in development mode"""
    if is_development():
        logger.debug(f"[DEBUG] {message}", *args, **kwargs)
