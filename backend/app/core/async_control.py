from __future__ import annotations

import asyncio
from typing import Any


async def run_parallel_with_timeout(
    coroutines: list[Any], task_timeout_s: float, stage_timeout_s: float
) -> tuple[list[Any], list[str]]:
    tasks = [asyncio.create_task(coro) for coro in coroutines]
    completed: list[Any] = []
    errors: list[str] = []

    try:
        for task in tasks:
            try:
                result = await asyncio.wait_for(task, timeout=task_timeout_s)
                completed.append(result)
            except asyncio.TimeoutError:
                errors.append("task timeout")
                task.cancel()

        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=stage_timeout_s
        )
    except asyncio.TimeoutError:
        errors.append("stage timeout")
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    return completed, errors
