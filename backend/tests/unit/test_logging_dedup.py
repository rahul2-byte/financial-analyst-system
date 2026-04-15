from __future__ import annotations

import logging

from app.core.logging import RepeatedWarningFilter


def test_repeated_warning_filter_suppresses_duplicate_warnings_within_window() -> None:
    now = {"value": 1000.0}
    warning_filter = RepeatedWarningFilter(
        window_seconds=60.0,
        clock=lambda: now["value"],
    )

    first = logging.LogRecord(
        name="test.logger",
        level=logging.WARNING,
        pathname=__file__,
        lineno=10,
        msg="Repeated warning: %s",
        args=("boom",),
        exc_info=None,
    )
    second = logging.LogRecord(
        name="test.logger",
        level=logging.WARNING,
        pathname=__file__,
        lineno=11,
        msg="Repeated warning: %s",
        args=("boom",),
        exc_info=None,
    )

    assert warning_filter.filter(first) is True
    assert warning_filter.filter(second) is False

    now["value"] += 61.0

    assert warning_filter.filter(second) is True
