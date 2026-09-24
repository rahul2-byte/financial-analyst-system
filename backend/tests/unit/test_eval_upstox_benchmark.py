import gzip
import json
from datetime import UTC, datetime

import httpx
import pytest
from app.observability.provider_archive import ProviderArchive, ProviderSnapshot

from evals.upstox_benchmark import (
    build_cases,
    parse_nse_equities,
    score_artifacts,
    select_instruments,
    validate_archive_cases,
    validate_cases,
)


def test_parse_nse_equities_keeps_only_unique_nse_cash_equities():
    payload = [
        {
            "segment": "NSE_EQ",
            "instrument_type": "EQ",
            "instrument_key": "NSE_EQ|ISIN1",
            "trading_symbol": "AAA",
        },
        {
            "segment": "NSE_EQ",
            "instrument_type": "EQ",
            "instrument_key": "NSE_EQ|ISIN1",
            "trading_symbol": "AAA",
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "FUT",
            "instrument_key": "NSE_FO|1",
            "trading_symbol": "AAA FUT",
        },
    ]

    parsed = parse_nse_equities(gzip.compress(json.dumps(payload).encode()))

    assert parsed == [payload[0]]


def test_instrument_sample_is_stable_and_has_unique_keys():
    instruments = [
        {
            "segment": "NSE_EQ",
            "instrument_type": "EQ",
            "instrument_key": f"NSE_EQ|{index:03}",
            "trading_symbol": f"SYM{index}",
        }
        for index in range(20)
    ]

    first = select_instruments(instruments, count=10, seed=7)

    assert first == select_instruments(instruments, count=10, seed=7)
    assert len({item["instrument_key"] for item in first}) == 10


def test_instrument_sample_rejects_a_short_universe():
    with pytest.raises(ValueError, match="only 2 unique instruments"):
        select_instruments(
            [
                {"instrument_key": "NSE_EQ|A"},
                {"instrument_key": "NSE_EQ|A"},
                {"instrument_key": "NSE_EQ|B"},
            ],
            count=3,
            seed=1,
        )


def test_instrument_master_http_errors_remain_provider_errors(monkeypatch):
    from evals.upstox_benchmark import collect_instrument_master

    def fail_request(*args, **kwargs):
        raise httpx.ConnectError("network unavailable")

    monkeypatch.setattr(httpx, "get", fail_request)
    with pytest.raises(httpx.HTTPError, match="network unavailable"):
        collect_instrument_master("https://example.invalid/instruments.json.gz")


def test_validate_cases_rejects_duplicate_instrument_and_missing_gold():
    cases = [
        {
            "case_id": "case-1",
            "instrument_key": "NSE_EQ|ONE",
            "query": "Latest close?",
            "snapshot_id": "a" * 64,
            "source_url": "https://api.upstox.com",
            "retrieved_at": "2026-09-23T00:00:00Z",
            "usage_permission": "approved",
            "permission_basis": "local evaluation",
            "expected_outcome": "answer",
            "gold_numbers": {"close": 12.5},
        },
        {
            "case_id": "case-2",
            "instrument_key": "NSE_EQ|ONE",
            "query": "Latest close?",
            "snapshot_id": "b" * 64,
            "source_url": "https://api.upstox.com",
            "retrieved_at": "2026-09-23T00:00:00Z",
            "usage_permission": "approved",
            "permission_basis": "local evaluation",
            "expected_outcome": "answer",
            "gold_numbers": {},
        },
    ]

    errors = validate_cases(cases, expected_count=2)

    assert any("instrument_key must be unique" in error for error in errors)
    assert any("answer case requires gold_numbers" in error for error in errors)


def test_build_cases_uses_distinct_snapshot_and_close_gold(tmp_path):
    instruments = [
        {"instrument_key": f"NSE_EQ|{index}", "trading_symbol": f"S{index}"}
        for index in range(2)
    ]
    cases = build_cases(
        instruments,
        {
            item["instrument_key"]: [
                {
                    "timestamp": "2026-09-22T00:00:00+05:30",
                    "close": 100.0 + index,
                }
            ]
            for index, item in enumerate(instruments)
        },
        trading_date="2026-09-22",
        source_url="https://api.upstox.com/v3/historical-candle/",
        permission_basis="Upstox account; local evaluation only",
        retrieved_at=datetime(2026, 9, 23, tzinfo=UTC),
    )

    assert len(cases) == 2
    assert len({case["instrument_key"] for case in cases}) == 2
    assert cases[0]["gold_numbers"]["close"] == 100.0

    archive = ProviderArchive(tmp_path)
    master_snapshot = archive.store(
        ProviderSnapshot(
            provider="upstox",
            operation="instrument_master",
            payload={
                "provider": "upstox",
                "operation": "instrument_master",
                "selected_instruments": instruments,
            },
            fetched_at=datetime(2026, 9, 23, tzinfo=UTC),
        )
    )
    for case in cases:
        snapshot = archive.store(
            ProviderSnapshot(
                provider="upstox",
                operation="historical_candle",
                payload=case["snapshot"],
                fetched_at=datetime(2026, 9, 23, tzinfo=UTC),
            )
        )
        case["snapshot_id"] = snapshot.content_hash
        case["content_sha256"] = snapshot.content_hash
        case["instrument_master_snapshot_id"] = master_snapshot.content_hash
        case.pop("snapshot")

    assert archive.load(cases[0]["snapshot_id"]).payload["instrument_key"] == "NSE_EQ|0"
    assert validate_archive_cases(cases, tmp_path) == []
    cases[0]["gold_numbers"]["close"] = 999
    assert any(
        "does not match archived snapshot" in error
        for error in validate_archive_cases(cases, tmp_path)
    )


