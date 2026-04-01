"""
Input validation utilities for the Financial Intelligence Platform.

This module provides:
- Query sanitization
- Malicious pattern detection
- Input validation for various data types

Usage:
    from app.core.validators import sanitize_user_query, validate_query_not_malicious

    is_safe, reason = validate_query_not_malicious(user_input)
    clean_input = sanitize_user_query(user_input)
"""

import html
import re
from typing import Tuple, Optional

MALICIOUS_PATTERNS: list[str] = [
    r"ignore\s+(all\s+)?(previous|above|prior)",
    r"forget\s+(everything|all)\s+you\s+(know|were|have)",
    r"system\s*:\s*",
    r"assistant\s*:\s*",
    r"<!DOCTYPE\s+html",
    r"<script[^>]*>",
]

MAX_QUERY_LENGTH = 2000
MAX_QUERY_DISPLAY_LENGTH = 5000


def sanitize_user_query(query: str, max_length: int = MAX_QUERY_LENGTH) -> str:
    """
    Sanitize user query to prevent injection attacks.

    Args:
        query: Raw user input
        max_length: Maximum allowed length

    Returns:
        Sanitized query
    """
    if not query:
        return ""

    sanitized = query[:max_length]
    sanitized = sanitized.replace("\x00", "")
    sanitized = html.escape(sanitized)
    sanitized = " ".join(sanitized.split())

    return sanitized


def validate_query_not_malicious(query: str) -> Tuple[bool, str]:
    """
    Check if query appears malicious.

    Returns:
        Tuple of (is_safe, reason_if_unsafe)
    """
    if not query or len(query.strip()) == 0:
        return False, "Empty query"

    if len(query) > MAX_QUERY_DISPLAY_LENGTH:
        return False, "Query too long"

    query_lower = query.lower()
    for pattern in MALICIOUS_PATTERNS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            return False, "Potentially malicious pattern detected"

    return True, ""


def validate_ticker(ticker: Optional[str]) -> Tuple[bool, str]:
    """
    Validate a stock ticker symbol.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not ticker:
        return False, "Ticker is required"

    ticker = ticker.strip().upper()

    if len(ticker) > 10:
        return False, "Ticker too long"

    if not re.match(r"^[A-Z0-9\.\-\^]+$", ticker):
        return False, "Invalid ticker format"

    return True, ""


def validate_date_range(
    start_date: Optional[str], end_date: Optional[str]
) -> Tuple[bool, str]:
    """
    Validate date range parameters.

    Args:
        start_date: Start date in ISO format
        end_date: End date in ISO format

    Returns:
        Tuple of (is_valid, error_message)
    """
    from datetime import datetime

    if not start_date or not end_date:
        return True, ""

    try:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)

        if start > end:
            return False, "Start date must be before end date"

        if (end - start).days > 365 * 10:
            return False, "Date range cannot exceed 10 years"

        return True, ""
    except ValueError as e:
        return False, f"Invalid date format: {str(e)}"
