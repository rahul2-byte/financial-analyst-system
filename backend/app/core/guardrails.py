"""Deterministic request and tool guardrails shared by app and CLI."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.models.routing import PromptInjectionRisk
from pydantic import BaseModel, ConfigDict, Field, field_validator

_TICKER = re.compile(r"^[A-Za-z0-9._|:-]{1,64}$")
_PERIODS = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y"}
_INTERVALS = {"1d", "1wk", "1h", "4h", "15m", "5m", "1m"}
_EXCHANGES = {"NSE", "BSE"}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INJECTION_RULES = {
    "instruction_override": re.compile(
        r"\b(ignore|disregard|override)\b.{0,80}\b(previous|system|developer|safety|instructions?)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    "privilege_claim": re.compile(
        r"\b(reveal|print|show|leak)\b.{0,80}\b(system prompt|secret|token|api key|credentials?)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    "tool_manipulation": re.compile(
        r"(?:\b(call|run|execute|use)\b.{0,60}\b(any|all|hidden|internal)\b.{0,40}\btool|tool permission)",
        re.IGNORECASE | re.DOTALL,
    ),
}


class InputSafetyAssessment(BaseModel):
    risk: PromptInjectionRisk = PromptInjectionRisk.LOW
    flags: list[str] = Field(default_factory=list)


def assess_input_safety(value: str) -> InputSafetyAssessment:
    """Detect clear instruction attacks before any model or tool is called."""
    flags = [
        name for name, pattern in _INJECTION_RULES.items() if pattern.search(value)
    ]
    risk = (
        PromptInjectionRisk.HIGH
        if len(flags) >= 2
        else PromptInjectionRisk.MEDIUM
        if flags
        else PromptInjectionRisk.LOW
    )
    return InputSafetyAssessment(risk=risk, flags=flags)


class ToolArguments(BaseModel):
    """Strict common tool arguments; unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid", strict=True)
    ticker: str = Field(min_length=1, max_length=64)
    period: str | None = None
    interval: str | None = None
    limit: int | None = Field(default=None, ge=1, le=20)

    @field_validator("ticker")
    @classmethod
    def valid_ticker(cls, value: str) -> str:
        value = value.strip().upper()
        if not _TICKER.fullmatch(value):
            raise ValueError("ticker contains unsupported characters")
        return value

    @field_validator("period")
    @classmethod
    def valid_period(cls, value: str | None) -> str | None:
        if value is not None and value not in _PERIODS:
            raise ValueError("unsupported period")
        return value

    @field_validator("interval")
    @classmethod
    def valid_interval(cls, value: str | None) -> str | None:
        if value is not None and value not in _INTERVALS:
            raise ValueError("unsupported interval")
        return value


def validate_tool_arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate model arguments before a tool reaches a provider."""
    if name == "interaction:ask_user":
        if set(arguments) != {"question"} or not isinstance(
            arguments.get("question"), str
        ):
            raise ValueError("clarification requires only a question")
        question = arguments["question"].strip()
        if not question or len(question) > 500:
            raise ValueError("clarification question must be 1-500 characters")
        return {"question": question}
    if name == "data:fetch_market_status":
        if set(arguments) != {"exchange"} or not isinstance(
            arguments.get("exchange"), str
        ):
            raise ValueError("market status requires only exchange")
        exchange = arguments["exchange"].strip().upper()
        if exchange not in _EXCHANGES:
            raise ValueError("unsupported exchange")
        return {"exchange": exchange}
    if name == "data:fetch_market_holidays":
        if set(arguments) - {"date"} or not isinstance(arguments.get("date"), str):
            raise ValueError("market holidays requires an ISO date")
        iso_date = arguments["date"].strip()
        if not _DATE.fullmatch(iso_date):
            raise ValueError("market holidays requires an ISO date")
        try:
            date.fromisoformat(iso_date)
        except ValueError as exc:
            raise ValueError("market holidays requires an ISO date") from exc
        return {"date": iso_date}
    if name not in {
        "data:fetch_stock_data",
        "data:fetch_fundamentals",
        "news:fetch_news",
        "analysis:run_fundamental_scan",
        "analysis:run_technical_scan",
        "analysis:get_technical_overview",
    }:
        raise ValueError(f"tool is not permitted: {name}")
    validated = ToolArguments.model_validate(arguments)
    if name in {"data:fetch_fundamentals", "analysis:run_fundamental_scan"} and (
        validated.period is not None
        or validated.interval is not None
        or validated.limit is not None
    ):
        raise ValueError("fundamental tools accept ticker only")
    if name == "news:fetch_news" and (
        validated.period is not None or validated.interval is not None
    ):
        raise ValueError("news tool accepts ticker and limit only")
    return validated.model_dump(exclude_none=True)
