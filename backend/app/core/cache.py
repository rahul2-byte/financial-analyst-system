"""
Thread-safe caching for LLM responses and tool results.

This module provides:
- TTL-based cache with thread safety
- Decorators for caching function results
- Cache management utilities

Usage:
    from app.core.cache import Cache, cached_llm_response, cached_tool_result

    cache = Cache(default_ttl=300.0)

    @cached_llm_response(ttl=300.0)
    async def llm_call(prompt):
        ...
"""

import hashlib
import json
import logging
import time
import threading
from typing import Any, Optional, Callable, Dict, Tuple
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)


class Cache:
    """
    Thread-safe TTL-based cache with lock protection.

    Features:
    - Time-to-live expiration
    - Thread-safe operations
    - Automatic cleanup of expired entries

    Usage:
        cache = Cache(default_ttl=300.0)
        cache.set("key", value, ttl=600.0)
        value = cache.get("key")
    """

    def __init__(self, default_ttl: float = 300.0):
        """
        Initialize cache.

        Args:
            default_ttl: Default time-to-live in seconds (default: 5 minutes)
        """
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._default_ttl = default_ttl
        self._lock = threading.RLock()

    def _make_key(self, *args, **kwargs) -> str:
        """Create a cache key from arguments."""
        key_data = json.dumps(
            {"args": args, "kwargs": kwargs}, sort_keys=True, default=str
        )
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    return value
                else:
                    del self._cache[key]
            return None

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Set value in cache with TTL."""
        with self._lock:
            ttl = ttl or self._default_ttl
            expiry = time.time() + ttl
            self._cache[key] = (value, expiry)

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        """Return number of cached items (excluding expired)."""
        with self._lock:
            now = time.time()
            self._cache = {k: v for k, v in self._cache.items() if v[1] >= now}
            return len(self._cache)

    def cleanup_expired(self) -> int:
        """Remove expired entries and return count of removed items."""
        with self._lock:
            now = time.time()
            expired_keys = [k for k, v in self._cache.items() if v[1] < now]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)


_llm_response_cache = Cache(default_ttl=300.0)
_tool_result_cache = Cache(default_ttl=600.0)


def cached_llm_response(ttl: float = 300.0):
    """
    Decorator for caching LLM responses.

    Args:
        ttl: Time-to-live in seconds

    Usage:
        @cached_llm_response(ttl=300.0)
        async def llm_call(prompt):
            ...
    """
    return _make_cache_wrapper(_llm_response_cache, ttl)


def _make_cache_wrapper(cache: Cache, ttl: float):
    """Create a unified cache wrapper for both sync and async functions."""

    def wrapper(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            cache_key = cache._make_key(*args, **kwargs)
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return cached
            result = await func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            cache_key = cache._make_key(*args, **kwargs)
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return cached
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return wrapper


def cached_tool_result(ttl: float = 600.0):
    """
    Decorator for caching tool results.

    Args:
        ttl: Time-to-live in seconds

    Usage:
        @cached_tool_result(ttl=600.0)
        def fetch_data(ticker):
            ...
    """
    return _make_cache_wrapper(_tool_result_cache, ttl)


def clear_all_caches() -> None:
    """Clear all caches."""
    _llm_response_cache.clear()
    _tool_result_cache.clear()
    logger.info("All caches cleared")


def get_cache_stats() -> Dict[str, int]:
    """Get statistics about cache usage."""
    return {
        "llm_response_cache_size": len(_llm_response_cache),
        "tool_result_cache_size": len(_tool_result_cache),
    }
