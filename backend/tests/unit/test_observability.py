from app.core.observability import (
    clear_recorded_metrics,
    get_recorded_metrics,
    observe,
    run_context,
)


def test_observe_records_local_duration() -> None:
    clear_recorded_metrics()

    @observe(name="unit")
    def work() -> str:
        return "ok"

    assert work() == "ok"
    assert get_recorded_metrics()[-1]["name"] == "unit"


def test_run_context_stores_run_metadata() -> None:
    run_context.update_current_trace(run_id="run-1")
    assert run_context.get_current_trace_id() == "run-1"
