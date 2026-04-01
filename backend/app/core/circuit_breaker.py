"""Circuit Breaker implementation for external service protection."""

import time
import logging
from enum import Enum
from typing import Callable, Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerOpen(Exception):
    """Raised when circuit is open and call is rejected."""

    pass


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures from external services.

    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Service is failing, calls are rejected immediately
    - HALF_OPEN: Testing if service has recovered
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if self._last_failure_time:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    logger.info(
                        f"Circuit '{self.name}': Opening half-open state after {elapsed:.1f}s"
                    )
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
        return self._state

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            logger.info(f"Circuit '{self.name}': Success in half-open, closing circuit")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            logger.warning(f"Circuit '{self.name}': Failure in half-open, reopening")
            self._state = CircuitState.OPEN
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.failure_threshold:
                logger.warning(
                    f"Circuit '{self.name}': Opening after {self._failure_count} failures"
                )
                self._state = CircuitState.OPEN

    def can_execute(self) -> bool:
        """Check if a call can be executed."""
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            return self._half_open_calls < self.half_open_max_calls
        return False  # OPEN

    def __call__(self, func: Callable) -> Callable:
        """Use as decorator."""

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not self.can_execute():
                raise CircuitBreakerOpen(f"Circuit '{self.name}' is open")

            if self.state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1

            try:
                result = await func(*args, **kwargs)
                self.record_success()
                return result
            except Exception as e:
                self.record_failure()
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not self.can_execute():
                raise CircuitBreakerOpen(f"Circuit '{self.name}' is open")

            if self.state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1

            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
            except Exception as e:
                self.record_failure()
                raise

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper


# Singleton circuit breakers for each service
_circuits: dict[str, CircuitBreaker] = {}


def get_circuit(name: str, **kwargs) -> CircuitBreaker:
    """Get or create a circuit breaker for a service."""
    if name not in _circuits:
        _circuits[name] = CircuitBreaker(name, **kwargs)
    return _circuits[name]
