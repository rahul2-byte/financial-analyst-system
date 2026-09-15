from __future__ import annotations

import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]

ALLOWLIST = {
    Path("app/core/ticker.py"),
    Path("agents/financial/data/symbol_resolution.py"),
    Path("agents/financial/data/datasets/news.py"),
}

SUSPICIOUS_PATTERNS = (
    re.compile(r"\.endswith\(\s*[\"']\.(?:NS|BO)[\"']"),
    re.compile(r"\.removesuffix\(\s*[\"']\.(?:NS|BO)[\"']"),
    re.compile(r"\.replace\(\s*[\"']\.(?:NS|BO)[\"']"),
)


def test_ticker_normalization_stays_centralized() -> None:
    offenders: set[Path] = set()
    for path in BACKEND_ROOT.rglob("*.py"):
        relative = path.relative_to(BACKEND_ROOT)
        if relative.parts[0] in {"tests"}:
            continue

        text = path.read_text(encoding="utf-8")
        if any(pattern.search(text) for pattern in SUSPICIOUS_PATTERNS):
            offenders.add(relative)

    unexpected = offenders - ALLOWLIST
    assert not unexpected, (
        f"Move ticker suffix normalization to app.core.ticker: {sorted(unexpected)}"
    )
    assert offenders <= ALLOWLIST
