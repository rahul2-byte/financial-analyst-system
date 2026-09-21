from decimal import Decimal

from evals.numeric import parse_number, within_tolerance


def test_parse_indian_units_and_currency():
    assert parse_number("₹1.2 lakh")["value"] == Decimal(120000)
    assert parse_number("12 crore")["value"] == Decimal(120000000)
    assert parse_number("1,23,456")["value"] == Decimal(123456)


def test_parse_percentage_and_exclude_years():
    parsed = parse_number("12.5%")
    assert parsed["value"] == Decimal("12.5")
    assert parsed["unit"] == "%"
    assert parse_number("2026") is None


def test_within_tolerance():
    actual = parse_number("₹100.05")
    expected = parse_number("₹100")
    assert within_tolerance(actual, expected, Decimal("0.1"))
