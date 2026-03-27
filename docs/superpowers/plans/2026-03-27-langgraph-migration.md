# LangGraph Agent Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the existing agent system to a clean LangGraph architecture with centralized tools, stateless agent functions, error handling, and memory management.

**Architecture:** Incremental migration with 4 phases:
1. Centralize tool execution into a unified ToolRegistry and ToolExecutor node
2. Refactor agent classes to stateless function nodes
3. Add dedicated error_handler_node for resilience
4. Implement memory management for conversation history

**Tech Stack:** LangGraph, Python 3.11+, Pydantic, asyncio

---

## File Structure Overview

### New Files to Create:
- `backend/app/core/tool_registry.py` - Unified tool definitions
- `backend/app/core/tool_executor.py` - Centralized tool execution node
- `backend/app/core/error_handler.py` - Error handling node and utilities
- `backend/app/core/memory.py` - Memory management utilities
- `backend/app/core/graph_builder_v2.py` - Enhanced graph with all improvements
- `backend/tests/integration/test_tool_executor.py` - Tool executor tests
- `backend/tests/integration/test_error_handler.py` - Error handler tests

### Files to Modify:
- `backend/app/core/graph_nodes.py` - Refactor to use tool executor
- `backend/app/core/graph_state.py` - Enhance state schema
- `backend/app/core/graph_builder.py` - Add new nodes
- `backend/agents/base.py` - Deprecate class-based agents
- `backend/agents/data_access/market_offline.py` - Convert to function
- `backend/agents/analysis/fundamental.py` - Convert to function
- `backend/agents/analysis/technical.py` - Convert to function

---

## Phase 1: Centralize Tool Execution

### Task 1: Create Unified Tool Registry

**Files:**
- Create: `backend/app/core/tool_registry.py`
- Test: `backend/tests/unit/test_tool_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_tool_registry.py
import pytest
from app.core.tool_registry import ToolRegistry, ToolDefinition

def test_tool_registry_singleton():
    registry = ToolRegistry()
    assert registry is ToolRegistry()

def test_register_tool():
    registry = ToolRegistry()
    tool_def = ToolDefinition(
        name="test_tool",
        description="Test tool",
        parameters={"type": "object", "properties": {}}
    )
    registry.register("test", tool_def)
    assert "test_tool" in registry.list_tools()

def test_get_tool():
    registry = ToolRegistry()
    tool = registry.get_tool("test_tool")
    assert tool.name == "test_tool"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_tool_registry.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.core.tool_registry'"

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/core/tool_registry.py
from typing import Dict, List, Any, Optional, Callable
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Optional[Callable] = None

class ToolRegistry:
    """Singleton registry for all tools in the system."""
    _instance = None
    _tools: Dict[str, ToolDefinition] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ToolRegistry, cls).__new__(cls)
            cls._instance._tools = {}
        return cls._instance
    
    def register(self, namespace: str, tool: ToolDefinition) -> None:
        full_name = f"{namespace}:{tool.name}" if namespace else tool.name
        self._tools[full_name] = tool
        logger.info(f"Registered tool: {full_name}")
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        return list(self._tools.keys())
    
    def clear(self) -> None:
        self._tools.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_tool_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/tool_registry.py backend/tests/unit/test_tool_registry.py
git commit -m "feat(tools): add ToolRegistry singleton for centralized tool management"
```

### Task 2: Create Tool Executor Node

