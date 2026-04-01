"""
YFinance data provider for the Financial Intelligence Platform.

This module provides:
- OHLCV data fetching
- Company fundamentals
- Financial statements
- Macro indicators
- News fetching

Usage:
    from data.providers.yfinance import YFinanceFetcher

    fetcher = YFinanceFetcher()
    ohlcv_data = fetcher.fetch_ohlcv("RELIANCE.NS", start_date, end_date)
"""

import yfinance as yf
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.core.observability import observe
from data.interfaces.fetcher import IDataFetcher
from data.schemas.market import OHLCVData
from data.schemas.text import NewsArticle

INDIAN_STOCK_SUFFIX = ".NS"
DEFAULT_TICKER_SUFFIXES = [".NS", ".BO", ".SS"]


class YFinanceFetcher(IDataFetcher):
    """
    Data fetcher using yfinance library.

    Handles:
    - Auto-formatting of Indian stock tickers
    - Multi-index column handling
    - Error handling for missing data
    """

    def _format_ticker(self, ticker: str) -> str:
        """
        Auto-append .NS for Indian stocks if no suffix is provided.

        Args:
            ticker: Raw ticker symbol

        Returns:
            Formatted ticker with appropriate suffix
        """
        ticker = ticker.upper()
        if not any(suffix in ticker for suffix in [".", "=", "^"]):
            return f"{ticker}{INDIAN_STOCK_SUFFIX}"
        return ticker

    def _parse_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Parse yfinance DataFrame to handle multi-index columns.

        Args:
            df: Raw DataFrame from yfinance

        Returns:
            Cleaned DataFrame with simple columns
        """
        if df is None or df.empty:
            return df

        df = df.reset_index()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        return df

    def _safe_get_value(self, row: pd.Series, col: str, default: float = 0.0) -> float:
        """
        Safely extract a value from a DataFrame row.

        Args:
            row: DataFrame row
            col: Column name
            default: Default value if not found

        Returns:
            Float value
        """
        if col not in row:
            return default

        val = row[col]

        if isinstance(val, (pd.Series, np.ndarray)):
            if len(val) > 0:
                val = val.iloc[0]
            else:
                return default

        if pd.isna(val):
            return default

        return float(val)

    def _safe_get_date(self, row: pd.Series) -> Optional[datetime]:
        """
        Safely extract date from a DataFrame row.

        Args:
            row: DataFrame row

        Returns:
            datetime object or None
        """
        date_col = "Date" if "Date" in row.index else None

        if not date_col:
            for idx in row.index:
                if isinstance(idx, tuple):
                    for item in idx:
                        if "date" in str(item).lower():
                            date_col = item
                            break

        if not date_col:
            return None

        date_val = row[date_col]

        if date_val is None:
            return None

        if not isinstance(date_val, datetime):
            return pd.to_datetime(date_val).to_pydatetime()

        return date_val

    @observe(name="Tool:YFinance:FetchOHLCV")
    def fetch_ohlcv(
        self, ticker: str, start_date: datetime, end_date: datetime
    ) -> List[OHLCVData]:
        """
        Fetch historical OHLCV data.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date
            end_date: End date

        Returns:
            List of OHLCVData objects
        """
        formatted_ticker = self._format_ticker(ticker)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        df = yf.download(formatted_ticker, start=start_str, end=end_str, progress=False)

        if df is None or df.empty:
            return []

        df = self._parse_dataframe(df)

        results: List[OHLCVData] = []

        for _, row in df.iterrows():
            date_val = self._safe_get_date(row)

            if date_val is None:
                continue

            data = OHLCVData(
                ticker=formatted_ticker,
                date=date_val,
                open=self._safe_get_value(row, "Open"),
                high=self._safe_get_value(row, "High"),
                low=self._safe_get_value(row, "Low"),
                close=self._safe_get_value(row, "Close"),
                volume=int(self._safe_get_value(row, "Volume")),
                adjusted_close=(
                    self._safe_get_value(row, "Adj Close")
                    if "Adj Close" in row.index
                    else None
                ),
            )
            results.append(data)

        return results

    @observe(name="Tool:YFinance:FetchPrice")
    def fetch_stock_price(
        self, ticker: str, period: str = "1mo", interval: str = "1d"
    ) -> Dict[str, Any]:
        """
        Fetch stock price by period and interval.

        Args:
            ticker: Stock ticker
            period: Time period (e.g., "1mo", "1y")
            interval: Data interval (e.g., "1d", "1h")

        Returns:
            Dictionary with price data
        """
        formatted_ticker = self._format_ticker(ticker)

        df = yf.download(
            formatted_ticker, period=period, interval=interval, progress=False
        )

        if df is None or df.empty:
            return {"error": "No data found", "ticker": formatted_ticker}

        df = self._parse_dataframe(df)

        date_col = (
            "Date"
            if "Date" in df.columns
            else "Datetime" if "Datetime" in df.columns else df.columns[0]
        )
        df[date_col] = df[date_col].astype(str)

        return {
            "ticker": formatted_ticker,
            "period": period,
            "interval": interval,
            "data": df.to_dict(orient="records"),
        }

    @observe(name="Tool:YFinance:FetchFundamentals")
    def fetch_company_fundamentals(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch company fundamental data.

        Args:
            ticker: Stock ticker

        Returns:
            Dictionary with fundamental metrics
        """
        formatted_ticker = self._format_ticker(ticker)
        ticker_obj = yf.Ticker(formatted_ticker)
        info = ticker_obj.info

        if not info:
            return {"error": "No fundamental info found", "ticker": formatted_ticker}

        return {
            "ticker": formatted_ticker,
            "name": info.get("shortName", ""),
            "industry": info.get("industry", ""),
            "sector": info.get("sector", ""),
            "marketCap": info.get("marketCap"),
            "peRatio": info.get("trailingPE"),
            "forwardPE": info.get("forwardPE"),
            "pegRatio": info.get("pegRatio"),
            "priceToBook": info.get("priceToBook"),
            "debtToEquity": info.get("debtToEquity"),
            "returnOnEquity": info.get("returnOnEquity"),
            "profitMargins": info.get("profitMargins"),
            "revenueGrowth": info.get("revenueGrowth"),
            "earningsGrowth": info.get("earningsGrowth"),
            "dividendYield": info.get("dividendYield"),
            "currentPrice": info.get("currentPrice"),
            "targetMeanPrice": info.get("targetMeanPrice"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
        }

    @observe(name="Tool:YFinance:FetchFinancials")
    def fetch_financial_statements(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch financial statements.

        Args:
            ticker: Stock ticker

        Returns:
            Dictionary with income statement, balance sheet, cash flow
        """
        formatted_ticker = self._format_ticker(ticker)
        ticker_obj = yf.Ticker(formatted_ticker)

        income_stmt = ticker_obj.financials
        balance_sheet = ticker_obj.balance_sheet
        cash_flow = ticker_obj.cashflow

        def format_df(df: Optional[pd.DataFrame]) -> Dict[str, Any]:
            if df is None or df.empty:
                return {}

            df = df.copy()
            df.columns = [
                col.strftime("%Y-%m-%d") if isinstance(col, datetime) else str(col)
                for col in df.columns
            ]
            df = df.where(pd.notnull(df), None)
            return df.to_dict()

        return {
            "ticker": formatted_ticker,
            "income_statement": format_df(income_stmt),
            "balance_sheet": format_df(balance_sheet),
            "cash_flow": format_df(cash_flow),
        }

    @observe(name="Tool:YFinance:FetchMacro")
    def fetch_macro_indicators(self) -> Dict[str, Any]:
        """
        Fetch key macro indicators for Indian markets.

        Returns:
            Dictionary with macro indicator values
        """
        macros: Dict[str, str] = {
            "NIFTY_50": "^NSEI",
            "INDIA_VIX": "^INDIAVIX",
            "USD_INR": "INR=X",
            "CRUDE_OIL": "CL=F",
            "GOLD": "GC=F",
        }

        results: Dict[str, Optional[float]] = {}

        for name, ticker in macros.items():
            try:
                ticker_obj = yf.Ticker(ticker)
                history = ticker_obj.history(period="1d")

                if not history.empty:
                    close_price = history["Close"].iloc[-1]
                    if isinstance(close_price, pd.Series):
                        close_price = close_price.iloc[0]
                    results[name] = float(close_price)
                else:
                    results[name] = None
            except Exception:
                results[name] = None

        return results

    @observe(name="Tool:YFinance:FetchNews")
    def fetch_news(self, ticker: str, limit: int = 10) -> List[NewsArticle]:
        """
        Fetch latest news for a ticker.

        Args:
            ticker: Stock ticker
            limit: Maximum number of articles

        Returns:
            List of NewsArticle objects
        """
        formatted_ticker = self._format_ticker(ticker)
        ticker_obj = yf.Ticker(formatted_ticker)
        news_items = ticker_obj.news

        results: List[NewsArticle] = []

        for item in news_items[:limit]:
            pub_date = datetime.fromtimestamp(item.get("providerPublishTime", 0))

            article = NewsArticle(
                ticker=formatted_ticker,
                title=item.get("title", "No Title"),
                url=item.get("link", ""),
                source=item.get("publisher", "Unknown"),
                published_date=pub_date,
                content=str(item.get("relatedTickers", [])),
            )
            results.append(article)

        return results
