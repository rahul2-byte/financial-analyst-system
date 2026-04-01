from __future__ import annotations

import asyncio
from typing import Any


async def _run_fundamental(_state: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(0)
    return {"signal": "neutral", "confidence": 0.65, "evidence_strength": 0.7}


async def _run_sentiment(_state: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(0)
    return {"signal": "bullish", "confidence": 0.62, "evidence_strength": 0.6}


async def _run_macro(_state: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(0)
    return {"signal": "mixed", "confidence": 0.58, "evidence_strength": 0.55}


async def research_execution_node(state: dict[str, Any]) -> dict[str, Any]:
    fundamental_task = _run_fundamental(state)
    sentiment_task = _run_sentiment(state)
    macro_task = _run_macro(state)

    fundamental, sentiment, macro = await asyncio.gather(
        fundamental_task, sentiment_task, macro_task, return_exceptions=False
    )

    results = {
        "fundamental": fundamental,
        "sentiment": sentiment,
        "macro": macro,
    }

    return {
        "status": "success",
        "reasoning": "Executed fundamental, sentiment, and macro analysis in parallel.",
        "confidence_score": float(state.get("confidence_score", 0.66)),
        "next_action": "run_synthesis",
        "data": {"results": results},
        "results": results,
        "errors": [],
    }
