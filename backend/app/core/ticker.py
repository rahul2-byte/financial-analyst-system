from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, cast

KNOWN_EXCHANGE_SUFFIXES = (".NS", ".BO")
TickerExchangeSuffix = Literal[".NS", ".BO"]
YFINANCE_PAIR_QUOTE_LEGS = frozenset(
    {"USD", "USDT", "INR", "EUR", "GBP", "JPY", "BTC", "ETH"}
)

_VALID_TICKER_RE = re.compile(r"^[A-Z0-9.\-^=]+$")
_HAS_ALNUM_RE = re.compile(r"[A-Z0-9]")
_VALID_DEFAULT_SUFFIX_RE = re.compile(r"^\.[A-Z0-9]+$")


@dataclass(frozen=True, slots=True)
class Ticker:
    canonical: str
    exchange_suffix: TickerExchangeSuffix | None = None

    def __post_init__(self) -> None:
        canonical = self.canonical.strip().upper()
        _validate_ticker_value(canonical)
        if (
            self.exchange_suffix is not None
            and self.exchange_suffix not in KNOWN_EXCHANGE_SUFFIXES
        ):
            raise ValueError("Unsupported exchange suffix")

        object.__setattr__(self, "canonical", canonical)

    @property
    def db_lookup_variants(self) -> tuple[str, ...]:
        variants = (self.canonical, f"{self.canonical}.NS", f"{self.canonical}.BO")
        return tuple(dict.fromkeys(variants))

    @property
    def cache_key(self) -> str:
        return self.canonical

    @property
    def provider_symbol(self) -> str:
        if self.exchange_suffix is not None:
            return f"{self.canonical}{self.exchange_suffix}"
        return self.canonical

    def provider_format_yfinance(
        self,
        default_exchange_suffix: str | None = None,
    ) -> str:
        if self.exchange_suffix is not None:
            return self.provider_symbol

        if default_exchange_suffix is not None and not _is_yfinance_provider_symbol(
            self.canonical
        ):
            suffix = _normalize_default_suffix(default_exchange_suffix)
            return f"{self.canonical}{suffix}"

        return self.canonical

    def __str__(self) -> str:
        return self.canonical


def parse_ticker(raw: str | Ticker) -> Ticker:
    if isinstance(raw, Ticker):
        return raw

    value = raw.strip().upper()
    _validate_ticker_value(value)

    exchange_suffix: TickerExchangeSuffix | None = None
    canonical = value
    for suffix in KNOWN_EXCHANGE_SUFFIXES:
        if value.endswith(suffix):
            exchange_suffix = cast(TickerExchangeSuffix, suffix)
            canonical = value[: -len(suffix)]
            _validate_ticker_value(canonical)
            break

    return Ticker(canonical=canonical, exchange_suffix=exchange_suffix)


def _validate_ticker_value(value: str) -> None:
    if not value:
        raise ValueError("Ticker is required")
    if not _VALID_TICKER_RE.fullmatch(value) or not _HAS_ALNUM_RE.search(value):
        raise ValueError("Invalid ticker format")


def _is_yfinance_provider_symbol(canonical: str) -> bool:
    if canonical.startswith("^") or "=" in canonical or "." in canonical:
        return True

    if "-" in canonical:
        quote_leg = canonical.rsplit("-", maxsplit=1)[-1]
        return quote_leg in YFINANCE_PAIR_QUOTE_LEGS

    return False


def _normalize_default_suffix(default_exchange_suffix: str) -> str:
    suffix = default_exchange_suffix.strip().upper()
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    if not _VALID_DEFAULT_SUFFIX_RE.fullmatch(suffix):
        raise ValueError("Invalid default exchange suffix")
    return suffix