**Files:**
- Create: `backend/app/core/tool_executor.py`
- Modify: `backend/app/core/graph_nodes.py` (import tool executor)
- Test: `backend/tests/integration/test_tool_executor.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_tool_executor.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.core.tool_executor import ToolExecutorNode, execute_tool_node
from app.core.graph_state import ResearchGraphState

@pytest.mark.asyncio
async def test_tool_executor_routes_to_handler():
    # Create mock tool with handler
    mock_handler = AsyncMock(return_value='{"result": "success"}')
    tool_def = ToolDefinition(
        name="test_tool",
        description="Test",
        parameters={"type": "object"},
        handler=mock_handler
    )
    
    registry = ToolRegistry()
    registry.clear()
    registry.register("test", tool_def)
    
    state = {
        "current_tool": "test:test_tool",
        "tool_args": {"param": "value"},
        "tool_registry": []
    }
    
    result = await execute_tool_node(state)
    assert mock_handler.called
    assert "tool_results" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integration/test_tool_executor.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/core/tool_executor.py
import logging
import json
from typing import Dict, Any, List, Optional
from app.core.graph_state import ResearchGraphState
from app.core.tool_registry import ToolRegistry, ToolDefinition

logger = logging.getLogger(__name__)

class ToolExecutorNode:
    """Node for centralized tool execution."""
    
    def __init__(self):
        self.registry = ToolRegistry()
    
    async def execute(self, state: ResearchGraphState) -> Dict[str, Any]:
        """Execute tools based on current state."""
        current_tool = state.get("current_tool")
        if not current_tool:
            return {"errors": ["No tool specified"]}
        
        tool_def = self.registry.get_tool(current_tool)
        if not tool_def:
            return {"errors": [f"Tool not found: {current_tool}"]}
        
        tool_args = state.get("tool_args", {})
        
        try:
            if tool_def.handler:
                result = await tool_def.handler(tool_args)
                return {
                    "tool_results": [result],
                    "last_tool_output": result
                }
            return {"errors": ["Tool has no handler"]}
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return {"errors": [str(e)]}

# Singleton instance
tool_executor = ToolExecutorNode()

async def execute_tool_node(state: ResearchGraphState) -> Dict[str, Any]:
    """LangGraph node function for tool execution."""
    return await tool_executor.execute(state)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integration/test_tool_executor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/tool_executor.py backend/tests/integration/test_tool_executor.py
git commit -m "feat(tools): add centralized ToolExecutor node"
```

---

## Phase 2: Refactor Agents to Stateless Functions

### Task 3: Convert MarketOfflineAgent to Function Node

**Files:**
- Modify: `backend/agents/data_access/market_offline.py`
- Test: `backend/tests/agents/data_access/test_market_offline_function.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/agents/data_access/test_market_offline_function.py
import pytest
from unittest.mock import AsyncMock, patch
from app.core.graph_nodes import market_offline_node

@pytest.mark.asyncio
async def test_market_offline_node_returns_data():
    state = {
        "user_query": "Check if RELIANCE data is available",
        "plan": {"execution_steps": []},
        "executed_steps": [],
        "agent_outputs": {},
        "tool_registry": []
    }
    
    with patch("app.core.graph_nodes.NodeResources") as mock_resources:
        mock_resources.llm.generate_message = AsyncMock(
            return_value=MagicMock(
                content="Data available",
                tool_calls=[{
                    "function": {
                        "name": "submit_offline_status",
                        "arguments": '{"data_available": true, "summary": "Found"}'
                    }
                }]
            )
        )
        result = await market_offline_node(state)
        assert "agent_outputs" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/agents/data_access/test_market_offline_function.py -v`
