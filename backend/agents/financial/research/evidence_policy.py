from __future__ import annotations

from typing import Any

from app.core.research_plan_schemas import (
    QualitativeEvidenceRequirements,
    StructuredEvidenceRequirements,
)

AGENT_PRIORITIES: dict[str, str] = {
    "fundamental_analysis": "P0",
    "technical_analysis": "P1",
    "sentiment_analysis": "P1",
    "macro_analysis": "P1",
    "contrarian_analysis": "P2",
}

AGENT_DEPENDENCIES: dict[str, list[str]] = {
    "contrarian_analysis": [
        "fundamental_analysis",
        "technical_analysis",
        "sentiment_analysis",
        "macro_analysis",
    ]
}

AGENT_BASE_DIMENSIONS: dict[str, list[str]] = {
    "fundamental_analysis": ["profitability", "valuation", "balance_sheet"],
    "technical_analysis": ["price_action", "trend", "volatility"],
    "sentiment_analysis": ["qualitative_sentiment", "management_narrative"],
    "macro_analysis": ["macro_regime"],
}

AGENT_DATASETS: dict[str, list[str]] = {
    "fundamental_analysis": ["fundamentals"],
    "technical_analysis": ["ohlcv"],
    "sentiment_analysis": ["news"],
    "macro_analysis": ["macro"],
    "contrarian_analysis": ["fundamentals", "ohlcv", "news", "macro"],
}

DIMENSION_DATASETS: dict[str, list[str]] = {
    "profitability": ["fundamentals"],
    "valuation": ["fundamentals"],
    "balance_sheet": ["fundamentals"],
    "price_action": ["ohlcv"],
    "trend": ["ohlcv"],
    "volatility": ["ohlcv"],
    "qualitative_sentiment": ["news"],
    "management_narrative": ["news"],
    "macro_regime": ["macro"],
}


def _dataset_ready(data_status: dict[str, Any], dataset: str) -> bool:
    status = data_status.get(dataset, {})
    if not isinstance(status, dict):
        return False
    return (
        bool(status.get("available", False))
        and float(status.get("coverage", 0.0)) >= 0.5
        and float(status.get("freshness", 0.0)) >= 0.5
    )


def derive_required_dimensions(
    objective: str, hypotheses: list[dict[str, Any]]
) -> list[str]:
    text_parts = [objective.lower()]
    text_parts.extend(str(item.get("statement", "")).lower() for item in hypotheses)
    merged = " ".join(text_parts)

    dimensions: list[str] = []
    if any(
        keyword in merged
        for keyword in ["earnings", "margin", "fundamental", "cash", "balance sheet"]
    ):
        dimensions.extend(["profitability", "valuation", "balance_sheet"])
    if any(
        keyword in merged
        for keyword in ["price", "trend", "technical", "momentum", "volatility"]
    ):
        dimensions.extend(["price_action", "trend", "volatility"])
    if any(
        keyword in merged
        for keyword in ["sentiment", "news", "narrative", "guidance", "commentary"]
    ):
        dimensions.extend(["qualitative_sentiment", "management_narrative"])
    if any(
        keyword in merged
        for keyword in ["macro", "rates", "policy", "regime", "sector"]
    ):
        dimensions.append("macro_regime")
    if not dimensions:
        dimensions.extend(["profitability", "price_action", "qualitative_sentiment"])
    return sorted(set(dimensions))


def dimensions_for_agent(agent: str, dimensions: list[str]) -> list[str]:
    supported: list[str] = list(AGENT_BASE_DIMENSIONS.get(agent, []))
    datasets = set(AGENT_DATASETS.get(agent, []))
    for dimension in dimensions:
        mapped = set(DIMENSION_DATASETS.get(dimension, []))
        if mapped & datasets and dimension not in supported:
            supported.append(dimension)
    if agent == "contrarian_analysis":
        return dimensions
    return supported


def missing_dimensions_for_agent(
    agent: str, dimensions: list[str], data_status: dict[str, Any]
) -> list[str]:
    missing: list[str] = []
    for dimension in dimensions_for_agent(agent, dimensions):
        datasets = DIMENSION_DATASETS.get(dimension, [])
        if datasets and not any(
            _dataset_ready(data_status, dataset) for dataset in datasets
        ):
            missing.append(dimension)
    return missing


def build_structured_requirements(
    agent: str,
) -> StructuredEvidenceRequirements:
    required_fields: dict[str, list[str]] = {
        "fundamental_analysis": ["marketCap"],
        "technical_analysis": ["data"],
        "macro_analysis": [],
        "contrarian_analysis": [],
    }
    return StructuredEvidenceRequirements(
        datasets=AGENT_DATASETS.get(agent, []),
        required_fields=required_fields.get(agent, []),
    )


def build_qualitative_requirements(
    agent: str,
    research_question: str,
) -> QualitativeEvidenceRequirements:
    if agent not in {"sentiment_analysis", "contrarian_analysis"}:
        return QualitativeEvidenceRequirements(enabled=False)
    corpus_types = ["news", "filing", "transcript"]
    return QualitativeEvidenceRequirements(
        enabled=True,
        corpus_types=corpus_types,
        query_text=research_question,
        limit=8 if agent == "sentiment_analysis" else 10,
        recency_window_days=120 if agent == "sentiment_analysis" else 180,
    )


def dependencies_for_agent(agent: str) -> list[str]:
    return list(AGENT_DEPENDENCIES.get(agent, []))
