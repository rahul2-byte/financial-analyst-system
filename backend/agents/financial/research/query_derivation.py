from __future__ import annotations

from typing import Any


def _hypothesis_summary(hypotheses: list[dict[str, Any]]) -> str:
    statements = [str(item.get("statement", "")).strip() for item in hypotheses]
    statements = [statement for statement in statements if statement]
    return "; ".join(statements[:3])


def derive_agent_objective(
    agent: str,
    ticker: str | None,
    user_query: str,
    timeframe: str | None,
    hypotheses: list[dict[str, Any]],
    correction_prompt: str | None = None,
) -> str:
    symbol = ticker or "the target company"
    time_scope = timeframe or "the requested timeframe"
    hypothesis_summary = _hypothesis_summary(hypotheses)

    templates = {
        "fundamental_analysis": (
            f"Test whether {symbol} fundamentals support or weaken the user objective over {time_scope}, "
            "with emphasis on earnings quality, balance-sheet resilience, and valuation support."
        ),
        "technical_analysis": (
            f"Determine whether {symbol} price structure over {time_scope} confirms, contradicts, or complicates the user objective."
        ),
        "sentiment_analysis": (
            f"Assess whether recent narrative, management commentary, and market reaction for {symbol} over {time_scope} increase or reduce confidence in the user objective."
        ),
        "macro_analysis": (
            f"Evaluate whether macro and sector regime conditions over {time_scope} amplify or offset the risks embedded in the user objective for {symbol}."
        ),
        "contrarian_analysis": (
            f"Challenge the emerging thesis for {symbol} by identifying where consensus narrative may be overreacting or missing offsets over {time_scope}."
        ),
    }

    objective = templates.get(
        agent, f"Analyze {symbol} for the user objective over {time_scope}."
    )
    if hypothesis_summary:
        objective = f"{objective} Planning context: {hypothesis_summary}"
    if correction_prompt:
        objective = f"{objective} Correction focus: {correction_prompt}"
    return objective


def derive_research_question(
    agent: str,
    ticker: str | None,
    user_query: str,
    timeframe: str | None,
    objective: str,
    missing_dimensions: list[str],
    correction_prompt: str | None = None,
) -> str:
    symbol = ticker or "the target company"
    time_scope = timeframe or "the requested timeframe"
    gaps = (
        ", ".join(missing_dimensions)
        if missing_dimensions
        else "no known evidence gaps"
    )

    templates = {
        "fundamental_analysis": (
            f"For {symbol}, determine whether the available fundamentals over {time_scope} support or weaken the user request '{user_query}'. "
            f"Focus on profitability, valuation, and balance-sheet signals. Evidence gaps to address: {gaps}."
        ),
        "technical_analysis": (
            f"For {symbol}, analyze price action over {time_scope} to determine whether market structure confirms or contradicts the user request '{user_query}'. "
            f"Focus on trend, momentum, and volatility. Evidence gaps to address: {gaps}."
        ),
        "sentiment_analysis": (
            f"For {symbol}, retrieve and interpret recent news, commentary, and narrative signals over {time_scope} that are directly relevant to '{user_query}'. "
            f"Prioritize guidance changes, execution concerns, analyst reaction, and management tone. Evidence gaps to address: {gaps}."
        ),
        "macro_analysis": (
            f"For {symbol}, identify macro and sector regime conditions over {time_scope} that could validate or invalidate '{user_query}'. Evidence gaps to address: {gaps}."
        ),
        "contrarian_analysis": (
            f"For {symbol}, identify the strongest counter-thesis to '{user_query}' over {time_scope}. Use validated prior agent results plus relevant narrative evidence. Evidence gaps to address: {gaps}."
        ),
    }
    question = templates.get(agent, objective)
    if correction_prompt:
        question = f"{question} Correction guidance: {correction_prompt}"
    return question