Expected: FAIL (function doesn't exist yet)

- [ ] **Step 3: Write implementation in graph_nodes.py**

Add to `backend/app/core/graph_nodes.py`:

```python
async def market_offline_node(state: ResearchGraphState) -> Dict[str, Any]:
    """Stateless function node for MarketOffline agent."""
    resources = NodeResources()
    
    # Get parameters from state (passed from execution step)
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    ticker = params.get("ticker", "")
    
    try:
        # Execute DB query directly (bypass agent class)
        info = resources.sql_db.get_ticker_info(ticker)
        
        return {
            "agent_outputs": {"market_offline": json.dumps(info)},
            "tool_registry": [{
                "tool_name": "market_offline",
                "input_parameters": params,
                "output_data": info,
                "extracted_metrics": {}
            }]
        }
    except Exception as e:
        logger.error(f"MarketOffline node error: {e}")
        return {"errors": [str(e)]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/agents/data_access/test_market_offline_function.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/graph_nodes.py
git commit -m "refactor(agents): convert MarketOfflineAgent to stateless function node"
```

### Task 4: Convert FundamentalAnalysisAgent to Function Node

**Files:**
- Modify: `backend/app/core/graph_nodes.py`
- Test: `backend/tests/agents/analysis/test_fundamental_function.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/agents/analysis/test_fundamental_function.py
import pytest
from app.core.graph_nodes import fundamental_analysis_node

@pytest.mark.asyncio
async def test_fundamental_analysis_node():
    state = {
        "user_query": "Analyze RELIANCE fundamentals",
        "current_step": {
            "parameters": {"ticker": "RELIANCE"}
        },
        "agent_outputs": {},
        "tool_registry": []
    }
    
    result = await fundamental_analysis_node(state)
    assert "agent_outputs" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/agents/analysis/test_fundamental_function.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# Add to graph_nodes.py
async def fundamental_analysis_node(state: ResearchGraphState) -> Dict[str, Any]:
    """Stateless function node for FundamentalAnalysis agent."""
    resources = NodeResources()
    current_step = state.get("current_step", {})
    params = current_step.get("parameters", {})
    ticker = params.get("ticker", "")
    
    try:
        # Get fundamental data (from previous step or fetch)
        raw_data = params.get("raw_data", {})
        
        # Use deterministic scanner
        scanner = FundamentalScanner()
        scan_results = scanner.scan(raw_data)
        
        # Generate thesis using LLM
        prompt = f"Analyze {ticker} with data: {json.dumps(scan_results)}"
        response = await resources.llm.generate_message(
            messages=[Message(role="user", content=prompt)],
            model="mistral-8b"
        )
        
        return {
            "agent_outputs": {"fundamental_analysis": response.content or "Analysis complete"},
            "tool_registry": [{
                "tool_name": "fundamental_analysis",
                "input_parameters": params,
                "output_data": scan_results,
                "extracted_metrics": {}
            }]
        }
    except Exception as e:
        logger.error(f"FundamentalAnalysis node error: {e}")
        return {"errors": [str(e)]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/agents/analysis/test_fundamental_function.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/graph_nodes.py
git commit -m "refactor(agents): convert FundamentalAnalysisAgent to stateless function"
```

---

## Phase 3: Add Error Handler Node

### Task 5: Create Error Handler Node

**Files:**
- Create: `backend/app/core/error_handler.py`
- Modify: `backend/app/core/graph_builder.py` (add error edges)
- Test: `backend/tests/integration/test_error_handler.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_error_handler.py
import pytest
from app.core.error_handler import ErrorHandler, should_retry, get_error_severity

def test_should_retry_retriable_error():
    assert should_retry("Connection timeout") == True

def test_should_retry_non_retriable():
    assert should_retry("Invalid input") == False

def test_error_severity():
    assert get_error_severity("Connection timeout") == "high"
    assert get_error_severity("Invalid input") == "low"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integration/test_error_handler.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# backend/app/core/error_handler.py
import logging
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class ErrorSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

# Errors that should trigger a retry
RETRIABLE_ERRORS = [
    "timeout",
    "connection",
    "network",
    "temporary",
    "rate limit"
]

# Critical errors that should stop execution
CRITICAL_ERRORS = [
    "authentication",
    "authorization",
    "quota exceeded"
]

def should_retry(error_msg: str) -> bool:
    """Determine if an error is retriable."""
    error_lower = error_msg.lower()
    return not any(crit in error_lower for crit in CRITICAL_ERRORS)

def get_error_severity(error_msg: str) -> ErrorSeverity:
    """Determine error severity."""
    error_lower = error_msg.lower()
    if any(crit in error_lower for crit in CRITICAL_ERRORS):
        return ErrorSeverity.CRITICAL
    if any(ret in error_lower for ret in RETRIABLE_ERRORS):
        return ErrorSeverity.HIGH
    return ErrorSeverity.MEDIUM

class ErrorHandler:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
    
    def should_continue(self, errors: list, retry_count: int) -> bool:
        """Determine if execution should continue."""
        if retry_count >= self.max_retries:
            return False
        
        # Check if all errors are retriable
        return all(should_retry(str(e)) for e in errors)
    
    def get_action(self, errors: list, retry_count: int) -> str:
        """Get recommended action: 'retry', 'escalate', or 'end'."""
        if not errors:
            return "continue"
        
        if self.should_continue(errors, retry_count):
            return "retry"
        
        return "end"

async def error_handler_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node for error handling."""
    errors = state.get("errors", [])
    retry_count = state.get("retry_count", 0)
    
    handler = ErrorHandler(max_retries=3)
    action = handler.get_action(errors, retry_count)
    
    if action == "retry":
        logger.info(f"Retrying execution (attempt {retry_count + 1})")
        return {
            "retry_count": retry_count + 1,
            "errors": [],  # Clear errors for retry
            "should_retry": True
        }
    
    logger.error(f"Execution failed with errors: {errors}")
    return {
        "should_retry": False,
        "should_escalate": action == "end",
        "final_report": None
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integration/test_error_handler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/error_handler.py backend/tests/integration/test_error_handler.py
git commit -m "feat(resilience): add ErrorHandler node with retry logic"
```

---

## Phase 4: Implement Memory Management

### Task 6: Enhance Conversation History

**Files:**
- Create: `backend/app/core/memory.py`
- Modify: `backend/app/core/graph_state.py`
- Test: `backend/tests/unit/test_memory.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_memory.py
import pytest
from app.core.memory import ConversationMemory, memory_reducer
from app.core.graph_state import ResearchGraphState

def test_conversation_memory_add():
    memory = ConversationMemory(max_history=5)
    memory.add("user", "Hello")
    memory.add("assistant", "Hi")
    assert len(memory.messages) == 2

def test_memory_reducer_truncates():
    state = {"conversation_history": []}
    new_messages = [{"role": "user", "content": "Test"}] * 10
    
    result = memory_reducer(state, new_messages)
    assert len(result["conversation_history"]) <= 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_memory.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# backend/app/core/memory.py
import logging
from typing import List, Dict, Any, Annotated
from collections import deque
import operator

logger = logging.getLogger(__name__)

class ConversationMemory:
    """Manages conversation history with sliding window."""
    
    def __init__(self, max_history: int = 10):
        self.max_history = max_history
        self.messages: deque = deque(maxlen=max_history)
    
    def add(self, role: str, content: str) -> None:
        """Add a message to memory."""
        self.messages.append({"role": role, "content": content})
    
    def get_history(self) -> List[Dict[str, str]]:
        """Get full conversation history."""
        return list(self.messages)
    
    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()

def memory_reducer(
    left: List[Dict[str, str]], 
    right: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    """LangGraph reducer for conversation history with truncation."""
    combined = list(left) + list(right)
    
    # Sliding window - keep last N messages
    max_history = 10  # Could be made configurable
    if len(combined) > max_history:
        return combined[-max_history:]
    
    return combined
```

- [ ] **Step 4: Update graph_state.py**

```python
# backend/app/core/graph_state.py
from typing import TypedDict, Dict, Any, List, Optional, Annotated
import operator
from app.core.memory import memory_reducer

class ResearchGraphState(TypedDict):
    # ... existing fields ...
    conversation_history: Annotated[List[Dict[str, str]], memory_reducer]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_memory.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/memory.py backend/app/core/graph_state.py
git commit -m "feat(memory): add ConversationMemory with sliding window"
```

---

## Phase 5: Integration and Testing

### Task 7: Build Enhanced Graph

**Files:**
- Create: `backend/app/core/graph_builder_v2.py`
- Test: `backend/tests/integration/test_graph_v2.py`

- [ ] **Step 1: Write integration test**

```python
# backend/tests/integration/test_graph_v2.py
import pytest
from app.core.graph_builder_v2 import build_enhanced_graph

def test_enhanced_graph_compiles():
    graph = build_enhanced_graph()
    assert graph is not None
    assert hasattr(graph, 'ainvoke')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integration/test_graph_v2.py -v`
Expected: FAIL

- [ ] **Step 3: Write enhanced graph builder**

```python
# backend/app/core/graph_builder_v2.py
from langgraph.graph import StateGraph, END
from app.core.graph_state import ResearchGraphState
from app.core.graph_nodes import (
    planner_node,
    execute_level_node,
    synthesis_node,
    verification_node,
    validation_node
)
from app.core.error_handler import error_handler_node
from app.core.tool_executor import execute_tool_node
from agents.orchestration.schemas import PlannerResponseMode

def route_after_planner(state: ResearchGraphState) -> str:
    """Route based on response mode."""
    plan = state.get("plan")
    if not plan:
        return END
    
    response_mode = plan.get("response_mode", PlannerResponseMode.EXECUTE_PLAN)
    
    if response_mode != PlannerResponseMode.EXECUTE_PLAN:
        return END
    
    return "execute_level_node"

def route_after_execution(state: ResearchGraphState) -> str:
    """Route after execution - loop or synthesize."""
    plan = state.get("plan")
    executed_steps = state.get("executed_steps", [])
    
    if not plan:
        return END
    
    execution_steps = plan.get("execution_steps", [])
    
    if len(executed_steps) >= len(execution_steps):
        return "synthesis_node"
    
    return "execute_level_node"

def route_after_verification(state: ResearchGraphState) -> str:
    """Route based on verification result."""
    verification_passed = state.get("verification_passed", False)
    verification_retry_count = state.get("verification_retry_count", 0)
    
    if verification_passed:
        return "validation_node"
    
    if verification_retry_count < 3:
        return "synthesis_node"
    
    return END

def build_enhanced_graph():
    """Build the enhanced LangGraph with all improvements."""
    graph = StateGraph(ResearchGraphState)
    
    # Add all nodes
    graph.add_node("planner", planner_node)
    graph.add_node("execute_level", execute_level_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("verification", verification_node)
    graph.add_node("validation", validation_node)
    graph.add_node("error_handler", error_handler_node)
    
    # Edges
    graph.add_edge("__start__", "planner")
    graph.add_conditional_edges("planner", route_after_planner, {
        "execute_level_node": "execute_level_node",
        END: END
    })
    graph.add_conditional_edges("execute_level", route_after_execution, {
        "synthesis_node": "synthesis_node",
        "execute_level_node": "execute_level_node"
    })
    graph.add_edge("synthesis", "verification")
    graph.add_conditional_edges("verification", route_after_verification, {
        "validation_node": "validation_node",
        "synthesis_node": "synthesis_node",
        END: END
    })
    graph.add_edge("validation", END)
    
    return graph.compile()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integration/test_graph_v2.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/graph_builder_v2.py backend/tests/integration/test_graph_v2.py
git commit -m "feat(graph): add enhanced graph builder v2 with all improvements"
```

### Task 8: Run Full Integration Tests

- [ ] **Step 1: Run all integration tests**

```bash
cd backend && pytest tests/integration/ -v
```

- [ ] **Step 2: Fix any failures**

(Address any issues found during testing)

- [ ] **Step 3: Final commit**

```bash
git add .
git commit -m "test: add full integration tests for LangGraph migration"
```

---

## Summary of Deliverables

| Phase | Task | Files Created/Modified |
|-------|------|----------------------|
| 1 | Tool Registry | `tool_registry.py`, `tool_executor.py` |
| 2 | Agent Functions | `graph_nodes.py` (modified) |
| 3 | Error Handler | `error_handler.py` |
| 4 | Memory | `memory.py`, `graph_state.py` (modified) |
| 5 | Integration | `graph_builder_v2.py`, multiple tests |

---

## Plan Review

Please review this plan and let me know if you want to:
1. Adjust the priority order
2. Add/remove any tasks
3. Change the scope of any phase

**Plan complete and saved to `docs/superpowers/plans/langgraph-migration.md`. Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
