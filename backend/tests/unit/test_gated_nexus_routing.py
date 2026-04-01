import pytest
from app.core.graph.graph_builder import route_after_discovery, route_after_planner, route_after_verification
from app.core.orchestration_schemas import DataStatus, PlannerResponseMode
from langgraph.graph import END

def test_discovery_routing_logic():
    # 1. Test Discovery -> END (Approval required)
    state_unapproved = {
        "data_manifest": {
            "user_approved": False,
            "datasets": [{"dataset_type": "ohlcv", "status": "missing"}]
        }
    }
    assert route_after_discovery(state_unapproved) == END

    # 2. Test Discovery -> Acquisition
    state_approved_missing = {
        "data_manifest": {
            "user_approved": True,
            "datasets": [{"dataset_type": "ohlcv", "status": "missing"}]
        }
    }
    assert route_after_discovery(state_approved_missing) == "acquisition_subgraph"

    # 3. Test Discovery -> Planner (Data available)
    state_approved_ready = {
        "data_manifest": {
            "user_approved": True,
            "datasets": [{"dataset_type": "ohlcv", "status": "available"}]
        }
    }
    assert route_after_discovery(state_approved_ready) == "planner_node"

def test_research_routing_logic():
    # 1. Test Planner -> Research
    state = {"errors": []}
    assert route_after_planner(state) == "research_subgraph"

    # 2. Test Verification -> Validation (No conflict)
    state_verified = {"verification_passed": True}
    assert route_after_verification(state_verified) == "validation_node"

    # 3. Test Verification -> Research (Conflict re-trigger)
    state_conflict = {"verification_passed": False, "verification_retry_count": 0}
    assert route_after_verification(state_conflict) == "research_subgraph"
