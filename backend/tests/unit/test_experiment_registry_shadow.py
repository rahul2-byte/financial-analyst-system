from experiments.registry import ExperimentRegistry
from experiments.shadow import ShadowLedger


def test_registry_completes_and_lists(tmp_path):
    registry = ExperimentRegistry(tmp_path)
    run_id = registry.create({"strategy": "fixture"})
    registry.complete(run_id, {"metrics": {"trade_count": 0}})
    assert registry.load(run_id)["status"] == "completed"
    assert len(registry.list()) == 1


def test_shadow_ledger_is_idempotent(tmp_path):
    ledger = ShadowLedger(tmp_path / "shadow.jsonl")
    assert ledger.append("obs-1", {"decision": "hold"})
    assert not ledger.append("obs-1", {"decision": "buy"})
    assert ledger.seen_ids() == {"obs-1"}
