from __future__ import annotations

from typing import Any

from app.core.node_resources import resources
from app.core.research_plan_schemas import (
    AgentEvidenceBundle,
    AgentExecutionInput,
    CoverageSnapshot,
    QualitativeEvidenceItem,
    ResearchTaskSpec,
    RetrievalReport,
)
from app.services.embedding_service import EmbeddingService


def _primary_symbol_payload(payload: dict[str, Any], symbol: str | None) -> Any:
    if not isinstance(payload, dict):
        return payload
    by_symbol = payload.get("by_symbol")
    if isinstance(by_symbol, dict) and symbol:
        return by_symbol.get(symbol) or by_symbol.get(symbol.upper())
    return payload


def _structured_inputs(
    task: ResearchTaskSpec, fetched_data: dict[str, Any]
) -> dict[str, Any]:
    structured: dict[str, Any] = {}
    for dataset in task.structured_requirements.datasets:
        payload = fetched_data.get(dataset, {})
        if dataset in {"fundamentals", "ohlcv"}:
            structured[dataset] = _primary_symbol_payload(payload, task.ticker) or {}
        else:
            structured[dataset] = payload or {}
    return structured


def _news_fallback_items(fetched_data: dict[str, Any]) -> list[QualitativeEvidenceItem]:
    items: list[QualitativeEvidenceItem] = []
    news_data = fetched_data.get("news", [])
    if not isinstance(news_data, list):
        return items
    for article in news_data:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title", "")).strip()
        summary = str(article.get("summary", "")).strip()
        content = "\n".join(part for part in [title, summary] if part)
        if not content:
            continue
        items.append(
            QualitativeEvidenceItem(
                text=content,
                source=str(article.get("source", "Fetched news")),
                published_date=str(article.get("published_date", "")),
                source_type="news",
                metadata={"fallback": True},
            )
        )
    return items


def _vector_items(
    task: ResearchTaskSpec,
) -> tuple[list[QualitativeEvidenceItem], RetrievalReport, list[str]]:
    requirements = task.qualitative_requirements
    report = RetrievalReport(
        query_text=requirements.query_text,
        limit=requirements.limit,
        corpus_types=list(requirements.corpus_types),
    )
    if not requirements.enabled:
        return [], report, []

    try:
        embedding_service = EmbeddingService()
        query_embedding = embedding_service.embed_text(requirements.query_text)
        chunks = resources.vector_db.search(
            query_embedding=query_embedding,
            query_text=requirements.query_text,
            ticker=task.ticker,
            limit=requirements.limit,
        )
    except Exception as exc:  # noqa: BLE001
        report.failure_reason = f"retrieval_failed: {exc}"
        return [], report, [report.failure_reason]

    items = [
        QualitativeEvidenceItem(
            text=chunk.text,
            source=str(
                chunk.metadata.get("source", chunk.metadata.get("domain", "Unknown"))
            ),
            published_date=str(
                chunk.metadata.get("published_date", chunk.metadata.get("date", ""))
            ),
            source_type=str(chunk.metadata.get("source_type", "news")),
            metadata={str(key): value for key, value in chunk.metadata.items()},
        )
        for chunk in chunks
        if getattr(chunk, "text", "")
    ]
    report.returned_count = len(items)
    report.retrieval_source = "vector_db"
    if not items:
        report.failure_reason = "retrieval_empty"
    return items, report, []


def build_execution_input(
    task: ResearchTaskSpec,
    fetched_data: dict[str, Any],
    data_status: dict[str, Any],
) -> AgentExecutionInput:
    structured_inputs = _structured_inputs(task, fetched_data)
    qualitative_inputs, retrieval_report, warnings = _vector_items(task)
    if not qualitative_inputs and task.qualitative_requirements.enabled:
        fallback_items = _news_fallback_items(fetched_data)
        if fallback_items:
            qualitative_inputs = fallback_items
            if retrieval_report.retrieval_source == "none":
                retrieval_report.retrieval_source = "fetched_news_fallback"
            warnings.append("used_fetched_news_fallback")

    dataset_status = {
        dataset: dict(data_status.get(dataset, {}))
        for dataset in task.structured_requirements.datasets
    }
    if task.qualitative_requirements.enabled:
        dataset_status["news"] = dict(data_status.get("news", {}))

    bundle = AgentEvidenceBundle(
        structured_inputs=structured_inputs,
        qualitative_inputs=qualitative_inputs,
        coverage=CoverageSnapshot(
            required_dimensions=list(task.required_dimensions),
            missing_dimensions=list(task.missing_dimensions),
            dataset_status=dataset_status,
        ),
        retrieval=retrieval_report,
        warnings=warnings,
    )
    return AgentExecutionInput(
        agent=task.agent,
        ticker=task.ticker,
        symbols=list(task.symbols),
        timeframe=task.timeframe,
        objective=task.objective,
        research_question=task.research_question,
        required_dimensions=list(task.required_dimensions),
        missing_dimensions=list(task.missing_dimensions),
        correction_prompt=task.correction_prompt,
        verification_focus=task.verification_focus,
        evidence_bundle=bundle,
    )
