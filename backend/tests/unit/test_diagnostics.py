from app.core.diagnostics import diagnostic_payload, diagnostics_enabled


def test_diagnostic_payload_redacts_sensitive_keys_and_truncates() -> None:
    payload = diagnostic_payload({"api_key": "secret", "query": "x" * 20}, max_chars=24)

    assert "secret" not in payload
    assert "[REDACTED]" in payload
    assert payload.endswith("…")


def test_diagnostics_enabled_requires_explicit_environment(monkeypatch) -> None:
    monkeypatch.delenv("FINAI_DIAGNOSTICS", raising=False)
    assert diagnostics_enabled() is False
    monkeypatch.setenv("FINAI_DIAGNOSTICS", "trace")
    assert diagnostics_enabled() is True
