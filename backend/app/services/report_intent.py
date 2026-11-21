"""Single source of truth for report-intent detection on a user query."""

from __future__ import annotations

import re

_FILLER_PREFIXES = (
    "i want you to ",
    "i'd like you to ",
    "i would like you to ",
    "please ",
    "can you ",
    "could you ",
    "would you ",
    "help me ",
)
_REPORT_VERBS = ("analyze ", "analyse ", "analsye ", "research ", "compare ")
_REPORT_MARKERS = ("report", "investment thesis", "full analysis", "detailed analysis")


# Single-stock investment questions that deserve a full report. Simple lookups
# (price, quote, market status, holidays) deliberately do not match.
_INVESTMENT_QUESTIONS = re.compile(
    r"\bis\b.+\b(?:a|an)\s+(?:good|bad|great|solid|safe|worthwhile)\s+"
    r"(?:buy|sell|investment|stock|hold|bet)\b"
    r"|\bis\b.+\bworth\s+(?:buying|investing)\b"
    r"|\bshould\s+i\s+(?:buy|sell|hold|invest\s+in|accumulate)\b"
    r"|\boutlook\s+(?:for|on|of)\b"
    r"|\bdeep[- ]dive\b"
    r"|\b(?:fundamental|technical)(?:\s+(?:and|&|plus)\s+(?:fundamental|technical))?"
    r"\s+analysis\b"
    r"|\binvestment\s+case\b"
    r"|\bvaluation\s+(?:of|for)\b"
    r"|\bvaluation\s*[?.!]*$"
    r"|\bstock\s+analysis\b"
)
_ACTION_CHOICE = re.compile(
    r"\b(?:buy|sell|hold)(?:,\s*(?:buy|sell|hold))?\s+or\s+(?:buy|sell|hold)\b"
)
_MULTI_INSTRUMENT = re.compile(r"\b(?:vs\.?|versus|or|better\s+than)\b")


def _strip_filler(query: str) -> str:
    lowered = query.casefold().strip()
    for prefix in _FILLER_PREFIXES:
        if lowered.startswith(prefix):
            return lowered[len(prefix) :].lstrip()
    return lowered


def wants_report(query: str) -> bool:
    """True when the query asks for a research report (comparisons included).

    Single-stock investment questions (is X a good buy, should I buy X, outlook,
    deep dive, fundamental/technical analysis, valuation) count as report asks.
    """
    lowered = _strip_filler(query)
    if lowered.startswith(_REPORT_VERBS) or any(
        marker in lowered for marker in _REPORT_MARKERS
    ):
        return True
    return bool(
        _INVESTMENT_QUESTIONS.search(lowered)
        and not _MULTI_INSTRUMENT.search(_ACTION_CHOICE.sub("", lowered))
    )


def is_comparison(query: str) -> bool:
    """True when the query compares instruments."""
    return "compare" in _strip_filler(query)
