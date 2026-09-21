from evals.agreement import cohens_kappa
from evals.provider_checks import compare_values
from evals.reference_indicators import macd, rsi, sma


def test_reference_indicators_are_deterministic():
    assert sma([1, 2, 3, 4], 2) == 3.5
    assert round(rsi(list(range(1, 20))), 6) == 100.0
    assert len(macd(list(range(1, 45)))) == 3


def test_kappa_and_provider_checks():
    assert cohens_kappa(["supports", "unsupported"], ["supports", "unsupported"]) == 1.0
    result = compare_values([
        {"primary_value": 10, "independent_value": 10.01, "tolerance": 0.02},
        {"primary_value": 10, "independent_value": 12, "tolerance": 0.02},
    ])
    assert result["agree"] == 1
    assert result["disagree"] == 1
