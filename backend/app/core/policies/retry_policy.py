"""Centralized retry/backoff policy constants and helpers."""

MAX_RETRIES = 3
MAX_BACKOFF_SECONDS = 30


def exponential_backoff_seconds(retry_count: int) -> int:
    """Return capped exponential backoff seconds for zero-based retry count."""
    return min(2**retry_count, MAX_BACKOFF_SECONDS)
