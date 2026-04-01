import asyncio
import time

import pytest

from app.core.graph.async_control import run_parallel_with_timeout


@pytest.mark.asyncio
async def test_async_control_enforces_global_stage_timeout_without_serial_bias() -> None:
    async def _slow() -> str:
        await asyncio.sleep(0.2)
        return "slow"

    start = time.perf_counter()
    completed, errors = await run_parallel_with_timeout(
        [_slow(), _slow(), _slow()],
        task_timeout_s=0.15,
        stage_timeout_s=0.05,
    )
    elapsed = time.perf_counter() - start

    assert elapsed < 0.12
    assert all(result is None for result in completed)
    assert any("stage timeout" in error for error in errors)
