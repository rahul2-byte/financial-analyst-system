"""Environment-driven application configuration."""

from app.config.models import EnvSettings

Settings = EnvSettings
settings = Settings()

__all__ = ["EnvSettings", "Settings", "settings"]
