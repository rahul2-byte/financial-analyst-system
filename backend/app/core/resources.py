"""Explicit runtime-owned external services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RuntimeResources:
    """Services shared by one runtime instance."""

    llm_service: Any
    yf_fetcher: Any


def build_runtime_resources(*, llm_service: Any | None = None, yf_fetcher: Any | None = None) -> RuntimeResources:
    """Build runtime dependencies, allowing tests to inject fakes."""
    if llm_service is None:
        from app.services.hive_service import HiveService

        llm_service = HiveService()
    if yf_fetcher is None:
        from data.providers.yfinance import YFinanceFetcher

        yf_fetcher = YFinanceFetcher()
    return RuntimeResources(llm_service=llm_service, yf_fetcher=yf_fetcher)
