import asyncio
import sys
import os
import json

from app.core.node_resources import resources
from agents.financial.data.data_fetch_node import data_fetch_node

async def main():
    state = {
        "data_status": {},
        "fetched_data": {},
        "data_plan": [
            {"dataset": "ohlcv", "requirements": {"period": "1mo", "interval": "1d"}},
            {"dataset": "fundamentals"},
            {"dataset": "macro"},
            {"dataset": "news", "requirements": {"minimum_items": 3}}
        ],
        "retry_count_by_domain": {},
        "goal": {"ticker": "HDFC.NS", "symbols": ["HDFC.NS"], "objective": "Analyze HDFC bank"},
        "user_query": "Analyze HDFC bank",
        "timeframe_policy": {
            "ohlcv": {"expected_points": 20},
            "news": {"minimum_items": 5, "stale_after_days": 2},
            "fundamentals": {"stale_after_days": 90},
            "macro": {"stale_after_days": 7}
        }
    }
    
    res = await data_fetch_node(state)
    
    print("Data Fetch Output Status:", res["status"])
    print("Fetched Data Keys:", res["fetched_data"].keys())
    
    print("Test finished.")

if __name__ == "__main__":
    sys.path.append("/home/zeek/ML/fin/backend")
    asyncio.run(main())
