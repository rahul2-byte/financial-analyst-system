import asyncio

from app.core.model_stream import (
    capture_public_tokens,
    get_public_token_sink,
    publish_public_tokens,
)


async def _sink(_token: str) -> None:
    await asyncio.sleep(0)


def test_captured_sink_is_published_only_inside_report_scope() -> None:
    with capture_public_tokens(_sink):
        assert get_public_token_sink() is None
        with publish_public_tokens():
            assert get_public_token_sink() is _sink
        assert get_public_token_sink() is None
