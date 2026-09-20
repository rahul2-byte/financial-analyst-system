from __future__ import annotations

from app.observability.tracing import redact_trace_value, trace_content


def test_redact_trace_value_removes_credentials_without_changing_safe_content() -> None:
    value = {
        "authorization": "Bearer secret-token",
        "api_key": "secret-key",
        "nested": {"cookie": "session-secret", "query": "HDFC BANK"},
    }

    result = redact_trace_value(value)

    assert result == {
        "authorization": "Bearer [REDACTED]",
        "api_key": "[REDACTED]",
        "nested": {"cookie": "[REDACTED]", "query": "HDFC BANK"},
    }


def test_tracing_disabled_returns_noop_safe_handle(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.FINAI_OBSERVABILITY_ENABLED", False)

    from app.observability.tracing import initialize_tracing

    handle = initialize_tracing()

    assert handle.enabled is False


def test_trace_content_is_bounded_and_redacted(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.FINAI_TRACE_CONTENT", "redacted_full")
    monkeypatch.setattr("app.config.settings.FINAI_TRACE_MAX_CONTENT_BYTES", 20)

    content, truncated, original_size = trace_content(
        {"authorization": "Bearer secret", "body": "x" * 100}
    )

    assert truncated is True
    assert original_size > len(content.encode())
    assert "secret" not in content
