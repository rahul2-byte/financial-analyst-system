"""Tests for caching functionality."""

import pytest
import asyncio
import time
from app.core.cache import Cache, cached_llm_response, cached_tool_result


class TestCache:
    """Test Cache class."""

    def test_cache_set_and_get(self):
        """Cache should store and retrieve values."""
        cache = Cache(default_ttl=60)

        cache.set("key1", "value1")
        result = cache.get("key1")

        assert result == "value1"

    def test_cache_expires(self):
        """Cache should expire after TTL."""
        cache = Cache(default_ttl=1)

        cache.set("key1", "value1")
        time.sleep(1.1)

        result = cache.get("key1")

        assert result is None

    def test_cache_clear(self):
        """Cache should clear all entries."""
        cache = Cache()

        cache.set("key1", "value1")
        cache.clear()

        assert len(cache) == 0

    def test_cache_makes_key(self):
        """Cache should create consistent keys."""
        cache = Cache()

        key1 = cache._make_key("arg1", kwarg1="value1")
        key2 = cache._make_key("arg1", kwarg1="value1")

        assert key1 == key2


class TestCachedDecorator:
    """Test cached decorators."""

    @pytest.mark.asyncio
    async def test_cached_llm_response(self):
        """Cached decorator should cache async results."""
        call_count = 0

        @cached_llm_response(ttl=60)
        async def mock_llm_call(messages, model):
            nonlocal call_count
            call_count += 1
            return f"response-{call_count}"

        result1 = await mock_llm_call([], "model")

        result2 = await mock_llm_call([], "model")

        assert result1 == result2
        assert call_count == 1

    def test_cached_tool_result_sync(self):
        """Cached decorator should cache sync results."""
        call_count = 0

        @cached_tool_result(ttl=60)
        def mock_tool_call(param):
            nonlocal call_count
            call_count += 1
            return f"result-{call_count}"

        result1 = mock_tool_call("test")
        result2 = mock_tool_call("test")

        assert result1 == result2
        assert call_count == 1
