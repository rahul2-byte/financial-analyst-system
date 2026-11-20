"""Independent, dependency-light reference indicators and offline gold numbers.

``python -m evals.reference_indicators --write`` fills ``gold_numbers`` (flat
name -> value) and ``gold_number_specs`` (value, tolerance, snapshot id, as-of)
for answer cases of the real-v1 manifest from stored provider snapshots. It
never touches the network and only uses bars completed at or before each case's
as-of time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from statistics import fmean
from typing import Any


def sma(values: Sequence[float], period: int) -> float:
    if period < 1 or len(values) < period:
        raise ValueError("insufficient values for SMA")
    return fmean(values[-period:])


def rsi(values: Sequence[float], period: int = 14) -> float:
    if period < 1 or len(values) <= period:
        raise ValueError("insufficient values for RSI")
    changes = [current - previous for previous, current in pairwise(values)]
    gains = [max(change, 0.0) for change in changes[-period:]]
    losses = [max(-change, 0.0) for change in changes[-period:]]
    average_gain = fmean(gains)
    average_loss = fmean(losses)
    if average_loss == 0:
        return 100.0
    return 100 - (100 / (1 + average_gain / average_loss))


def macd(
    values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[float, float, float]:
    if min(fast, slow, signal) < 1 or len(values) < slow + signal:
        raise ValueError("insufficient values for MACD")

    def ema(series: Sequence[float], period: int) -> list[float]:
        multiplier = 2 / (period + 1)
        result = [fmean(series[:period])]
        for value in series[period:]:
            result.append((value - result[-1]) * multiplier + result[-1])
        return result

    fast_values = ema(values, fast)
    slow_values = ema(values, slow)
    offset = slow - fast
    line = [
        fast_values[index + offset] - slow_value
        for index, slow_value in enumerate(slow_values)
    ]
    signal_values = ema(line, signal)
    macd_value = line[-1]
    signal_value = signal_values[-1]
    return macd_value, signal_value, macd_value - signal_value


# ---------------------------------------------------------------------------
# Gold-number generation from stored provider snapshots (offline, no network).
# ---------------------------------------------------------------------------

GOLD_VERSION = "ref-indicators-v1"
DEFAULT_CASES = Path(__file__).parent / "gold" / "real-v1" / "cases.jsonl"
DEFAULT_ARCHIVE = Path(".finai") / "provider-snapshots"
_TRADING_DAYS_52W = 252

#: Gold numbers per case category. Evidence-gap categories deliberately get none.
CATEGORY_NUMBERS: dict[str, tuple[str, ...]] = {
    "price": (
        "close",
        "previous_close",
        "day_change_pct",
        "sma_20",
        "ema_20",
        "rsi_14",
    ),
    "range": ("high", "low", "high_52w", "low_52w"),
    "volume": ("volume", "avg_volume_20"),
    "grounding_check": ("close", "high", "low", "volume", "sma_20", "rsi_14", "macd"),
}


def ema(values: Sequence[float], period: int) -> float:
    """EMA seeded with the SMA of the first ``period`` values (TA-Lib convention)."""
    if period < 1 or len(values) < period:
        raise ValueError("insufficient values for EMA")
    multiplier = 2 / (period + 1)
    current = fmean(values[:period])
    for value in values[period:]:
        current = (value - current) * multiplier + current
    return current


def rsi_wilder(values: Sequence[float], period: int = 14) -> float:
    """Wilder-smoothed RSI (matches TA-Lib and the production engine)."""
    if period < 1 or len(values) <= period:
        raise ValueError("insufficient values for RSI")
    changes = [b - a for a, b in pairwise(values)]
    gain = fmean(max(c, 0.0) for c in changes[:period])
    loss = fmean(max(-c, 0.0) for c in changes[:period])
    for change in changes[period:]:
        gain = (gain * (period - 1) + max(change, 0.0)) / period
        loss = (loss * (period - 1) + max(-change, 0.0)) / period
    if loss == 0:
        return 100.0
    return 100 - 100 / (1 + gain / loss)


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def bars_from_payload(payload: dict[str, Any]) -> list[Bar]:
    """Parse a stored price payload into ascending, de-duplicated daily bars."""
    by_time: dict[datetime, Bar] = {}
    for row in payload.get("data") or []:
        stamp = datetime.fromisoformat(str(row["timestamp"]))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        values = [float(row[k]) for k in ("open", "high", "low", "close")]
        volume = float(row.get("volume") or 0.0)
        if not all(math.isfinite(v) for v in [*values, volume]) or values[3] <= 0:
            continue
        by_time[stamp] = Bar(stamp, values[0], values[1], values[2], values[3], volume)
    return [by_time[key] for key in sorted(by_time)]


def bars_as_of(bars: Sequence[Bar], as_of: datetime) -> list[Bar]:
    """Completed daily bars only: a bar is usable once its full day has elapsed."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    return [bar for bar in bars if bar.timestamp + timedelta(days=1) <= as_of]


