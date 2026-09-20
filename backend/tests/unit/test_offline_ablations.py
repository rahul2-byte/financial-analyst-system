import json
from typing import Any

from evals.ablations import (
    ABLATION_VARIANTS,
    compare_ablation_results,
    variant_configuration,
)


def test_ablation_variants_are_a_complete_four_cell_matrix() -> None:
    assert [variant.name for variant in ABLATION_VARIANTS] == [
        "baseline",
        "quality_only",
        "publication_only",
        "full",
    ]
    assert variant_configuration({}, "baseline") == {
        "source_quality_filtering": False,
        "publish_reports": False,
    }
    assert variant_configuration({}, "full") == {
        "source_quality_filtering": True,
        "publish_reports": True,
    }


def test_ablation_comparison_reports_paired_counts_and_failures() -> None:
    artifacts: dict[str, list[dict[str, Any]]] = {
        "baseline": [
            {
                "case_id": "case-1",
                "terminal_status": "success",
                "failure_details": [],
                "report_validation": {"status": "structured"},
                "tool_details": [
                    {
                        "tool": "news:fetch_news",
                        "detail": json.dumps(
                            {
                                "news_quality": {
                                    "raw_count": 2,
                                    "quality_filtered_count": 1,
                                    "retained_count": 1,
                                }
                            }
                        ),
                    }
                ],
            },
            {
                "case_id": "case-2",
                "terminal_status": "failed",
                "failure_details": ["provider failed"],
                "report_validation": {"status": "pending"},
            },
        ],
        "quality_only": [
            {
                "case_id": "case-1",
                "terminal_status": "success",
                "failure_details": [],
                "report_validation": {"status": "structured"},
            },
            {
                "case_id": "case-2",
                "terminal_status": "success",
                "failure_details": [],
                "report_validation": {"status": "structured"},
            },
        ],
    }

    comparison = compare_ablation_results(artifacts)

    assert comparison["variants"]["baseline"]["scheduled_case_count"] == 2
    assert comparison["variants"]["baseline"]["failed_case_count"] == 1
    assert (
        comparison["differences"]["quality_only_vs_baseline"]["paired_case_count"] == 2
    )
    assert comparison["differences"]["quality_only_vs_baseline"][
        "terminal_success"
    ] == {
        "variant": {"count": 2, "denominator": 2},
        "baseline": {"count": 1, "denominator": 2},
        "delta_count": 1,
    }
    assert comparison["variants"]["baseline"]["failure_examples"]
    assert comparison["variants"]["baseline"]["source_quality"] == {
        "raw_count": {"count": 2, "denominator": 1},
        "quality_filtered_count": {"count": 1, "denominator": 1},
        "retained_count": {"count": 1, "denominator": 1},
    }
