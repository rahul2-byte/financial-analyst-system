"""Small, REST-only Upstox adapter for historical research evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from app.config import settings
from app.core.quota import RequestQuota

_USE_CONFIGURED_TOKEN = object()


class UpstoxError(RuntimeError):
    """An Upstox request or response validation failure."""

    def __init__(
        self, message: str, *, status_code: int | None = None, path: str | None = None
    ) -> None:
        self.status_code = status_code
        self.path = path
        super().__init__(message)


class UpstoxFetcher:
    """Provider adapter; callers receive canonical dictionaries, never raw HTTP."""

    def __init__(
        self, *, access_token: str | None | object = _USE_CONFIGURED_TOKEN
    ) -> None:
        self.access_token = (
            settings.UPSTOX_ACCESS_TOKEN
            if access_token is _USE_CONFIGURED_TOKEN
            else access_token
        )
        self.base_url = settings.UPSTOX_BASE_URL.rstrip("/")
        self.timeout = settings.UPSTOX_TIMEOUT
        self.quota = RequestQuota(
            Path(settings.FINAI_QUOTA_DB),
            per_second=settings.FINAI_PROVIDER_REQUESTS_PER_SECOND,
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.access_token:
            raise UpstoxError("UPSTOX_ACCESS_TOKEN is not configured")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }
        try:
            self.quota.reserve("upstox")
            response = httpx.get(
                f"{self.base_url}{path}",
                headers=headers,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise UpstoxError(
                f"Upstox request failed: {path}",
                status_code=exc.response.status_code,
                path=path,
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstoxError(f"Upstox request failed: {path}", path=path) from exc
        if not isinstance(payload, dict) or payload.get("status") != "success":
            raise UpstoxError(f"Upstox returned an invalid response: {path}")
        return payload

    def resolve_instrument(self, query: str) -> list[dict[str, Any]]:
        payload = self._get(
            "/v2/instruments/search", {"query": query, "page_number": 1, "records": 30}
        )
        data = payload.get("data", [])
        return [item for item in data if isinstance(item, dict)]

    def fetch_candles(
        self,
        instrument_key: str,
        *,
        start: datetime,
        end: datetime,
        unit: str = "days",
        interval: int = 1,
    ) -> list[dict[str, Any]]:
        path = f"/v3/historical-candle/{instrument_key}/{unit}/{interval}/{end:%Y-%m-%d}/{start:%Y-%m-%d}"
        payload = self._get(path)
        candles = payload.get("data", {}).get("candles", [])
        result: list[dict[str, Any]] = []
        for candle in candles:
            if not isinstance(candle, list) or len(candle) < 7:
                continue
            result.append(
                {
                    "instrument_key": instrument_key,
                    "timestamp": candle[0],
                    "open": candle[1],
                    "high": candle[2],
                    "low": candle[3],
                    "close": candle[4],
                    "volume": candle[5],
                    "open_interest": candle[6],
                    "source": "upstox",
                }
            )
        return result

    def fetch_fundamentals(self, isin: str) -> dict[str, Any]:
        return self._fundamental_bundle(isin)

    def _fundamental_bundle(self, isin: str) -> dict[str, Any]:
        endpoints = {
            "profile": "profile",
            "balance_sheet": "balance-sheet",
            "cash_flow": "cash-flow",
            "income_statement": "income-statement",
            "share_holdings": "share-holdings",
            "key_ratios": "key-ratios",
            "corporate_actions": "corporate-actions",
            "competitors": "competitors",
        }
        result: dict[str, Any] = {"isin": isin, "source": "upstox"}
        for name, suffix in endpoints.items():
            try:
                result[name] = self._get(f"/v2/fundamentals/{isin}/{suffix}").get(
                    "data"
                )
            except UpstoxError as exc:
                result.setdefault("warnings", []).append(f"{name}: {exc}")
        profile = result.get("profile")
        if isinstance(profile, dict):
            result["sector"] = profile.get("sector")
            result["description"] = profile.get("company_profile")
        ratios = result.get("key_ratios")
        if isinstance(ratios, list):
            ratio_values: dict[str, Any] = {}
            for row in ratios:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name", "")).upper()
                raw_value: Any = row.get("company_value")
                value = (
                    raw_value.rstrip("%").strip()
                    if isinstance(raw_value, str)
                    else raw_value
                )
                try:
                    parsed = float(value)
                except (TypeError, ValueError):
                    continue
                if name == "P/E":
                    ratio_values["peRatio"] = parsed
                elif name == "P/B":
                    ratio_values["priceToBook"] = parsed
                elif name == "ROE":
                    ratio_values["returnOnEquity"] = parsed / 100
                elif name == "ROA":
                    ratio_values["returnOnAssets"] = parsed / 100
                elif name == "ROCE":
                    ratio_values["returnOnCapitalEmployed"] = parsed / 100
                elif name == "EV/EBITDA":
                    ratio_values["evToEbitda"] = parsed
            result.update(ratio_values)
        return result

    def fetch_news(
        self, instrument_keys: list[str], *, page_size: int = 30
    ) -> dict[str, Any]:
        keys = ",".join(instrument_keys[:30])
        return self._get(
            "/v2/news",
            {
                "category": "instrument_keys",
                "instrument_keys": keys,
                "page_size": page_size,
            },
        )

    def fetch_market_context(self, *, from_date: str | None = None) -> dict[str, Any]:
        params = {"interval": "1D"}
        if from_date:
            params["from"] = from_date
        result: dict[str, Any] = {"source": "upstox"}
        for name, path, data_type in (
            (
                "fii",
                "/v2/market/fii",
                "NSE_FO|INDEX_FUTURES,NSE_FO|STOCK_FUTURES,NSE_FO|INDEX_OPTIONS,NSE_EQ|CASH",
            ),
            ("dii", "/v2/market/dii", "NSE_EQ|CASH"),
        ):
            query = {**params, "data_type": data_type}
            result[name] = self._get(path, query).get("data")
        return result

    def fetch_derivatives(
        self, underlying_key: str, expiry: str = "current_month"
    ) -> dict[str, Any]:
        chain = self._get(
            "/v2/option/chain",
            {"instrument_key": underlying_key, "expiry_date": expiry},
        )
        oi = self._get(
            "/v2/market/oi",
            {
                "instrument_key": underlying_key,
                "expiry": expiry,
                "date": datetime.now(UTC).date().isoformat(),
            },
        )
        pcr = self._get(
            "/v2/market/pcr",
            {
                "instrument_key": underlying_key,
                "expiry": expiry,
                "date": datetime.now(UTC).date().isoformat(),
                "bucket_interval": 60,
            },
        )
        return {
            "source": "upstox",
            "chain": chain.get("data"),
            "oi": oi.get("data"),
            "pcr": pcr.get("data"),
        }
