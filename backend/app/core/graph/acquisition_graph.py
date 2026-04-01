import logging
import json
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from app.core.node_resources import NodeResources, resources
from app.core.orchestration_schemas import DataManifest, DataStatus
from app.core.graph.node_helpers import build_node_success, build_node_error

logger = logging.getLogger(__name__)

async def acquisition_router_node(state: Dict[str, Any], resources: NodeResources) -> Dict[str, Any]:
    """Strict deterministic router for data acquisition."""
    manifest_dict = state.get("data_manifest")
    if not manifest_dict:
        return {"errors": ["Acquisition reached without manifest"]}
    
    manifest = DataManifest.model_validate(manifest_dict)
    missing = [d.dataset_type for d in manifest.datasets if d.status == DataStatus.MISSING]
    
    return {"missing_datasets": missing}

async def fetch_ohlcv_node(state: Dict[str, Any], resources: NodeResources) -> Dict[str, Any]:
    """Fetches OHLCV data."""
    ticker = state.get("data_manifest", {}).get("ticker")
    recommended_range = state.get("data_manifest", {}).get("recommended_range", "1y")
    try:
        data = resources.yf_fetcher.fetch_stock_price(ticker, period=recommended_range)
        # In a real system, we would save to SQL DB here
        resources.sql_db.save_ohlcv(data)
        resources.sql_db.update_cache_index(ticker, "ohlcv", available_range=recommended_range)
        
        # Fix: update manifest status
        manifest = DataManifest.model_validate(state["data_manifest"])
        for d in manifest.datasets:
            if d.dataset_type == "ohlcv":
                d.status = DataStatus.AVAILABLE
        
        return {"fetch_status": "ohlcv_success", "data_manifest": manifest.model_dump()}
    except Exception as e:
        return {"errors": [f"OHLCV fetch failed: {str(e)}"]}

async def fetch_fundamentals_node(state: Dict[str, Any], resources: NodeResources) -> Dict[str, Any]:
    """Fetches fundamental data."""
    ticker = state.get("data_manifest", {}).get("ticker")
    try:
        data = resources.yf_fetcher.fetch_company_fundamentals(ticker)
        resources.sql_db.upsert_fundamentals(data)
        resources.sql_db.update_cache_index(ticker, "fundamentals")
        
        # Fix: update manifest status
        manifest = DataManifest.model_validate(state["data_manifest"])
        for d in manifest.datasets:
            if d.dataset_type == "fundamentals":
                d.status = DataStatus.AVAILABLE
        
        return {"fetch_status": "fundamentals_success", "data_manifest": manifest.model_dump()}
    except Exception as e:
        return {"errors": [f"Fundamentals fetch failed: {str(e)}"]}

def route_acquisition(state: Dict[str, Any]) -> str:
    missing = state.get("missing_datasets", [])
    if "ohlcv" in missing:
        return "fetch_ohlcv"
    if "fundamentals" in missing:
        return "fetch_fundamentals"
    return END

from app.core.graph.graph_state import ResearchGraphState

from functools import partial

def build_acquisition_graph():
    graph = StateGraph(ResearchGraphState)
    
    graph.add_node("router", partial(acquisition_router_node, resources=resources))
    graph.add_node("fetch_ohlcv", partial(fetch_ohlcv_node, resources=resources))
    graph.add_node("fetch_fundamentals", partial(fetch_fundamentals_node, resources=resources))
    
    graph.set_entry_point("router")
    
    graph.add_conditional_edges(
        "router",
        route_acquisition,
        {
            "fetch_ohlcv": "fetch_ohlcv",
            "fetch_fundamentals": "fetch_fundamentals",
            END: END
        }
    )
    
    graph.add_edge("fetch_ohlcv", "router")
    graph.add_edge("fetch_fundamentals", "router")
    
    return graph.compile()
