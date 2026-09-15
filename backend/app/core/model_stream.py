"""Context-local sink for public narrative model tokens."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

TokenSink = Callable[[str], Awaitable[None]]
_token_sink: ContextVar[TokenSink | None] = ContextVar("public_token_sink", default=None)
_publishing_public_tokens: ContextVar[bool] = ContextVar(
    "publishing_public_tokens", default=False
)


def get_public_token_sink() -> TokenSink | None:
    return _token_sink.get() if _publishing_public_tokens.get() else None


def get_captured_token_sink() -> TokenSink | None:
    """Return the run-level sink without granting publication permission."""
    return _token_sink.get()


@contextmanager
def capture_public_tokens(sink: TokenSink) -> Iterator[None]:
    token = _token_sink.set(sink)
    try:
        yield
    finally:
        _token_sink.reset(token)


@contextmanager
def publish_public_tokens() -> Iterator[None]:
    """Allow the current public narrative call to forward model tokens."""
    token = _publishing_public_tokens.set(True)
    try:
        yield
    finally:
        _publishing_public_tokens.reset(token)
