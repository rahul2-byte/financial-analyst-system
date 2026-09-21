from pydantic import ValidationError

from evals.judge import JudgeEvaluation, _parse, summarize


def test_judge_parse_and_summary() -> None:
    row = _parse(
        '{"verdict":"pass","outcome":"answer","numeric_correct":true,'
        '"tool_behavior_correct":true,"citation_support":"supports",'
        '"safety_behavior":"safe","reason":"grounded",'
        '"evidence_refs":["snapshot:1"]}',
        "case-1",
        "gpt-5.6-sol",
        "judge-v1",
    )
    assert isinstance(row, JudgeEvaluation)
    assert summarize([row])["status"] == "judge_evaluated"


def test_judge_rejects_unknown_enum() -> None:
    try:
        _parse(
            '{"verdict":"maybe","outcome":"answer","citation_support":"supports",'
            '"safety_behavior":"safe","reason":"x"}',
            "case-1",
            "gpt-5.6-sol",
            "judge-v1",
        )
    except (ValidationError, ValueError, TypeError) as exc:
        assert "verdict" in str(exc)
    else:
        raise AssertionError("invalid verdict accepted")
