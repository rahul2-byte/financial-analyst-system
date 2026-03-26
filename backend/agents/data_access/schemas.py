from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class AgentExecutionMode(str, Enum):
    CONTINUE = "continue"
    WAIT_FOR_APPROVAL = "wait_for_approval"
    BRANCH = "branch"
    STOP = "stop"


class CheckDBStatusParams(BaseModel):
    pass  # No parameters needed


class GetDBInfoParams(BaseModel):
    pass


class GetTickerInfoParams(BaseModel):
    ticker: str = Field(..., description="The stock ticker symbol (e.g., 'AAPL').")


class GetOHLCVDataParams(BaseModel):
    ticker: str = Field(..., description="The stock ticker symbol.")
    start_date: Optional[str] = Field(
        None, description="Start date in YYYY-MM-DD format."
    )
    end_date: Optional[str] = Field(None, description="End date in YYYY-MM-DD format.")


class DeleteTickerDataParams(BaseModel):
    ticker: str = Field(..., description="The stock ticker symbol to delete.")


# --- Online Fetching Params ---
class FetchStockPriceParams(BaseModel):
    ticker: str = Field(..., description="The stock ticker symbol (e.g., 'RELIANCE').")
    period: str = Field(
        "1mo", description="Data period (e.g., '1d', '5d', '1mo', '3mo', '1y')."
    )
    interval: str = Field(
        "1d", description="Data interval (e.g., '1m', '15m', '1h', '1d', '1wk')."
    )


class FetchCompanyFundamentalsParams(BaseModel):
    ticker: str = Field(..., description="The stock ticker symbol.")


class FetchFinancialStatementsParams(BaseModel):
    ticker: str = Field(..., description="The stock ticker symbol.")


class FetchMarketNewsParams(BaseModel):
    category: str = Field(
        "general",
        description="Category: 'general', 'markets', 'companies', or 'economy'.",
    )


class FetchMacroIndicatorsParams(BaseModel):
    pass


class AgentResponse(BaseModel):
    status: str = Field(..., description="'success' or 'failure'")
    execution_mode: AgentExecutionMode = Field(
        default=AgentExecutionMode.CONTINUE,
        description="Controls the flow of the entire agent system. CONTINUE=proceed, WAIT_FOR_APPROVAL=ask user, BRANCH=switch agent, STOP=end execution.",
    )
    data: dict = Field(default_factory=dict, description="The returned data payload")
    errors: Optional[List[str]] = Field(None, description="List of errors if any")
