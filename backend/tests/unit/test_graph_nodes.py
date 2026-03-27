import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.core.graph_nodes import (
    market_offline_node,
    price_and_fundamentals_node,
    market_news_node,
    macro_indicators_node,
    fundamental_analysis_node,
    technical_analysis_node,
    sentiment_analysis_node,
    macro_analysis_node,
    contrarian_analysis_node,
    retrieval_node,
)


def create_mock_state(ticker: str = "AAPL", query: str = "test") -> dict:
    """Create a mock state for testing stateless nodes."""
    return {
        "user_query": f"Analyze {ticker}",
        "current_step": {
            "step_number": 1,
            "agent": "test_agent",
            "parameters": {
                "ticker": ticker,
                "query": query,
                "raw_data": {"revenue": 1000000, "profit": 500000},
                "ohlcv_data": [
                    {"open": 100, "high": 105, "low": 99, "close": 103, "volume": 1000000}
                ],
                "text": "Stock analysis text",
                "macro_data": {"gdp": 2.5, "inflation": 3.0},
                "market_data": {"pe_ratio": 20.5},
                "sentiment_data": {"score": 0.7},
            },
        },
    }


def extract_metrics_from_tool_registry(result: dict) -> dict:
    """Extract extracted_metrics from tool_registry in node result."""
    tool_registry = result.get("tool_registry", [])
    if tool_registry and len(tool_registry) > 0:
        return tool_registry[0].get("extracted_metrics", {}) if isinstance(tool_registry[0], dict) else {}
    return {}


