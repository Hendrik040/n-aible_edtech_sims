"""
Rate Limiting Utilities for AI Agent Education Platform
Provides IP-based rate limiting for anonymous operations using in-memory storage
"""

import time
import threading
import asyncio
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timedelta, timezone
from fastapi import Request, HTTPException
from pydantic import BaseModel
from collections import defaultdict, deque
from functools import wraps

class RateLimitConfig(BaseModel):
    """Configuration for rate limiting"""
    max_requests: int = 5  # Maximum requests per window
    window_seconds: int = 3600  # Time window in seconds (1 hour)
    key_prefix: str = "rate_limit"
    
class RateLimitResult(BaseModel):
    """Result of rate limit check"""
    allowed: bool
    remaining: int
    reset_time: datetime
    retry_after: Optional[int] = None

class RateLimiter:
    """In-memory rate limiter for IP addresses using sliding window"""
    
    def __init__(self):
        """
        Initialize rate limiter with in-memory storage
        """
        self._storage: Dict[str, deque] = defaultdict(deque)
        self._lock = threading.RLock()  # Thread-safe access
        self._cleanup_interval = 300  # Clean up old entries every 5 minutes
        self._last_cleanup = time.time()
    
    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request
        
        Args:
            request: FastAPI request object
            
        Returns:
            Client IP address
        """
        # Check for forwarded headers (for reverse proxy setups)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        if request.client and hasattr(request.client, 'host'):
            return request.client.host
        
        return "unknown"
    
    def _get_rate_limit_key(self, ip: str, operation: str) -> str:
        """
        Generate key for rate limiting
        
        Args:
            ip: Client IP address
            operation: Operation being rate limited
            
        Returns:
            Rate limit key string
        """
        return f"rate_limit:{operation}:{ip}"
    
    def _cleanup_old_entries(self):
        """Clean up old entries to prevent memory leaks"""
        current_time = time.time()
        if current_time - self._last_cleanup < self._cleanup_interval:
            return
        
        with self._lock:
            keys_to_remove = []
            for key, timestamps in self._storage.items():
                # Remove timestamps older than 2 hours (safety buffer)
                cutoff_time = current_time - 7200
                while timestamps and timestamps[0] < cutoff_time:
                    timestamps.popleft()
                
                # Remove empty entries
                if not timestamps:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self._storage[key]
            
            self._last_cleanup = current_time

    def check_rate_limit(
        self, 
        request: Request, 
        operation: str,
        config: RateLimitConfig
    ) -> RateLimitResult:
        """
        Check if request is within rate limits using sliding window
        
        Args:
            request: FastAPI request object
            operation: Operation name (e.g., 'anonymous_review')
            config: Rate limiting configuration
            
        Returns:
            RateLimitResult with limit status and metadata
        """
        # Periodic cleanup
        self._cleanup_old_entries()
        
        client_ip = self._get_client_ip(request)
        key = self._get_rate_limit_key(client_ip, operation)
        current_time = time.time()
        window_start = current_time - config.window_seconds
        
        with self._lock:
            # Get or create the deque for this key
            timestamps = self._storage[key]
            
            # Remove timestamps outside the window
            while timestamps and timestamps[0] < window_start:
                timestamps.popleft()
            
            # Check if we're within the limit
            if len(timestamps) >= config.max_requests:
                # Rate limit exceeded
                oldest_timestamp = timestamps[0] if timestamps else current_time
                retry_after = int(config.window_seconds - (current_time - oldest_timestamp))
                retry_after = max(1, retry_after)  # At least 1 second
                reset_time = datetime.now(timezone.utc) + timedelta(seconds=retry_after)
                
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    reset_time=reset_time,
                    retry_after=retry_after
                )
            
            # Add current timestamp
            timestamps.append(current_time)
            remaining = config.max_requests - len(timestamps)
            
            # Calculate reset time (when the oldest request will expire)
            if timestamps:
                oldest_timestamp = timestamps[0]
                reset_time = datetime.fromtimestamp(oldest_timestamp + config.window_seconds, tz=timezone.utc)
            else:
                reset_time = datetime.now(timezone.utc) + timedelta(seconds=config.window_seconds)
            
            return RateLimitResult(
                allowed=True,
                remaining=remaining,
                reset_time=reset_time
            )
    
    def get_rate_limit_headers(self, result: RateLimitResult, config: RateLimitConfig) -> Dict[str, str]:
        """
        Generate rate limit headers for HTTP response
        
        Args:
            result: Rate limit check result
            config: Rate limiting configuration
            
        Returns:
            Dictionary of HTTP headers
        """
        headers = {
            "X-RateLimit-Limit": str(config.max_requests),
            "X-RateLimit-Remaining": str(result.remaining),
            "X-RateLimit-Reset": str(int(result.reset_time.timestamp()))
        }
        
        if result.retry_after:
            headers["X-RateLimit-Retry-After"] = str(result.retry_after)
        
        return headers

# Global rate limiter instance
rate_limiter = RateLimiter()

# Predefined configurations for different operations
ANONYMOUS_REVIEW_CONFIG = RateLimitConfig(
    max_requests=3,  # 3 reviews per hour per IP
    window_seconds=3600,  # 1 hour
    key_prefix="anonymous_review"
)

TEST_LOGIN_CONFIG = RateLimitConfig(
    max_requests=5,  # 5 attempts per hour per IP
    window_seconds=3600,  # 1 hour
    key_prefix="test_login"
)

def check_anonymous_review_rate_limit(request: Request) -> RateLimitResult:
    """
    Check rate limit for anonymous review creation
    
    Args:
        request: FastAPI request object
        
    Returns:
        RateLimitResult with limit status
        
    Raises:
        HTTPException: If rate limit is exceeded
    """
    result = rate_limiter.check_rate_limit(request, "anonymous_review", ANONYMOUS_REVIEW_CONFIG)
    
    if not result.allowed:
        headers = rate_limiter.get_rate_limit_headers(result, ANONYMOUS_REVIEW_CONFIG)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "message": f"Too many anonymous reviews. You can create {ANONYMOUS_REVIEW_CONFIG.max_requests} reviews per hour.",
                "retry_after": result.retry_after,
                "reset_time": result.reset_time.isoformat()
            },
            headers=headers
        )
    
    return result

def check_test_login_rate_limit(request: Request) -> RateLimitResult:
    """
    Check rate limit for test-login endpoint
    
    Args:
        request: FastAPI request object
        
    Returns:
        RateLimitResult with limit status
        
    Raises:
        HTTPException: If rate limit is exceeded
    """
    result = rate_limiter.check_rate_limit(request, "test_login", TEST_LOGIN_CONFIG)
    
    if not result.allowed:
        headers = rate_limiter.get_rate_limit_headers(result, TEST_LOGIN_CONFIG)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "message": f"Too many login attempts. You can make {TEST_LOGIN_CONFIG.max_requests} attempts per hour.",
                "retry_after": result.retry_after,
                "reset_time": result.reset_time.isoformat()
            },
            headers=headers
        )
    
    return result

def async_retry(retries: int = 3, delay: float = 1.0):
    """
    Decorator for retrying async functions with exponential backoff
    
    Args:
        retries: Number of retry attempts
        delay: Initial delay between retries in seconds
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < retries:
                        wait_time = delay * (2 ** attempt)  # Exponential backoff
                        await asyncio.sleep(wait_time)
                    else:
                        raise last_exception
            
            return None
        return wrapper
    return decorator