def _tolerance(name: str) -> tuple[float, float]:
    """Return (relative, absolute floor) tolerance for a gold number."""
    if name in {"volume", "avg_volume_20"}:
        return 0.005, 1.0
    if name.endswith("_pct"):
        return 0.0, 0.05
    if name.startswith(("rsi", "macd")):
        return 0.01, 0.05
    return 0.005, 0.01


def compute_values(bars: Sequence[Bar]) -> dict[str, float]:
    """Every reference number the bars support; unsupported ones are omitted."""
    closes = [bar.close for bar in bars]
    values: dict[str, float] = {}
    if not bars:
        return values
    last = bars[-1]
    values.update(close=last.close, high=last.high, low=last.low, volume=last.volume)
    if len(bars) >= 2:
        values["previous_close"] = closes[-2]
        values["day_change_pct"] = (closes[-1] / closes[-2] - 1) * 100
    if len(bars) >= _TRADING_DAYS_52W // 2:
        window = bars[-_TRADING_DAYS_52W:]
        values["high_52w"] = max(bar.high for bar in window)
        values["low_52w"] = min(bar.low for bar in window)
    if len(bars) >= 20:
        values["sma_20"] = sma(closes, 20)
        values["ema_20"] = ema(closes, 20)
        values["avg_volume_20"] = fmean(bar.volume for bar in bars[-20:])
    if len(bars) >= 50:
        values["sma_50"] = sma(closes, 50)
    if len(bars) > 14:
        values["rsi_14"] = rsi_wilder(closes, 14)
    if len(bars) >= 35:
        line, signal_value, hist = macd(closes)
        values.update(macd=line, macd_signal=signal_value, macd_hist=hist)
    return values


def gold_number_specs(
    bars: Sequence[Bar],
    *,
    snapshot_id: str,
    as_of: datetime,
    names: Sequence[str],
) -> dict[str, dict[str, Any]]:
    """Gold specs using only bars completed at or before ``as_of`` (no lookahead)."""
    usable = bars_as_of(bars, as_of)
    values = compute_values(usable)
    specs: dict[str, dict[str, Any]] = {}
    for name in names:
        if name not in values:
            continue
        rel, floor = _tolerance(name)
        specs[name] = {
            "value": round(values[name], 6),
            "tolerance_rel": rel,
            "tolerance_abs": floor,
            "snapshot_id": snapshot_id,
            "as_of": as_of.astimezone(UTC).isoformat(),
            "last_bar": usable[-1].timestamp.isoformat(),
            "rows_used": len(usable),
            "method": GOLD_VERSION,
        }
    return specs


def load_snapshot_payload(archive_root: Path, snapshot_id: str) -> dict[str, Any]:
    """Load one archived snapshot and verify its canonical content hash."""
    path = archive_root / snapshot_id[:2] / f"{snapshot_id}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    body = {key: value for key, value in record.items() if key != "content_hash"}
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != snapshot_id or record.get("content_hash") != snapshot_id:
        raise ValueError(f"snapshot content hash mismatch: {snapshot_id}")
    payload = record.get("payload")
    if not isinstance(payload, dict):
        msg = f"snapshot payload is not an object: {snapshot_id}"
        raise TypeError(msg)
    return payload


def populate_case(case: dict[str, Any], archive_root: Path) -> dict[str, Any]:
    """Return a copy of ``case`` with gold_numbers/gold_number_specs filled."""
    updated = dict(case)
    names = CATEGORY_NUMBERS.get(str(case.get("category")), ())
    if case.get("expected_outcome") != "answer" or not names:
        updated["gold_numbers"] = {}
        updated.pop("gold_number_specs", None)
        return updated
    snapshot_id = str(case["snapshot_id"])
    bars = bars_from_payload(load_snapshot_payload(archive_root, snapshot_id))
    as_of = datetime.fromisoformat(str(case["retrieved_at"]))
    specs = gold_number_specs(bars, snapshot_id=snapshot_id, as_of=as_of, names=names)
    updated["gold_numbers"] = {name: spec["value"] for name, spec in specs.items()}
    updated["gold_number_specs"] = specs
    return updated


def populate_cases(
    cases: Sequence[dict[str, Any]], archive_root: Path
) -> list[dict[str, Any]]:
    return [populate_case(case, archive_root) for case in cases]


def _read_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _dump_cases(cases: Sequence[dict[str, Any]]) -> str:
    return "".join(json.dumps(case, sort_keys=True) + "\n" for case in cases)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute offline gold numbers.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--write", action="store_true", help="rewrite the cases file")
    args = parser.parse_args(argv)
    updated = populate_cases(_read_cases(args.cases), args.archive)
    filled = sum(1 for case in updated if case["gold_numbers"])
    print(f"{filled}/{len(updated)} cases have gold numbers")
    rendered = _dump_cases(updated)
    if args.write:
        args.cases.write_text(rendered, encoding="utf-8")
        return 0
    if rendered != args.cases.read_text(encoding="utf-8"):
        print("gold numbers are stale; rerun with --write")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
