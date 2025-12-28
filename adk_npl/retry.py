"""
Retry utilities for resilient NPL Engine calls.

Provides exponential backoff retry logic for handling transient failures.
"""

import time
import logging
from typing import Callable, TypeVar, Optional, List
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryableError(Exception):
    """Base exception for errors that should trigger retries."""
    pass


class NonRetryableError(Exception):
    """Base exception for errors that should not trigger retries."""
    pass


def is_retryable_status_code(status_code: int) -> bool:
    """
    Determine if an HTTP status code indicates a retryable error.
    
    Args:
        status_code: HTTP status code
        
    Returns:
        True if the error is retryable
    """
    # Retry on 5xx (server errors) and 429 (rate limiting)
    return status_code >= 500 or status_code == 429


def is_retryable_exception(exception: Exception) -> bool:
    """
    Determine if an exception is retryable.
    
    Args:
        exception: Exception to check
        
    Returns:
        True if the exception is retryable
    """
    # Network errors are retryable
    if isinstance(exception, (ConnectionError, TimeoutError)):
        return True
    
    # Check for requests exceptions
    import requests
    if isinstance(exception, requests.exceptions.RequestException):
        if hasattr(exception, 'response') and exception.response is not None:
            return is_retryable_status_code(exception.response.status_code)
        # Connection/timeout errors are retryable
        return isinstance(exception, (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ReadTimeout
        ))
    
    return False


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: Optional[List[type]] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Decorator for retrying function calls with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 60.0)
        exponential_base: Base for exponential backoff (default: 2.0)
        retryable_exceptions: List of exception types that should trigger retries
        on_retry: Optional callback function called on each retry (exception, attempt_number)
        
    Returns:
        Decorated function
    """
    if retryable_exceptions is None:
        retryable_exceptions = []
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    # Check if we should retry
                    should_retry = (
                        attempt < max_retries and
                        (
                            any(isinstance(e, exc_type) for exc_type in retryable_exceptions) or
                            is_retryable_exception(e)
                        )
                    )
                    
                    if not should_retry:
                        logger.error(
                            f"Non-retryable error in {func.__name__} (attempt {attempt + 1}/{max_retries + 1}): {e}"
                        )
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(
                        initial_delay * (exponential_base ** attempt),
                        max_delay
                    )
                    
                    # Add jitter to prevent thundering herd
                    import random
                    jitter = random.uniform(0, delay * 0.1)
                    total_delay = delay + jitter
                    
                    logger.warning(
                        f"Retryable error in {func.__name__} (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {total_delay:.2f}s..."
                    )
                    
                    if on_retry:
                        on_retry(e, attempt + 1)
                    
                    time.sleep(total_delay)
            
            # If we exhausted all retries, raise the last exception
            logger.error(
                f"Max retries exceeded for {func.__name__} after {max_retries + 1} attempts"
            )
            raise last_exception
        
        return wrapper
    return decorator

