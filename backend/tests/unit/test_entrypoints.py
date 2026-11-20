import logging
import socket

import pytest
from fastapi.testclient import TestClient
from finai import __main__ as finai_main


def test_console_script_target_exists():
    assert callable(finai_main.main)


def test_cli_help_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["finai", "--help"])
    with pytest.raises(SystemExit) as exc:
        finai_main.main()
    assert exc.value.code == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_cli_bad_args_exit_nonzero(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["finai", "--definitely-not-a-flag"])
    with pytest.raises(SystemExit) as exc:
        finai_main.main()
    assert exc.value.code == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_health_endpoint(monkeypatch):
    import app.observability.tracing as tracing_module
    from app.config import settings

    # Importing app.main configures global logging and tracing; undo both afterwards.
    monkeypatch.setattr(settings, "FINAI_OBSERVABILITY_ENABLED", False)
    # Restore the global tracing handle on teardown (monkeypatch records the old value).
    monkeypatch.setattr(tracing_module, "_handle", tracing_module._handle)
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    filters = {handler: list(handler.filters) for handler in handlers}
    try:
        from app.main import app
    finally:
        root.setLevel(level)
        root.handlers[:] = handlers
        for handler, saved in filters.items():
            handler.filters[:] = saved

    response = TestClient(app).get("/api/health")
    assert response.status_code == 200


def test_socket_guard_blocks_external_connections():
    with pytest.raises(RuntimeError, match="network access blocked"):
        socket.create_connection(("203.0.113.1", 80), timeout=0.1)
    with pytest.raises(RuntimeError, match="network access blocked"):
        socket.socket().connect(("203.0.113.1", 80))


@pytest.mark.live
def test_live_marker_disables_guard():
    assert socket.socket.connect.__name__ != "guarded_connect"
