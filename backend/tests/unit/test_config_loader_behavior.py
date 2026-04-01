import app.config as app_config


def test_default_model_falls_back_when_yaml_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        app_config,
        "_load_yaml_config",
        lambda: (_ for _ in ()).throw(FileNotFoundError("missing yaml")),
    )

    cfg = app_config.AppSettings()

    assert cfg.DEFAULT_LLM_MODEL == cfg.FALLBACK_LLM_MODEL


def test_env_override_default_model_does_not_require_yaml(monkeypatch) -> None:
    monkeypatch.setenv("DEFAULT_LLM_MODEL", "env-priority-model")
    monkeypatch.setattr(
        app_config,
        "_load_yaml_config",
        lambda: (_ for _ in ()).throw(FileNotFoundError("missing yaml")),
    )

    cfg = app_config.AppSettings()

    assert cfg.DEFAULT_LLM_MODEL == "env-priority-model"
