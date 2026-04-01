"""Unified application configuration package.

Public API remains compatible with prior imports:

    from app.config import settings
"""

from __future__ import annotations

import logging
from typing import Any

from app.config.loader import load_yaml_config
from app.config.models import ApiConfig, EnvSettings, LlamaServerConfig, ModelConfig, YamlAppSettings

Settings = EnvSettings

logger = logging.getLogger(__name__)


def _load_yaml_config() -> YamlAppSettings:
    """Compatibility wrapper for tests that monkeypatch this loader."""

    return load_yaml_config()


class AppSettings:
    """Unified settings facade for YAML + environment configuration."""

    _yaml_config: YamlAppSettings | None
    _env_config: EnvSettings | None

    def __init__(self) -> None:
        self._yaml_config = None
        self._env_config = None

    def _get_env(self) -> EnvSettings:
        if self._env_config is None:
            self._env_config = EnvSettings()
        assert self._env_config is not None
        return self._env_config

    def _get_yaml(self) -> YamlAppSettings:
        if self._yaml_config is None:
            self._yaml_config = _load_yaml_config()
        assert self._yaml_config is not None
        return self._yaml_config

    @property
    def API_TITLE(self) -> str:
        return self._get_yaml().API_TITLE

    @property
    def API_VERSION(self) -> str:
        return self._get_yaml().API_VERSION

    @property
    def DEBUG(self) -> bool:
        return self._get_yaml().DEBUG

    @property
    def llama_server(self) -> LlamaServerConfig:
        return self._get_yaml().llama_server

    @property
    def api(self) -> ApiConfig:
        return self._get_yaml().api

    @property
    def model(self) -> ModelConfig:
        return self._get_yaml().model

    @property
    def server_logfile(self) -> str:
        return self._get_yaml().server_logfile

    @property
    def DATABASE_URL(self) -> str:
        return self._get_env().DATABASE_URL

    @property
    def QDRANT_URL(self) -> str:
        return self._get_env().QDRANT_URL

    @property
    def DEFAULT_LLM_MODEL(self) -> str:
        env_override = self._get_env().DEFAULT_LLM_MODEL
        if env_override:
            return env_override

        try:
            return self._get_yaml().model.default_model
        except FileNotFoundError:
            logger.warning("YAML config unavailable; using FALLBACK_LLM_MODEL")
            return self._get_env().FALLBACK_LLM_MODEL

    @property
    def FALLBACK_LLM_MODEL(self) -> str:
        return self._get_env().FALLBACK_LLM_MODEL

    def __getattr__(self, name: str) -> Any:
        env = self._get_env()
        if hasattr(env, name):
            return getattr(env, name)

        yaml_settings = self._get_yaml()
        if hasattr(yaml_settings, name):
            return getattr(yaml_settings, name)

        raise AttributeError(f"Unknown setting: {name}")


settings = AppSettings()

__all__ = [
    "ApiConfig",
    "AppSettings",
    "EnvSettings",
    "LlamaServerConfig",
    "ModelConfig",
    "Settings",
    "YamlAppSettings",
    "_load_yaml_config",
    "settings",
]
