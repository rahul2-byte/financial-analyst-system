from decimal import Decimal

from evals.numeric import parse_number, within_tolerance


def _value(text: str):
    parsed = parse_number(text)
    assert parsed is not None
    return parsed["value"]


def test_parse_indian_units_and_currency():
    assert _value("₹1.2 lakh") == Decimal(120000)
    assert _value("12 crore") == Decimal(120000000)
    assert _value("1,23,456") == Decimal(123456)


def test_parse_percentage_and_exclude_years():
    parsed = parse_number("12.5%")
    assert parsed is not None
    assert parsed["value"] == Decimal("12.5")
    assert parsed["unit"] == "%"
    assert parse_number("2026") is None


def test_within_tolerance():
    actual = parse_number("₹100.05")
    expected = parse_number("₹100")
    assert within_tolerance(actual, expected, Decimal("0.1"))