def test_build_cases_labels_missing_requested_date_as_evidence_gap():
    cases = build_cases(
        [{"instrument_key": "NSE_EQ|1", "trading_symbol": "ONE"}],
        {"NSE_EQ|1": [{"timestamp": "2026-09-21T00:00:00+05:30", "close": 10}]},
        trading_date="2026-09-22",
        source_url="https://api.upstox.com/v3/historical-candle/",
        permission_basis="local evaluation",
        retrieved_at=datetime(2026, 9, 23, tzinfo=UTC),
    )

    assert cases[0]["expected_outcome"] == "evidence_gap"
    assert cases[0]["gold_numbers"] == {}
    assert cases[0]["frozen_candle"] is None


def test_score_artifacts_requires_published_close_and_matching_timestamp_facts():
    case = {
        "case_id": "case-1",
        "trading_date": "2026-09-22",
        "expected_outcome": "answer",
        "gold_numbers": {"close": 8.25},
        "frozen_candle": {
            "timestamp": "2026-09-22T00:00:00+05:30",
            "close": 8.25,
        },
    }
    close_id = "upstox_historical_candle:data.first.close"
    timestamp_id = "upstox_historical_candle:data.first.timestamp"
    good = {
        "case_id": "case-1",
        "terminal_status": "completed",
        "report_validation": {"publication_status": "passed"},
        "citations": [{"citation_id": "src", "source_id": "upstox_historical_candle"}],
        "claims": [
            {
                "importance": "major",
                "evidence_refs": ["src"],
                "numeric_refs": [close_id, timestamp_id],
                "text": f"Close [[fact:{close_id}]] on [[fact:{timestamp_id}]].",
            }
        ],
    }

    score = score_artifacts([case], [good])

    assert score["deterministic_checks_passed"] is True
    assert score["status"] == "pending_semantic_judge"
    assert score["semantic_judge_required"] is True
    bad = {**good, "claims": []}
    failed = score_artifacts([case], [bad])
    assert failed["deterministic_checks_passed"] is False
    assert failed["status"] == "deterministic_checks_failed"
    assert "expected_close_and_timestamp_not_bound_in_major_claim" in failed["cases"][0]["issues"]


def test_score_artifacts_accepts_close_and_timestamp_across_cited_major_claims():
    case = {
        "case_id": "case-1",
        "trading_date": "2026-09-22",
        "expected_outcome": "answer",
        "gold_numbers": {"close": 8.25},
        "frozen_candle": {
            "timestamp": "2026-09-22T00:00:00+05:30",
            "close": 8.25,
        },
    }
    close_id = "upstox_historical_candle:data.first.close"
    timestamp_id = "upstox_historical_candle:data.first.timestamp"
    artifact = {
        "case_id": "case-1",
        "terminal_status": "completed",
        "report_validation": {"publication_status": "passed"},
        "citations": [{"citation_id": "src", "source_id": "upstox_historical_candle"}],
        "claims": [
            {
                "importance": "major",
                "evidence_refs": ["src"],
                "numeric_refs": [timestamp_id],
                "text": f"Observed on [[fact:{timestamp_id}]].",
            },
            {
                "importance": "major",
                "evidence_refs": ["src"],
                "numeric_refs": [close_id],
                "text": f"Close [[fact:{close_id}]].",
            },
        ],
    }

    score = score_artifacts([case], [artifact])

    assert score["deterministic_checks_passed"] is True


def test_score_artifacts_accepts_expected_no_candle_abstention():
    case = {
        "case_id": "gap-1",
        "trading_date": "2026-09-22",
        "expected_outcome": "evidence_gap",
        "gold_numbers": {},
        "frozen_candle": None,
    }
    artifact = {
        "case_id": "gap-1",
        "terminal_status": "completed_with_limited_evidence",
        "report_validation": {"publication_status": "pending"},
        "claims": [],
    }

    score = score_artifacts([case], [artifact])

    assert score["deterministic_checks_passed"] is True
    assert score["cases"][0]["status"] == "expected_evidence_gap"
