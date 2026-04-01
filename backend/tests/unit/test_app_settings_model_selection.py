from app.config import (
    ApiConfig,
    AppSettings,
    LlamaServerConfig,
    ModelConfig,
    Settings,
    YamlAppSettings,
)


def _yaml_config(default_model: str) -> YamlAppSettings:
    return YamlAppSettings(
        llama_server=LlamaServerConfig(
            binary_path="/tmp/llama-server",
            model_path="/tmp/model.gguf",
            host="127.0.0.1",
            port=8080,
            args={},
        ),
        api=ApiConfig(base_url="http://127.0.0.1:8000", timeout=30.0),
        model=ModelConfig(default_model=default_model, max_output_tokens=1024),
        server_logfile="/tmp/llama.log",
    )


def test_default_llm_model_falls_back_to_yaml_when_env_not_set():
    settings = AppSettings()
    object.__setattr__(settings, "_yaml_config", _yaml_config("mistral-yaml"))
    object.__setattr__(settings, "_env_config", Settings(DEFAULT_LLM_MODEL=None))

    assert settings.DEFAULT_LLM_MODEL == "mistral-yaml"


def test_default_llm_model_prefers_env_override_when_set():
    settings = AppSettings()
    object.__setattr__(settings, "_yaml_config", _yaml_config("mistral-yaml"))
    object.__setattr__(settings, "_env_config", Settings(DEFAULT_LLM_MODEL="mistral-env"))

    assert settings.DEFAULT_LLM_MODEL == "mistral-env"
