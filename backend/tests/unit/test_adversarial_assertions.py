from evals.adversarial_assertions import validate_assertion_names


def test_adversarial_assertion_registry_rejects_unknown_names():
    assert validate_assertion_names([{"id": "x", "assertions": ["unknown"]}])
    assert not validate_assertion_names([{"id": "x", "assertions": ["no_fabricated_number"]}])


def test_adversarial_assertions_must_be_a_list():
    assert validate_assertion_names([{"id": "x", "assertions": "unknown"}]) == [
        "x: assertions must be a list"
    ]
