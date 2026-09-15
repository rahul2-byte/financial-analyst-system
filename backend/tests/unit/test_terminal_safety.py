from finai.safety import sanitize_terminal_text


def test_terminal_safety_removes_control_sequences_but_keeps_newlines() -> None:
    value = sanitize_terminal_text("safe\x1b]52;c;secret\x07\ntext\x1b[31m")

    assert value == "safe\ntext"
