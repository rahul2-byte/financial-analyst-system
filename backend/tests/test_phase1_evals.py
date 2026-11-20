"""Phase 1 evals: offline gold numbers and numeric grounding score."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
import talib

from evals.grounding import grounding_report, score_answer
from evals.reference_indicators import (
    Bar,
    bars_as_of,
    bars_from_payload,
    compute_values,
    gold_number_specs,
    populate_case,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def _bars(count: int, last_close: float | None = None) -> list[Bar]:
    rows = []
    for i in range(count):
        close = 100.0 + i + (3.0 if i % 3 == 0 else 0.0) - (2.0 if i % 5 == 0 else 0.0)
        if last_close is not None and i == count - 1:
            close = last_close
        rows.append(
            Bar(
                START + timedelta(days=i),
                close,
                close + 2,
                close - 2,
                close,
                1000.0 + i,
            )
        )
    return rows


def _as_of(count: int) -> datetime:
    return START + timedelta(days=count + 1)


def test_gold_numbers_are_deterministic_and_match_talib() -> None:
    bars = _bars(60)
    first = compute_values(bars)
    assert first == compute_values(bars)
    closes = np.array([bar.close for bar in bars])
    assert first["rsi_14"] == pytest.approx(talib.RSI(closes, 14)[-1])
    assert first["sma_20"] == pytest.approx(talib.SMA(closes, 20)[-1])
    assert first["ema_20"] == pytest.approx(talib.EMA(closes, 20)[-1])
    assert first["macd"] == pytest.approx(
        talib.MACD(closes, 12, 26, 9)[0][-1], rel=1e-3
    )  # talib seeds short series differently
    assert first["close"] == bars[-1].close
    assert first["previous_close"] == bars[-2].close


def test_short_history_omits_unsupported_numbers() -> None:
    values = compute_values(_bars(10))
    assert "close" in values and "rsi_14" not in values and "sma_20" not in values


def test_future_rows_do_not_change_gold_numbers() -> None:
    bars = _bars(60)
    as_of = _as_of(60)
    names = ["close", "sma_20", "rsi_14", "macd"]
    baseline = gold_number_specs(bars, snapshot_id="s", as_of=as_of, names=names)
    future = Bar(START + timedelta(days=61), 900.0, 950.0, 10.0, 900.0, 1.0)
    with_future = gold_number_specs(
        [*bars, future], snapshot_id="s", as_of=as_of, names=names
    )
    assert baseline == with_future
    assert baseline["close"]["value"] == bars[-1].close
    assert baseline["close"]["snapshot_id"] == "s"
    assert baseline["close"]["as_of"] == as_of.isoformat()
    # An incomplete same-day bar is also excluded.
    same_day = [*bars, Bar(as_of - timedelta(hours=1), 5.0, 5.0, 5.0, 5.0, 1.0)]
    assert bars_as_of(same_day, as_of)[-1] == bars[-1]


def test_populate_case_from_archive(tmp_path: Path) -> None:
    import hashlib

    rows = [
        {
            "timestamp": bar.timestamp.isoformat(),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in reversed(_bars(60))  # provider order is newest first
    ]
    record = {
        "provider": "upstox",
        "operation": "fetch_stock_price",
        "payload": {"data": rows},
    }
    digest = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path = tmp_path / digest[:2] / f"{digest}.json"
    path.parent.mkdir()
    path.write_text(json.dumps({**record, "content_hash": digest}))
    case = {
        "id": "c1",
        "category": "price",
        "expected_outcome": "answer",
        "snapshot_id": digest,
        "retrieved_at": _as_of(60).isoformat(),
        "gold_numbers": {},
    }
    filled = populate_case(case, tmp_path)
    assert filled["gold_numbers"]["close"] == _bars(60)[-1].close
    assert populate_case(filled, tmp_path) == filled  # idempotent
    assert len(bars_from_payload({"data": rows})) == 60
    gap = populate_case(
        {**case, "expected_outcome": "evidence_gap", "category": "evidence_gap"},
        tmp_path,
    )
    assert gap["gold_numbers"] == {}


def test_grounding_matched_contradicted_unverifiable() -> None:
    gold = {"close": 399.75, "volume": 72761.0, "rsi_14": 53.2}
    answer = (
        "The closing price was ₹399.75. Volume was 90,000 shares. "
        "RSI is 53.19. P/E is 31.4."
    )
    result = score_answer(answer, gold)
    assert [m["gold"] for m in result["matched"]] == ["close", "rsi_14"]
    assert [c["gold"] for c in result["contradicted"]] == ["volume"]
    assert [u["value"] for u in result["unverifiable"]] == [31.4]
    assert result["score"] == pytest.approx(2 / 4)
    assert result["has_contradiction"]


def test_grounding_ignores_dates_and_empty_answers() -> None:
    result = score_answer("As of 2026-09-18 the price is 399.75.", {"close": 399.75})
    assert result["claims"] == 1 and result["score"] == 1.0
    assert score_answer("No numbers here.", {"close": 1.0})["score"] is None


def test_grounding_uses_evidence_facts_and_specs() -> None:
    result = score_answer(
        "Revenue was 500 and close 100.4.",
        {"close": 100.0},
        gold_number_specs={"close": {"tolerance_rel": 0.01, "tolerance_abs": 0.0}},
        evidence_facts={"revenue": 500},
    )
    assert len(result["matched"]) == 2 and not result["contradicted"]


def test_grounding_report_scores_alongside_terminal_success() -> None:
    cases = [
        {"id": "a", "gold_numbers": {"close": 10.0}},
        {"id": "b", "gold_numbers": {"close": 10.0}},
        {"id": "c", "gold_numbers": {}},
    ]
    results = {
        "a": {"terminal_status": "success", "report": "Close 10.00"},
        "b": {"terminal_status": "success", "report": "Close 12.00"},
        "c": {"terminal_status": "failed", "report": "nothing"},
    }
    report = grounding_report(cases, results)
    assert report["terminal_success"]["success"] == 2
    assert report["grounding"]["cases_scored"] == 2
    assert report["grounding"]["cases_not_scored"] == 1
    assert report["grounding"]["contradicted"] == 1
    assert report["grounding"]["claim_score"] == pytest.approx(0.5)


def test_real_v1_manifest_gold_numbers_are_populated() -> None:
    cases = [
        json.loads(line)
        for line in Path("evals/gold/real-v1/cases.jsonl").read_text().splitlines()
        if line.strip()
    ]
    with_gold = [case for case in cases if case["gold_numbers"]]
    assert len(with_gold) == 87
    for case in with_gold:
        assert case["expected_outcome"] == "answer"
        for name, spec in case["gold_number_specs"].items():
            assert spec["value"] == case["gold_numbers"][name]
            assert spec["snapshot_id"] == case["snapshot_id"]
            assert spec["as_of"].startswith(case["retrieved_at"][:10])
    assert all(
        not c["gold_numbers"] for c in cases if c["expected_outcome"] != "answer"
    )
