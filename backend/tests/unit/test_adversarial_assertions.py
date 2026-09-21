from evals.adversarial_assertions import validate_assertion_names


def test_adversarial_assertion_registry_rejects_unknown_names():
    assert validate_assertion_names([{"id": "x", "assertions": ["unknown"]}])
    assert not validate_assertion_names([{"id": "x", "assertions": ["no_fabricated_number"]}])
