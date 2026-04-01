from app.core.policies.retry_policy import (
    MAX_BACKOFF_SECONDS,
    MAX_RETRIES,
    exponential_backoff_seconds,
)


def test_retry_policy_defaults_are_consistent():
    assert MAX_RETRIES == 3
    assert MAX_BACKOFF_SECONDS == 30


def test_exponential_backoff_seconds_caps_at_max():
    assert exponential_backoff_seconds(0) == 1
    assert exponential_backoff_seconds(1) == 2
    assert exponential_backoff_seconds(4) == 16
    assert exponential_backoff_seconds(10) == MAX_BACKOFF_SECONDS
