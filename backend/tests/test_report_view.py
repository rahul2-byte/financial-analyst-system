"""ReportView builder: refs map to source numbers, missing data fails closed."""

from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest
from finai.bridge import protocol as p
from finai.bridge.fake_report import KINDS, fake_material
from finai.report_view import (
    MAX_SPARK_POINTS,
    build_report_view,
    evidence_availability,
)

RAW_ID = re.compile(r"\b[a-z_]+:[a-z0-9_]+\b")
FACT_MARKER = re.compile(r"\[\[fact:")


def _dump(view: p.ReportView) -> str:
    return json.dumps(view.model_dump(mode="json"), ensure_ascii=False)


def test_full_view_blocks_and_source_numbers() -> None:
    view = build_report_view(fake_material("full"))
    assert view is not None and view.kind == "report"
    assert [s.ref for s in view.sources] == [1, 2, 3]
    assert view.instrument is not None and view.instrument.symbol == "HDFCBANK"
    assert view.quote is not None and view.quote.direction == "up"
    assert view.sparkline is not None
    assert view.evidence.status == "complete"
    assert [d.importance for d in view.drivers] == [
        "major",
        "major",
        "supporting",
        "minor",
    ]
    # claim evidence_refs (c2 -> fundamentals) become source number 2
    assert view.drivers[0].source_refs == [2]
    assert view.drivers[2].source_refs == [1]
    assert view.signals and view.signals[0].name == "RSI (14)"
    assert view.signals[0].percentile_text == "93rd pct"
    assert all(f.source_ref in {1, 2} for f in view.key_figures)


def test_no_markers_or_raw_ids_leak_into_text() -> None:
    for kind in KINDS:
        view = build_report_view(fake_material(kind))
        assert view is not None
        text = _dump(view)
        assert not FACT_MARKER.search(text)
        for field in (
            view.summary,
            view.final_view or "",
            view.detailed_analysis or "",
        ):
            assert not RAW_ID.search(field), field


def test_partial_view_reports_unavailable_news() -> None:
    view = build_report_view(fake_material("partial"))
    assert view is not None
    assert view.evidence.status == "limited"
    news = next(s for s in view.evidence.sources if s.name == "News")
    assert news.status == "unavailable" and news.reason == "news provider timed out"
    assert any("News unavailable" in line for line in view.limitations)
    assert [s.ref for s in view.sources] == [1, 2]


def test_lookup_view_has_no_report_only_blocks() -> None:
    view = build_report_view(fake_material("lookup"))
    assert view is not None and view.kind == "lookup"
    assert view.signals == [] and view.drivers == [] and view.risks == []
    assert view.final_view is None and view.detailed_analysis is None


def test_sparkline_is_normalised_and_capped() -> None:
    view = build_report_view(fake_material("full"))
    assert view is not None and view.sparkline is not None
    points = view.sparkline.points
    assert len(points) == MAX_SPARK_POINTS
    assert min(points) == 0.0 and max(points) == 1.0
    assert view.sparkline.period_text == "1y"


def test_missing_price_and_technical_data_become_null_blocks() -> None:
    material = fake_material("full")
    material["ohlcv"] = None
    material["technical"] = None
    view = build_report_view(material)
    assert view is not None
    assert view.sparkline is None and view.quote is None and view.signals == []


def test_price_series_for_another_ticker_is_ignored() -> None:
    material = fake_material("full")
    key, rows = material["ohlcv"]
    material["ohlcv"] = (("TCS.NS", key[1], key[2]), rows)
    material["technical"] = {**material["technical"], "ticker": "TCS.NS"}
    view = build_report_view(material)
    assert view is not None
    assert view.sparkline is None and view.quote is None and view.signals == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m["result"].update(publication_status="failed"),
        lambda m: m["result"].update(draft=None),
        lambda m: m["facts"].clear(),  # markers can no longer be resolved
    ],
)
def test_invalid_material_fails_closed(mutate) -> None:  # type: ignore[no-untyped-def]
    material = deepcopy(fake_material("full"))
    mutate(material)
    assert build_report_view(material) is None


def test_none_material_is_none() -> None:
    assert build_report_view(None) is None


def test_terminal_escapes_are_sanitised() -> None:
    material = fake_material("full")
    material["result"]["draft"]["final_view"] = "Hold\x1b[31m red\x1b[0m"
    view = build_report_view(material)
    assert view is not None and "\x1b" not in (view.final_view or "")


def test_evidence_availability_friendly_names() -> None:
    rows = evidence_availability(
        [
            {"source": "news", "status": "unavailable", "reason": "timed out"},
            {"source": "market_data", "status": "available"},
        ]
    )
    assert rows is not None
    assert [(r.name, r.status) for r in rows] == [
        ("News", "unavailable"),
        ("Price history", "available"),
    ]
    assert evidence_availability([]) is None


@pytest.mark.parametrize(
    ("engine_direction", "state", "expected"),
    [
        ("bullish", "overbought", "bearish"),  # real engine: RSI 74 is above centre 50
        ("bearish", "oversold", "bullish"),
        ("bullish", "range", "bullish"),
    ],
)
def test_rsi_extremes_read_as_caution_not_trend(
    engine_direction: str, state: str, expected: str
) -> None:
    material = fake_material("full")
    rsi = next(
        m for m in material["technical"]["measurements"] if m["indicator"] == "RSI_14"
    )
    rsi.update(direction=engine_direction, state=state)
    view = build_report_view(material)
    assert view is not None
    assert view.signals[0].name == "RSI (14)"
    assert view.signals[0].direction == expected
    assert view.signals[0].state_text == state
