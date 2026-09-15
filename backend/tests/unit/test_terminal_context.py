from app.models.request_models import Message
from finai.context_budget import ContextBudget


def test_context_budget_defaults_to_250k_and_compacts_at_90_percent() -> None:
    budget = ContextBudget()

    assert budget.max_tokens == 250_000
    assert budget.compaction_limit == 225_000
    assert budget.should_compact(225_000)


def test_context_budget_estimate_is_deterministic_and_conservative() -> None:
    budget = ContextBudget()

    assert budget.estimate("12345678") == 2
    assert budget.estimate("") == 0


def test_context_compaction_returns_provenance_for_discarded_messages() -> None:
    budget = ContextBudget(max_tokens=10, compaction_ratio=0.9)
    messages = [
        Message(role="user", content="x" * 40),
        Message(role="assistant", content="y" * 40),
        Message(role="user", content="new"),
    ]

    _kept, result = budget.compact(messages)

    assert result["compacted_messages"] == 2
    assert isinstance(result["source_hash"], str)
    assert result["source_hash"]
