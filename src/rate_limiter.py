"""
Rate limiting module for controlling request frequency.
Implements per-domain rate limiting and configurable delays between requests.
"""

import asyncio
import time
import logging
from typing import Dict, Optional
from collections import defaultdict
from urllib.parse import urlparse
import random
import threading

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Thread-safe rate limiter for controlling request frequency per domain.
    Tracks requests per domain and enforces maximum requests per minute.
    """
    
    def __init__(self, max_requests_per_minute: int = 30):
        """
        Initialize rate limiter.
        
        Args:
            max_requests_per_minute: Maximum requests allowed per domain per minute
        """
        self.max_requests_per_minute = max_requests_per_minute
        self.request_times: Dict[str, list] = defaultdict(list)
        self.lock = threading.Lock()
        logger.info(f"Rate limiter initialized: max {max_requests_per_minute} requests/minute per domain")
    
    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc or parsed.path.split('/')[0]
        except Exception:
            return url
    
    def _clean_old_requests(self, domain: str, current_time: float) -> None:
        """Remove request timestamps older than 60 seconds."""
        cutoff_time = current_time - 60.0
        self.request_times[domain] = [
            req_time for req_time in self.request_times[domain]
            if req_time > cutoff_time
        ]
    
    async def wait_if_needed(self, url: str) -> None:
        """
        Wait if necessary to respect rate limits for the given domain.
        PROACTIVE: Waits BEFORE making request if we're close to the limit.
        
        Args:
            url: URL being requested
        """
        domain = self._get_domain(url)
        current_time = time.time()
        
        with self.lock:
            self._clean_old_requests(domain, current_time)
            request_count = len(self.request_times[domain])
            
            # PROACTIVE: If we're at 80% of limit, wait a bit to avoid hitting it
            threshold = int(self.max_requests_per_minute * 0.8)
            if request_count >= threshold:
                if request_count >= self.max_requests_per_minute:
                    # Already at limit - wait until oldest request expires
                    oldest_request = min(self.request_times[domain])
                    wait_time = 60.0 - (current_time - oldest_request) + 0.1
                    if wait_time > 0:
                        logger.info(f"Rate limit reached for {domain}: {request_count}/{self.max_requests_per_minute} requests. Waiting {wait_time:.2f}s")
                        await asyncio.sleep(wait_time)
                        current_time = time.time()
                        self._clean_old_requests(domain, current_time)
                else:
                    # Close to limit - wait a bit to spread out requests
                    wait_time = 2.0  # Wait 2 seconds to spread out requests
                    logger.debug(f"Rate limit approaching for {domain}: {request_count}/{self.max_requests_per_minute} requests. Waiting {wait_time:.2f}s to spread out")
                    await asyncio.sleep(wait_time)
                    current_time = time.time()
                    self._clean_old_requests(domain, current_time)
            
            # Record this request
            self.request_times[domain].append(current_time)
    
    def record_request(self, url: str) -> None:
        """
        Record a request for rate limiting purposes.
        This is called after the request is made.
        
        Args:
            url: URL that was requested
        """
        domain = self._get_domain(url)
        current_time = time.time()
        
        with self.lock:
            self._clean_old_requests(domain, current_time)
            self.request_times[domain].append(current_time)


class DelayManager:
    """
    Manages configurable delays between page requests with randomization.
    """
    
    def __init__(self, min_delay: float = 2.0, max_delay: float = 5.0):
        """
        Initialize delay manager.
        
        Args:
            min_delay: Minimum delay in seconds
            max_delay: Maximum delay in seconds
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        logger.info(f"Delay manager initialized: {min_delay}-{max_delay}s between pages")
    
    async def wait_between_pages(self) -> None:
        """
        Wait a random amount of time between page requests.
        This simulates human browsing behavior.
        """
        delay = random.uniform(self.min_delay, self.max_delay)
        logger.debug(f"Waiting {delay:.2f}s before next page request")
        await asyncio.sleep(delay)


# Global instances (will be initialized with config)
_rate_limiter: Optional[RateLimiter] = None
_delay_manager: Optional[DelayManager] = None


def initialize_rate_limiter(max_requests_per_minute: int = 30) -> None:
    """Initialize the global rate limiter."""
    global _rate_limiter
    _rate_limiter = RateLimiter(max_requests_per_minute)


def initialize_delay_manager(min_delay: float = 2.0, max_delay: float = 5.0) -> None:
    """Initialize the global delay manager."""
    global _delay_manager
    _delay_manager = DelayManager(min_delay, max_delay)


async def wait_for_rate_limit(url: str) -> None:
    """
    Wait if necessary to respect rate limits.
    
    Args:
        url: URL being requested
    """
    if _rate_limiter:
        await _rate_limiter.wait_if_needed(url)


async def wait_between_pages() -> None:
    """Wait a random delay between page requests."""
    if _delay_manager:
        await _delay_manager.wait_between_pages()


def record_request(url: str) -> None:
    """
    Record a request for rate limiting.
    
    Args:
        url: URL that was requested
    """
    if _rate_limiter:
        _rate_limiter.record_request(url)