class TestAutoExtractMetricsCalled:
    """Test that auto_extract_metrics is called in all stateless nodes."""

    @pytest.mark.asyncio
    @patch("app.core.graph_nodes.NodeResources")
    async def test_market_offline_node_extracts_metrics(self, mock_resources):
        mock_instance = MagicMock()
        mock_instance.sql_db.get_ticker_info.return_value = {
            "ticker": "AAPL",
            "price": 150.0,
            "volume": 1000000,
        }
        mock_resources.return_value = mock_instance

        state = create_mock_state()
        result = await market_offline_node(state)

        metrics = extract_metrics_from_tool_registry(result)
        assert metrics != {}, "market_offline_node must call auto_extract_metrics()"
        assert "price" in metrics or "volume" in metrics

    @pytest.mark.asyncio
    @patch("app.core.graph_nodes.NodeResources")
    async def test_price_and_fundamentals_node_extracts_metrics(self, mock_resources):
        mock_instance = MagicMock()
        mock_instance.yf_fetcher.fetch_stock_price.return_value = {
            "current_price": 150.0,
            "change_percent": 1.5,
        }
        mock_instance.yf_fetcher.fetch_company_fundamentals.return_value = {
            "pe_ratio": 25.0,
            "market_cap": 2500000000000,
        }
        mock_resources.return_value = mock_instance

        state = create_mock_state()
        result = await price_and_fundamentals_node(state)

        metrics = extract_metrics_from_tool_registry(result)
        assert metrics != {}, "price_and_fundamentals_node must call auto_extract_metrics()"
        assert "current_price" in metrics or "pe_ratio" in metrics

    @pytest.mark.asyncio
    @patch("app.core.graph_nodes.NodeResources")
    async def test_market_news_node_extracts_metrics(self, mock_resources):
        mock_instance = MagicMock()
        mock_instance.rss_fetcher.fetch_market_news.return_value = [
            {"title": "Test News", "sentiment_score": 0.8}
        ]
        mock_resources.return_value = mock_instance

        state = create_mock_state()
        result = await market_news_node(state)

        metrics = extract_metrics_from_tool_registry(result)
        assert metrics != {}, "market_news_node must call auto_extract_metrics()"
        assert "sentiment_score" in metrics or "0" in metrics

    @pytest.mark.asyncio
    @patch("app.core.graph_nodes.NodeResources")
    async def test_macro_indicators_node_extracts_metrics(self, mock_resources):
        mock_instance = MagicMock()
        mock_instance.yf_fetcher.fetch_macro_indicators.return_value = {
            "gdp_growth": 2.5,
            "inflation_rate": 3.0,
        }
        mock_resources.return_value = mock_instance

        state = create_mock_state()
        result = await macro_indicators_node(state)

        metrics = extract_metrics_from_tool_registry(result)
        assert metrics != {}, "macro_indicators_node must call auto_extract_metrics()"
        assert "gdp_growth" in metrics or "inflation_rate" in metrics

    @pytest.mark.asyncio
    @patch("app.core.graph_nodes.FundamentalScanner")
    @patch("app.core.graph_nodes.NodeResources")
    async def test_fundamental_analysis_node_extracts_metrics(self, mock_resources, mock_scanner):
        mock_instance = MagicMock()
        mock_resources.return_value = mock_instance
        mock_scanner_instance = MagicMock()
        mock_scanner.return_value = mock_scanner_instance
        mock_scanner_instance.scan.return_value = {
            "score": 75.0,
            "pe_ratio": 20.5,
            "debt_equity": 0.5,
        }

        state = create_mock_state()
        result = await fundamental_analysis_node(state)

        metrics = extract_metrics_from_tool_registry(result)
        assert metrics != {}, "fundamental_analysis_node must call auto_extract_metrics()"
        assert "score" in metrics or "pe_ratio" in metrics

    @pytest.mark.asyncio
    @patch("app.core.graph_nodes.TechnicalScanner")
    @patch("app.core.graph_nodes.NodeResources")
    async def test_technical_analysis_node_extracts_metrics(self, mock_resources, mock_scanner):
        mock_instance = MagicMock()
        mock_resources.return_value = mock_instance
        mock_scanner_instance = MagicMock()
        mock_scanner.return_value = mock_scanner_instance
        mock_scanner_instance.scan.return_value = {
            "rsi": 65.0,
            "macd": 1.5,
        }

        state = create_mock_state()
        result = await technical_analysis_node(state)

        metrics = extract_metrics_from_tool_registry(result)
        assert metrics != {}, "technical_analysis_node must call auto_extract_metrics()"
        assert "rsi" in metrics or "macd" in metrics

    @pytest.mark.asyncio
    @patch("app.core.graph_nodes.LlamaCppService")
    @patch("app.core.graph_nodes.NodeResources")
    async def test_sentiment_analysis_node_extracts_metrics(self, mock_resources, mock_llm):
        mock_instance = MagicMock()
        mock_resources.return_value = mock_instance
        mock_instance.llm.generate_message = AsyncMock(
            return_value=MagicMock(content="Positive sentiment")
        )

        state = create_mock_state()
        result = await sentiment_analysis_node(state)

        metrics = extract_metrics_from_tool_registry(result)
        assert metrics != {}, "sentiment_analysis_node must call auto_extract_metrics()"

    @pytest.mark.asyncio
    @patch("app.core.graph_nodes.LlamaCppService")
    @patch("app.core.graph_nodes.NodeResources")
    async def test_macro_analysis_node_extracts_metrics(self, mock_resources, mock_llm):
        mock_instance = MagicMock()
        mock_resources.return_value = mock_instance
        mock_instance.llm.generate_message = AsyncMock(
            return_value=MagicMock(content="Macro analysis complete")
        )

        state = create_mock_state()
        result = await macro_analysis_node(state)

        metrics = extract_metrics_from_tool_registry(result)
        assert metrics != {}, "macro_analysis_node must call auto_extract_metrics()"

    @pytest.mark.asyncio
    @patch("app.core.graph_nodes.LlamaCppService")
    @patch("app.core.graph_nodes.NodeResources")
    async def test_contrarian_analysis_node_extracts_metrics(self, mock_resources, mock_llm):
        mock_instance = MagicMock()
        mock_resources.return_value = mock_instance
        mock_instance.llm.generate_message = AsyncMock(
            return_value=MagicMock(content="Contrarian analysis complete")
        )

        state = create_mock_state()
        result = await contrarian_analysis_node(state)

        metrics = extract_metrics_from_tool_registry(result)
        assert metrics != {}, "contrarian_analysis_node must call auto_extract_metrics()"

    @pytest.mark.asyncio
    @patch("app.core.graph_nodes.NodeResources")
    async def test_retrieval_node_extracts_metrics(self, mock_resources):
        mock_instance = MagicMock()
        mock_instance.vector_db.hybrid_search.return_value = [
            {"score": 0.95, "text": "retrieved text"}
        ]
        mock_resources.return_value = mock_instance

        state = create_mock_state()
        result = await retrieval_node(state)

        metrics = extract_metrics_from_tool_registry(result)
        assert metrics != {}, "retrieval_node must call auto_extract_metrics()"
        assert "score" in metrics or "0" in metrics
