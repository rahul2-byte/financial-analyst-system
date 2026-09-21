import json

from evals.mutations import evaluate_mutations, load_clean_reports


def test_mutation_evaluation_counts_clean_and_applied_cases(tmp_path):
    path = tmp_path / "clean.jsonl"
    path.write_text(json.dumps({"report": "Price [[fact:price.latest]].", "evidence": {"price.latest": 10}}) + "\n")

    records = load_clean_reports(path)
    result = evaluate_mutations(records, seed=0)

    assert result["clean"]["n"] == 1
    assert result["mutations"]["delete_numeric_marker"]["n"] == 1


def test_mutation_evaluation_does_not_count_unapplied_mutations():
    result = evaluate_mutations([{"report": "No facts here.", "evidence": {}}], seed=0)

    assert result["mutations"]["delete_numeric_marker"]["n"] == 0
