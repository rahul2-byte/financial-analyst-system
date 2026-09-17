from finai.cli import parse_arguments


def test_cli_parser_exposes_plain_mode() -> None:
    options = parse_arguments(["--plain", "--data-dir", ".finai"])

    assert options.plain is True
