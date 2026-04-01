from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any


async def run_parallel_with_timeout(
    coroutines: list[Coroutine[Any, Any, Any]], task_timeout_s: float, stage_timeout_s: float
) -> tuple[list[Any | None], list[str]]:
    async def _run_one(index: int, coroutine: Coroutine[Any, Any, Any]) -> tuple[int, Any | None, str | None]:
        try:
            result = await asyncio.wait_for(coroutine, timeout=task_timeout_s)
            return index, result, None
        except asyncio.TimeoutError:
            return index, None, f"task timeout:{index}"

    wrapper_tasks = [
        asyncio.create_task(_run_one(index, coroutine))
        for index, coroutine in enumerate(coroutines)
    ]

    completed: list[Any | None] = [None] * len(wrapper_tasks)
    errors: list[str] = []

    done, pending = await asyncio.wait(wrapper_tasks, timeout=stage_timeout_s)
    for task in done:
        result = task.result()
        index, value, maybe_error = result
        completed[index] = value
        if maybe_error:
            errors.append(maybe_error)

    if pending:
        errors.append("stage timeout")
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    return completed, errors
