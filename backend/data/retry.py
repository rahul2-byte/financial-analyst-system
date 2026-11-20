"""Shared bounded retry, backoff and timeout helpers for provider adapters."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_AFTER_SECONDS = 30.0


class ProviderUnavailable(RuntimeError):
    """A provider could not serve a request (outage, rate limit, missing key).

    Callers must report this as "unavailable", never as "no data".
    """

    def __init__(
        self,
        provider: str,
        reason: str,
        *,
        status_code: int | None = None,
        attempts: int = 0,
    ) -> None:
        self.provider = provider
        self.reason = reason
        self.status_code = status_code
        self.attempts = attempts
        super().__init__(f"{provider} unavailable: {reason}")


def is_retryable(exc: BaseException) -> bool:
    """Return True for transient failures: timeouts, transport errors, 429/5xx."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    name = type(exc).__name__.lower()
    return "ratelimit" in name or "toomanyrequests" in name


def _status_code(exc: BaseException) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    value = getattr(exc, "status_code", None)
    return value if isinstance(value, int) else None


def _retry_after(exc: BaseException) -> float | None:
    if isinstance(exc, httpx.HTTPStatusError):
        raw = exc.response.headers.get("retry-after")
        if raw:
            try:
                return min(max(float(raw), 0.0), MAX_RETRY_AFTER_SECONDS)
            except ValueError:
                return None
    return None


def backoff_delay(
    attempt: int,
    *,
    base_delay: float,
    max_delay: float,
    jitter: Callable[[], float] = random.random,
) -> float:
    """Exponential backoff scaled by jitter into [0.5x, 1.0x] of the capped delay."""
    capped = min(max_delay, base_delay * (2 ** (attempt - 1)))
    return capped * (0.5 + 0.5 * jitter())


def _exhausted(provider: str, exc: BaseException, attempt: int) -> ProviderUnavailable:
    return ProviderUnavailable(
        provider,
        f"{type(exc).__name__} after {attempt} attempts",
        status_code=_status_code(exc),
        attempts=attempt,
    )


def _next_delay(
    exc: BaseException, attempt: int, base_delay: float, max_delay: float, jitter: Any
) -> float:
    delay = _retry_after(exc)
    if delay is None:
        delay = backoff_delay(
            attempt, base_delay=base_delay, max_delay=max_delay, jitter=jitter
        )
    return delay


def call_with_retry(
    function: Callable[[], T],
    *,
    provider: str,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
    retryable: Callable[[BaseException], bool] = is_retryable,
) -> T:
    """Run ``function`` with bounded retries; raise ProviderUnavailable when spent.

    Non-retryable exceptions propagate unchanged.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    attempt = 0
    while True:
        attempt += 1
        try:
            return function()
        except Exception as exc:
            if not retryable(exc):
                raise
            if attempt >= attempts:
                raise _exhausted(provider, exc, attempt) from exc
            delay = _next_delay(exc, attempt, base_delay, max_delay, jitter)
            logger.warning(
                "%s transient failure (%s); retrying in %.2fs",
                provider,
                type(exc).__name__,
                delay,
            )
            sleep(delay)


async def acall_with_retry(
    function: Callable[[], Awaitable[T]],
    *,
    provider: str,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    jitter: Callable[[], float] = random.random,
    retryable: Callable[[BaseException], bool] = is_retryable,
) -> T:
    """Async twin of :func:`call_with_retry`."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    attempt = 0
    while True:
        attempt += 1
        try:
            return await function()
        except Exception as exc:
            if not retryable(exc):
                raise
            if attempt >= attempts:
                raise _exhausted(provider, exc, attempt) from exc
            await sleep(_next_delay(exc, attempt, base_delay, max_delay, jitter))


def call_with_timeout(function: Callable[[], T], timeout: float) -> T:
    """Run a blocking call in a worker thread and raise TimeoutError on expiry.

    The worker cannot be killed; it is abandoned (not joined) after the timeout.
    """
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="provider-call")
    future = executor.submit(function)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError as exc:
        raise TimeoutError(f"provider call exceeded {timeout:.1f}s") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def provider_retry_kwargs() -> dict[str, Any]:
    """Retry settings from configuration."""
    from app.config import settings

    return {
        "attempts": int(settings.PROVIDER_RETRY_ATTEMPTS),
        "base_delay": float(settings.PROVIDER_RETRY_BASE_SECONDS),
        "max_delay": float(settings.PROVIDER_RETRY_MAX_SECONDS),
    }
