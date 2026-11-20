"""Interactive launch hands off to the Ink UI; its failure modes are actionable."""

from __future__ import annotations

from pathlib import Path

import pytest
from finai import cli


def test_help_has_no_ui_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.parse_arguments(["--help"])
    assert "--ui" not in capsys.readouterr().out


def test_exec_hands_off_to_node(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bundle = tmp_path / "cli.js"
    bundle.write_text("", encoding="utf-8")
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(cli, "TS_CLI", bundle)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/node")
    monkeypatch.setattr(cli.os, "execvp", lambda file, args: calls.append((file, list(args))))

    cli.exec_ts_ui(["--mode", "review"])

    assert calls == [("/usr/bin/node", ["/usr/bin/node", str(bundle), "--mode", "review"])]


def test_missing_bundle_tells_user_to_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli, "TS_CLI", tmp_path / "missing.js")
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/node")

    with pytest.raises(SystemExit, match="cd frontend && npm install && npm run build"):
        cli.exec_ts_ui([])


def test_missing_node_tells_user_to_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundle = tmp_path / "cli.js"
    bundle.write_text("", encoding="utf-8")
    monkeypatch.setattr(cli, "TS_CLI", bundle)
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    with pytest.raises(SystemExit, match="needs node"):
        cli.exec_ts_ui([])


def test_interactive_tty_launch_goes_to_ts_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    launched: list[list[str]] = []

    def fake_exec(argv: list[str]) -> None:
        launched.append(list(argv))
        raise SystemExit(0)

    monkeypatch.setattr(cli.sys, "argv", ["finai", "--mode", "review"])
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(cli, "exec_ts_ui", fake_exec)

    with pytest.raises(SystemExit):
        cli.main()

    assert launched == [["--data-dir", ".finai", "--mode", "review"]]


def test_interactive_argv_forwards_supported_options_and_flags_the_rest(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = cli.parse_arguments(["--session", "abc", "--data-dir", "d", "--debug"])

    assert cli.interactive_argv(args) == [
        "--data-dir",
        "d",
        "--mode",
        "guided",
        "--session",
        "abc",
    ]
    assert "--debug" in capsys.readouterr().err
