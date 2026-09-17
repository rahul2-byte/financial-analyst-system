import json

from app.core.agent_loop.model_events import (
    merge_chunk_tool_calls,
    result_payload,
    sanitize_tool_calls,
)
from app.core.agent_loop.runtime import _extract_sources


def test_sanitize_tool_calls_replaces_invalid_json_arguments() -> None:
    calls = [{"function": {"name": "data:fetch", "arguments": "{"}}]

    sanitized = sanitize_tool_calls(calls)

    assert sanitized[0]["function"]["arguments"] == "{}"


def test_sanitize_tool_calls_drops_nameless_provider_entries() -> None:
    calls = [
        {"index": 0, "function": {"name": "data:fetch_stock_data", "arguments": "{}"}},
        {"index": 1, "function": {"arguments": "{}"}},
    ]

    sanitized = sanitize_tool_calls(calls)

    assert len(sanitized) == 1
    assert sanitized[0]["function"]["name"] == "data:fetch_stock_data"


def test_merge_chunk_tool_calls_keeps_fragmented_arguments() -> None:
    calls: dict[int, dict] = {}
    chunk = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "function": {
                                "name": "x",
                                "arguments": json.dumps({"ticker": "INFY"}),
                            },
                        }
                    ]
                }
            }
        ]
    }

    merge_chunk_tool_calls(calls, chunk)

    assert calls[0]["function"]["name"] == "x"


def test_result_payload_normalizes_scalars() -> None:
    assert result_payload("ok") == {"data": "ok"}


def test_extract_sources_reads_nested_news_payload_and_deduplicates() -> None:
    payload = {
        "success": True,
        "data": [
            {"publisher": "Reuters", "link": "https://example.test/reuters"},
            {"publisher": "Reuters", "link": "https://example.test/duplicate"},
            {"publisher": "NSE India", "link": "https://example.test/nse"},
        ],
    }

    assert _extract_sources(payload) == [
        {"name": "Reuters", "url": "https://example.test/reuters"},
        {"name": "NSE India", "url": "https://example.test/nse"},
    ]
