from finai.commands import CommandRegistry, parse_command


def test_command_parser_separates_command_and_arguments() -> None:
    command, arguments = parse_command("/resume abc123")

    assert command == "resume"
    assert arguments == ["abc123"]


def test_unknown_command_is_not_registered() -> None:
    registry = CommandRegistry.default()

    assert registry.get("settings") is None
    assert registry.get("status") is not None


def test_registry_suggests_commands_for_slash_input() -> None:
    registry = CommandRegistry.default()

    assert registry.suggestions("s") == ["sources", "status", "sessions"]


def test_registry_exposes_command_descriptions_for_palette() -> None:
    registry = CommandRegistry.default()

    assert [
        (item.name, item.description) for item in registry.suggestion_items("st")
    ] == [("status", "Show current run status")]


def test_registry_formats_help_from_the_command_catalog() -> None:
    help_text = CommandRegistry.default().help_text()

    assert "/help  Show commands" in help_text
    assert "/trace  Show the current execution trace" in help_text
