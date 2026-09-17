from datetime import UTC, datetime, timedelta

from app.security.policy import (
    DataLicense,
    Permission,
    authorize,
    license_is_valid,
    redact_secrets,
)


def test_redact_secrets_removes_keys_and_bearer_tokens() -> None:
    value = redact_secrets(
        {"api_key": "secret", "nested": {"Authorization": "Bearer abc"}}
    )

    assert value == {
        "api_key": "[REDACTED]",
        "nested": {"Authorization": "Bearer [REDACTED]"},
    }


def test_permissions_and_license_expiry_are_explicit() -> None:
    permission = Permission(subject="agent", action="read", resource="prices")
    assert authorize(permission, permission)
    license = DataLicense(
        source="nse",
        permitted_use="research",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    assert license_is_valid(license)
