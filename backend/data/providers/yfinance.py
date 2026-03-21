import yfinance as yf
import pandas as pd
from typing import List, Dict, Any
from datetime import datetime
from app.core.observability import observe
from data.interfaces.fetcher import IDataFetcher
from data.schemas.market import OHLCVData
from data.schemas.text import NewsArticle


class YFinanceFetcher(IDataFetcher):
    def _format_ticker(self, ticker: str) -> str:
        """Auto-append .NS for Indian stocks if no suffix is provided."""
        ticker = ticker.upper()
        if not ("." in ticker or "=" in ticker or "^" in ticker):
            return f"{ticker}.NS"
        return ticker

    @observe(name="Tool:YFinance:FetchOHLCV")
    def fetch_ohlcv(
        self, ticker: str, start_date: datetime, end_date: datetime
    ) -> List[OHLCVData]:
        formatted_ticker = self._format_ticker(ticker)
        # yfinance expects YYYY-MM-DD string format
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        # Fetch data
        df = yf.download(formatted_ticker, start=start_str, end=end_str, progress=False)

        if df is None or df.empty:
            return []

        results = []
        # Reset index to get Date column if it's the index
        df = df.reset_index()

        for _, row in df.iterrows():
            # Handle multi-level columns if present (common in yf)
            # But simple download usually returns simple columns
            # We assume simple columns: Date, Open, High, Low, Close, Adj Close, Volume

            # Helper to safely get value
            def get_val(col):
                # Handle multi-index columns returned by yf.download in newer versions
                if isinstance(row.index, tuple):
                    # For multi-index, we need to find the column matching 'col'
                    for idx in row.index:
                        if idx[0] == col:
                            val = row[idx]
                            return (
                                float(val.iloc[0])
                                if isinstance(val, pd.Series)
                                else float(val)
                            )
                val = row[col] if col in row else 0.0
                return float(val.iloc[0]) if isinstance(val, pd.Series) else float(val)

            # Parse Date
            # Also handle multi-index for Date
            date_col_name = "Date"
            if isinstance(row.index, tuple):
                for idx in row.index:
                    if idx[0] == "Date":
                        date_col_name = idx
                        break

            date_val = row[date_col_name] if date_col_name in row else None

            if date_val is None:
                continue

            if not isinstance(date_val, datetime):
                # Ensure it's datetime
                import pandas as pd

                dt = pd.to_datetime(date_val)
                date_val = dt.to_pydatetime()  # type: ignore

            data = OHLCVData(
                ticker=formatted_ticker,
                date=date_val,
                open=get_val("Open"),
                high=get_val("High"),
                low=get_val("Low"),
                close=get_val("Close"),
                volume=int(get_val("Volume")),
                adjusted_close=get_val("Adj Close") if "Adj Close" in row else None,
            )
            results.append(data)

        return results

    @observe(name="Tool:YFinance:FetchPrice")
    def fetch_stock_price(
        self, ticker: str, period: str = "1mo", interval: str = "1d"
    ) -> Dict[str, Any]:
        """Fetch stock price by period and interval."""
        formatted_ticker = self._format_ticker(ticker)
        df = yf.download(
            formatted_ticker, period=period, interval=interval, progress=False
        )
        if df is None or df.empty:
            return {"error": "No data found"}

        # Convert to a basic dictionary list
        df = df.reset_index()
        # Handle multi-index columns from yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Convert dates to string for JSON serialization
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
        formatted_ticker = self._format_ticker(ticker)
        ticker_obj = yf.Ticker(formatted_ticker)
        info = ticker_obj.info

        if not info:
            return {"error": "No fundamental info found"}

        # Extract a curated list of value metrics
        return {
            "ticker": formatted_ticker,
            "name": info.get("shortName", ""),
            "industry": info.get("industry", ""),
            "sector": info.get("sector", ""),
            "marketCap": info.get("marketCap", None),
            "peRatio": info.get("trailingPE", None),
            "forwardPE": info.get("forwardPE", None),
            "pegRatio": info.get("pegRatio", None),
            "priceToBook": info.get("priceToBook", None),
            "debtToEquity": info.get("debtToEquity", None),
            "returnOnEquity": info.get("returnOnEquity", None),
            "profitMargins": info.get("profitMargins", None),
            "revenueGrowth": info.get("revenueGrowth", None),
            "earningsGrowth": info.get("earningsGrowth", None),
            "dividendYield": info.get("dividendYield", None),
            "currentPrice": info.get("currentPrice", None),
            "targetMeanPrice": info.get("targetMeanPrice", None),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh", None),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow", None),
        }

    @observe(name="Tool:YFinance:FetchFinancials")
    def fetch_financial_statements(self, ticker: str) -> Dict[str, Any]:
        formatted_ticker = self._format_ticker(ticker)
        ticker_obj = yf.Ticker(formatted_ticker)

        income_stmt = ticker_obj.financials
        balance_sheet = ticker_obj.balance_sheet
        cash_flow = ticker_obj.cashflow

        def format_df(df):
            if df is None or df.empty:
                return {}
            # Convert timestamp columns to string dates
            df.columns = [
                col.strftime("%Y-%m-%d") if isinstance(col, datetime) else str(col)
                for col in df.columns
            ]
            # Replace NaNs with None for JSON
            import pandas as pd

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
        macros = {
            "NIFTY_50": "^NSEI",
            "INDIA_VIX": "^INDIAVIX",
            "USD_INR": "INR=X",
            "CRUDE_OIL": "CL=F",
            "GOLD": "GC=F",
        }

        results = {}
        for name, ticker in macros.items():
            ticker_obj = yf.Ticker(ticker)
            history = ticker_obj.history(period="1d")
            if not history.empty:
                close_price = history["Close"].iloc[-1]
                if isinstance(close_price, pd.Series):
                    close_price = close_price.iloc[0]
                results[name] = float(close_price)
            else:
                results[name] = None

        return results

    @observe(name="Tool:YFinance:FetchNews")
    def fetch_news(self, ticker: str, limit: int = 10) -> List[NewsArticle]:
        formatted_ticker = self._format_ticker(ticker)
        ticker_obj = yf.Ticker(formatted_ticker)
        news_items = ticker_obj.news

        results = []
        for item in news_items[:limit]:
            # Convert timestamp to datetime
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
