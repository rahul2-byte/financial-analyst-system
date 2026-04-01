from app.core.orchestration_schemas import ExecutionStep
from app.core.graph.scheduler import get_agent_name, find_next_level


def test_find_next_level_skips_executed_and_respects_dependencies():
    steps = [
        ExecutionStep(
            step_number=1,
            target_agent="market_offline",
            parameters={},
            dependencies=[],
        ),
        ExecutionStep(
            step_number=2,
            target_agent="retrieval",
            parameters={},
            dependencies=[1],
        ),
    ]

    next_level = find_next_level(steps, executed_step_ids={1})

    assert [s.step_number for s in next_level] == [2]


def test_get_agent_name_returns_string_for_target_agent():
    step = ExecutionStep(
        step_number=1,
        target_agent="market_offline",
        parameters={},
        dependencies=[],
    )
    assert get_agent_name(step) == "market_offline"
