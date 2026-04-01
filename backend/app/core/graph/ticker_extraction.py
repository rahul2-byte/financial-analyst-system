from __future__ import annotations

import re


COMPANY_ALIAS_TO_TICKER = {
    "RELIANCE": "RELIANCE.NS",
    "APPLE": "AAPL",
    "MICROSOFT": "MSFT",
    "GOOGLE": "GOOGL",
    "ALPHABET": "GOOGL",
    "TESLA": "TSLA",
    "NVIDIA": "NVDA",
}

STOPWORDS = {
    "A",
    "AN",
    "AND",
    "ARE",
    "AS",
    "AT",
    "BUY",
    "FOR",
    "GOOD",
    "HOLD",
    "HOW",
    "I",
    "IN",
    "IS",
    "IT",
    "LONG",
    "MACRO",
    "NEXT",
    "NOW",
    "OF",
    "ON",
    "OR",
    "OVER",
    "QUARTER",
    "RESEARCH",
    "RISKS",
    "SELL",
    "SHOULD",
    "TERM",
    "THE",
    "TRADE",
    "WHAT",
    "YEARS",
}

SYMBOL_PATTERN = re.compile(r"\b[A-Z]{2,5}(?:\.[A-Z]{1,2})?\b")


def extract_ticker(user_query: str) -> str | None:
    upper_query = user_query.upper()

    for alias, ticker in COMPANY_ALIAS_TO_TICKER.items():
        if alias in upper_query:
            return ticker

    for symbol in SYMBOL_PATTERN.findall(upper_query):
        if symbol in STOPWORDS:
            continue
        return symbol

    return None
