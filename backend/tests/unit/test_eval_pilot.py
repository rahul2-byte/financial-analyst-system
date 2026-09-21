from evals.pilot import score_results, validate_pilot_cases


def test_validate_pilot_cases_requires_replay_and_expected_outcome():
    case = {
        "id": "case-1",
        "category": "numeric",
        "query": "price",
        "expected_outcome": "answer",
        "expected_terminal_status": "success",
        "replay_snapshots": {"model_stream": "a" * 64},
        "source_hashes": ["b" * 64],
    }
    assert validate_pilot_cases([case]) == []
    assert validate_pilot_cases([{**case, "expected_outcome": "unknown"}])


def test_score_results_reports_outcome_and_numeric_success():
    case = {
        "id": "case-1",
        "expected_outcome": "answer",
        "expected_terminal_status": "success",
        "required_facts": [{"field": "price", "value": 10, "tolerance": 0.1}],
    }
    result = {"case_id": "case-1", "terminal_status": "success", "numeric_outputs": {"price": 10.05}}
    scored = score_results([case], [result])

    assert scored["case_count"] == 1
    assert scored["task_success"]["count"] == 1
