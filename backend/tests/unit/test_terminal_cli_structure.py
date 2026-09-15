from pathlib import Path

from finai.cli import parse_arguments
from finai.session import FinAIRepl


def test_cli_parser_keeps_runtime_options_explicit() -> None:
    options = parse_arguments(["--plain", "--mode", "review", "Analyze", "INFY"])

    assert options.plain is True
    assert options.mode == "review"
    assert options.query == ["Analyze", "INFY"]
    assert options.data_dir == Path(".finai")


def test_session_controller_remains_importable_from_its_owner() -> None:
    assert FinAIRepl.__module__ == "finai.session"
