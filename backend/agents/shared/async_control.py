"""Bounded concurrent execution helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any


async def run_parallel_with_timeout(coroutines: list[Coroutine[Any, Any, Any]], task_timeout_s: float | None, stage_timeout_s: float | None) -> tuple[list[Any | None], list[str]]:
    async def run_one(index: int, coroutine: Coroutine[Any, Any, Any]) -> tuple[int, Any | None, str | None]:
        try:
            return index, await asyncio.wait_for(coroutine, timeout=task_timeout_s), None
        except TimeoutError:
            return index, None, f"task timeout:{index}"

    tasks = [asyncio.create_task(run_one(index, coroutine)) for index, coroutine in enumerate(coroutines)]
    completed: list[Any | None] = [None] * len(tasks)
    errors: list[str] = []
    done, pending = await asyncio.wait(tasks, timeout=stage_timeout_s)
    for task in done:
        index, value, error = task.result()
        completed[index] = value
        if error:
            errors.append(error)
    if pending:
        errors.append("stage timeout")
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    return completed, errors
