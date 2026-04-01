from app.models.request_models import Message


def test_message_content_allows_long_assistant_history_payloads() -> None:
    long_content = "x" * 6000
    message = Message(role="assistant", content=long_content)
    assert message.content == long_content
