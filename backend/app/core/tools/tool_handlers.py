"""Built-in tool handlers registered by :class:`ToolExecutor`."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from quant.fundamentals import FundamentalScanner
from quant.indicators import TechnicalScanner


def fundamental_scan(args: dict[str, Any]) -> dict[str, Any]:
    raw_data = args.get("raw_data", {})
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except json.JSONDecodeError:
            raw_data = {}
    if not isinstance(raw_data, dict) or not raw_data:
        return {"error": "No fundamental data provided"}
    if not any(raw_data.get(key) is not None for key in (
        "peRatio", "forwardPE", "priceToBook", "debtToEquity",
        "profitMargins", "returnOnEquity",
    )):
        return {"error": "No usable fundamental metrics provided"}
    return FundamentalScanner().scan(raw_data)


def technical_scan(args: dict[str, Any]) -> dict[str, Any]:
    ohlcv_data = args.get("ohlcv_data", [])
    if not ohlcv_data:
        return {"error": "No OHLCV data provided"}
    import pandas as pd

    return TechnicalScanner().scan(pd.DataFrame(ohlcv_data))


def register_default_handlers(register: Callable[[str, Callable[..., Any]], None]) -> None:
    handlers: dict[str, Callable[..., Any]] = {
        "market:submit_offline_status": lambda args: args,
        "data:fetch_stock_data": lambda args: {"delegate_to_agent": "price_and_fundamentals"},
        "data:fetch_fundamentals": lambda args: {"delegate_to_agent": "price_and_fundamentals"},
        "data:submit_data_response": lambda args: args,
        "news:fetch_news": lambda args: {"delegate_to_agent": "market_news"},
        "news:submit_news_summary": lambda args: args,
        "macro:fetch_macro_data": lambda args: {"delegate_to_agent": "macro_indicators"},
        "macro:calculate_indicators": lambda args: {"calculated": args.get("raw_data", {})},
        "analysis:run_fundamental_scan": fundamental_scan,
        "analysis:submit_thesis": lambda args: args,
        "analysis:run_technical_scan": technical_scan,
        "analysis:submit_technical_report": lambda args: args,
        "analysis:submit_sentiment": lambda args: args,
        "analysis:submit_macro_report": lambda args: args,
        "analysis:submit_contrarian_report": lambda args: args,
    }
    for name, handler in handlers.items():
        register(name, handler)
