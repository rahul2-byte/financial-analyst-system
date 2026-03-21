import yaml
from pathlib import Path
from pydantic import BaseModel, HttpUrl
from typing import Dict, Any

# --- Model Schemas for Type-Safe Configuration ---


class LlamaServerConfig(BaseModel):
    binary_path: str
    model_path: str
    host: str
    port: int
    args: Dict[str, Any]


class ApiConfig(BaseModel):
    base_url: HttpUrl
    timeout: float


class ModelConfig(BaseModel):
    default_model: str
    max_output_tokens: int


class AppSettings(BaseModel):
    API_TITLE: str = "Financial Intelligence Platform API"
    API_VERSION: str = "v1"
    DEBUG: bool = False
    llama_server: LlamaServerConfig
    api: ApiConfig
    model: ModelConfig
    server_logfile: str


# --- Configuration Loading Logic ---


def get_backend_root() -> Path:
    """
    Determines the absolute path to the 'backend' directory,
    which is the root of this project.
    """
    # This file is in .../backend/app/config.py
    # We want the path to .../backend/
    return Path(__file__).parent.parent.resolve()


def load_config() -> AppSettings:
    """
    Loads configuration from a YAML file, constructs absolute paths from
    the configured relative paths, and returns a validated AppSettings object.
    """
    backend_root = get_backend_root()
    config_path = backend_root / "config" / "llm_config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")

    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f)

    # --- Path Resolution ---
    # Paths in the YAML are relative to the backend directory.
    # The code constructs absolute paths from them.
    llama_server_config = config_data.get("llama_server", {})

    # Resolve binary and model paths relative to the backend root
    binary_path = backend_root / llama_server_config.get("binary_path", "")
    model_path = backend_root / llama_server_config.get("model_path", "")

    if not binary_path.exists():
        raise FileNotFoundError(
            f"Llama.cpp binary not found at resolved path: {binary_path.resolve()}"
        )
    if not model_path.exists():
        raise FileNotFoundError(
            f"Model file not found at resolved path: {model_path.resolve()}"
        )

    config_data["llama_server"]["binary_path"] = str(binary_path.resolve())
    config_data["llama_server"]["model_path"] = str(model_path.resolve())

    # Resolve log file path relative to the backend root
    server_logfile = backend_root / config_data.get(
        "server_logfile", "logs/llama_server.log"
    )
    config_data["server_logfile"] = str(server_logfile.resolve())

    return AppSettings(**config_data)


# --- Global Settings Singleton ---
settings = load_config()
