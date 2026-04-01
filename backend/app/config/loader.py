from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.config.models import YamlAppSettings
from app.config.paths import get_backend_root


def _resolve_required_file(path: Path, error_prefix: str) -> str:
    if not path.exists():
        raise FileNotFoundError(f"{error_prefix}: {path}")
    return str(path.resolve())


def load_yaml_config() -> YamlAppSettings:
    """Load and validate YAML-backed application settings."""

    backend_root = get_backend_root()
    config_path = backend_root / "config" / "llm_config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        raw_data: dict[str, Any] = yaml.safe_load(file)

    llama_config = raw_data.get("llama_server", {})
    binary_path = backend_root / str(llama_config.get("binary_path", ""))
    model_path = backend_root / str(llama_config.get("model_path", ""))

    raw_data["llama_server"]["binary_path"] = _resolve_required_file(
        binary_path,
        "Llama.cpp binary not found",
    )
    raw_data["llama_server"]["model_path"] = _resolve_required_file(
        model_path,
        "Model file not found",
    )

    logfile = backend_root / str(raw_data.get("server_logfile", "logs/llama_server.log"))
    raw_data["server_logfile"] = str(logfile.resolve())

    return YamlAppSettings(**raw_data)
