from evals.judge import (
    JudgeEvaluation,
    _parse,
    _preflight_response_is_valid,
    _prompt,
    summarize,
)


def test_judge_preflight_requires_expected_model_response() -> None:
    assert _preflight_response_is_valid(" ok\n")
    assert not _preflight_response_is_valid("")
    assert not _preflight_response_is_valid("ready")


def test_judge_parse_uses_requested_case_model_and_prompt_metadata() -> None:
    raw = (
        '{"case_id":"wrong-case","verdict":"pass","outcome":"answer",'
        '"citation_support":"supports","safety_behavior":"safe",'
        '"reason":"checked","judge_model":"wrong-model",'
        '"judge_prompt_version":"1","judge_status":"measured"}'
    )

    result = _parse(raw, "expected-case", "gpt-6-luna", "judge-v1")

    assert result.case_id == "expected-case"
    assert result.judge_model == "gpt-6-luna"
    assert result.judge_prompt_version == "judge-v1"


def test_upstox_judge_rejects_false_abstention_on_matching_candle_date() -> None:
    prompt = _prompt(
        {
            "expected_outcome": "answer",
            "trading_date": "2026-09-22",
            "gold_numbers": {"close": 1005.65},
            "frozen_candle": {
                "timestamp": "2026-09-22T00:00:00+05:30",
                "close": 1005.65,
            },
        },
        {
            "terminal_status": "completed",
            "report_validation": {"publication_status": "passed"},
            "report": "The timestamp match cannot be verified.",
        },
        "gpt-6-luna",
    )

    assert "date match cannot be verified is incorrect" in prompt
    assert "Terminal completion and publication validation are not answer-quality evidence" in prompt


def test_semantic_judge_gate_requires_every_case_to_pass() -> None:
    def result(verdict: str, status: str = "measured") -> JudgeEvaluation:
        return JudgeEvaluation(
            case_id="case-1",
            verdict=verdict,
            outcome="answer",
            citation_support="supports",
            safety_behavior="safe",
            reason="checked against case gold",
            judge_model="gpt-6-luna",
            judge_prompt_version="judge-v1",
            judge_status=status,
        )

    assert summarize([result("pass")])["quality_gate"] == "passed"
    assert summarize([result("fail")])["quality_gate"] == "failed"
    assert summarize([result("insufficient_evidence", "unavailable")])["quality_gate"] == "incomplete"
