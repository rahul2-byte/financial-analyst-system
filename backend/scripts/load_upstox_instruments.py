from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from storage.sql.client import PostgresClient


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y"):
        try:
            return datetime.strptime(candidate, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _normalize_segment(raw: str) -> str:
    value = (raw or "").upper()
    if "FUT" in value:
        return "FUT"
    if "OPT" in value:
        return "OPT"
    return "EQ"


def _normalize_instrument_type(segment: str, option_type: str | None) -> str:
    if segment == "FUT":
        return "future"
    if segment == "OPT":
        option = (option_type or "").upper()
        if option in {"CE", "CALL"}:
            return "call_option"
        if option in {"PE", "PUT"}:
            return "put_option"
        return "option"
    return "equity"


def _normalize_row(
    row: dict[str, str], snapshot_id: str, as_of_date: datetime | None
) -> dict[str, Any] | None:
    symbol = (
        (
            row.get("trading_symbol")
            or row.get("tradingsymbol")
            or row.get("symbol")
            or ""
        )
        .strip()
        .upper()
    )
    exchange = (
        (row.get("exchange") or row.get("exchange_segment") or "NSE").strip().upper()
    )
    segment = _normalize_segment(
        row.get("segment") or row.get("instrument_type") or "EQ"
    )
    instrument_key = (
        row.get("instrument_key")
        or row.get("instrument_token")
        or f"{exchange}:{symbol}"
    ).strip()
    if not instrument_key or not symbol:
        return None

    option_type = (
        row.get("option_type") or row.get("optiontype") or ""
    ).strip().upper() or None
    normalized = {
        "instrument_key": instrument_key,
        "exchange": exchange,
        "segment": segment,
        "trading_symbol": symbol,
        "underlying_symbol": (
            row.get("underlying_symbol") or row.get("underlying") or ""
        )
        .strip()
        .upper()
        or None,
        "company_name": (row.get("company_name") or row.get("name") or "").strip()
        or None,
        "sector": (row.get("sector") or "").strip() or None,
        "industry": (row.get("industry") or "").strip() or None,
        "instrument_type": _normalize_instrument_type(segment, option_type),
        "expiry": _parse_datetime(row.get("expiry") or row.get("expiry_date")),
        "strike": _parse_float(row.get("strike") or row.get("strike_price")),
        "option_type": option_type,
        "lot_size": _parse_int(row.get("lot_size") or row.get("lotsize")),
        "tick_size": _parse_float(row.get("tick_size") or row.get("ticksize")),
        "is_active": True,
        "as_of_date": as_of_date,
        "source_snapshot_id": snapshot_id,
    }
    return normalized


def load_upstox_csv(
    csv_path: Path,
    snapshot_id: str,
    as_of_date: datetime | None,
    batch_size: int = 2000,
) -> dict[str, int]:
    client = PostgresClient()
    buffer: list[dict[str, Any]] = []
    inserted = 0
    rejected = 0

    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            normalized = _normalize_row(
                row, snapshot_id=snapshot_id, as_of_date=as_of_date
            )
            if normalized is None:
                rejected += 1
                continue
            buffer.append(normalized)
            if len(buffer) >= batch_size:
                inserted += client.bulk_upsert_instruments(buffer)[
                    "inserted_or_updated"
                ]
                buffer.clear()

    if buffer:
        inserted += client.bulk_upsert_instruments(buffer)["inserted_or_updated"]

    return {"inserted_or_updated": inserted, "rejected": rejected}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load Upstox instrument CSV into instrument_master table."
    )
    parser.add_argument("--csv", required=True, help="Path to Upstox instruments CSV")
    parser.add_argument(
        "--snapshot-id",
        required=True,
        help="Snapshot identifier (e.g. upstox_2026_04_02)",
    )
    parser.add_argument(
        "--as-of-date", default="", help="Optional as-of date (YYYY-MM-DD)"
    )
    parser.add_argument("--batch-size", type=int, default=2000)
    args = parser.parse_args()

    csv_path = Path(args.csv).expanduser().resolve()
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    as_of_date = _parse_datetime(args.as_of_date)
    summary = load_upstox_csv(
        csv_path=csv_path,
        snapshot_id=args.snapshot_id,
        as_of_date=as_of_date,
        batch_size=args.batch_size,
    )
    print(summary)


if __name__ == "__main__":
    main()
