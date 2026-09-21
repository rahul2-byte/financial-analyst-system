"""Small deterministic parser for evaluation-number normalization."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import TypedDict


class NormalizedNumber(TypedDict):
    value: Decimal
    unit: str
    currency: str | None
    original: str


_VALUE = re.compile(r"(?P<currency>₹|INR|USD|\$)?\s*(?P<number>[+-]?(?:\d[\d,]*|\d+\.\d+)(?:\.\d+)?)\s*(?P<suffix>lakh\s+crore|lakh|crore|million|billion|thousand)?\s*(?P<pct>%)?", re.IGNORECASE)
_MULTIPLIERS = {
    "thousand": Decimal(1000),
    "million": Decimal(1_000_000),
    "billion": Decimal(1_000_000_000),
    "lakh": Decimal(100_000),
    "crore": Decimal(10_000_000),
    "lakh crore": Decimal(1_000_000_000_000),
}


def parse_number(text: str) -> NormalizedNumber | None:
    match = _VALUE.fullmatch(text.strip())
    if not match:
        return None
    original = match.group(0)
    raw = match.group("number").replace(",", "")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    if value == value.to_integral() and 1900 <= value <= 2200 and not match.group("suffix"):
        return None
    suffix = (match.group("suffix") or "").lower()
    unit = "%" if match.group("pct") else suffix or "absolute"
    if suffix:
        value *= _MULTIPLIERS[suffix]
    currency = match.group("currency")
    if currency in {"₹", "INR"}:
        currency = "INR"
    elif currency in {"$", "USD"}:
        currency = "USD"
    return {"value": value, "unit": unit, "currency": currency, "original": original}


def within_tolerance(
    actual: NormalizedNumber | None,
    expected: NormalizedNumber | None,
    absolute_tolerance: Decimal,
    relative_tolerance: Decimal | None = None,
) -> bool:
    if actual is None or expected is None or actual["currency"] != expected["currency"]:
        return False
    difference = abs(actual["value"] - expected["value"])
    if difference <= absolute_tolerance:
        return True
    return relative_tolerance is not None and difference <= abs(expected["value"]) * relative_tolerance
