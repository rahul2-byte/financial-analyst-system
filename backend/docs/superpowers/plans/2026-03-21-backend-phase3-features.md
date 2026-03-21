# Phase 3: Feature Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the platform's analytical capabilities by adding a deterministic Technical Analysis agent and a specialized Contrarian ("Bear Case") agent to provide a balanced investment view.

**Architecture:** 
- Implement a `TechnicalScanner` in `backend/quant/indicators.py` using NumPy/Pandas for RSI, MACD, and Bollinger Bands.
- Create `TechnicalAnalysisAgent` to interpret deterministic technical indicators.
- Create `ContrarianAgent` to search for and synthesize risks and negative trends.
- Update `PlannerAgent` and `PipelineOrchestrator` registry to support these new capabilities.

**Tech Stack:** Python 3.11+, NumPy, Pandas, Pydantic v2.

---

### Task 1: Implement Deterministic Technical Indicators

**Files:**
- Create: `backend/quant/indicators.py`

- [ ] **Step 1: Implement TechnicalScanner class**
Create a class that takes OHLCV data and returns RSI, MACD, and Bollinger Bands.

```python
# backend/quant/indicators.py
import pandas as pd
import numpy as np
from typing import Dict, Any, List

class TechnicalScanner:
    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs)).iloc[-1]

    def scan(self, df: pd.DataFrame) -> Dict[str, Any]:
        # Implement MACD, Bollinger Bands, and RSI
        # Return structured analysis
        pass
```

- [ ] **Step 2: Add unit tests for indicators**
Create `backend/tests/unit/test_indicators.py` to verify mathematical accuracy against known samples.

- [ ] **Step 3: Commit**
```bash
git add backend/quant/indicators.py backend/tests/unit/test_indicators.py
git commit -m "feat(quant): add deterministic technical indicators"
```

---

### Task 2: Create Technical Analysis Agent

**Files:**
- Create: `backend/agents/analysis/technical.py`
- Modify: `backend/agents/orchestration/schemas.py`

- [ ] **Step 1: Define TechnicalAnalysisAgent**
Agent should call `TechnicalScanner` and provide a readable summary of the trend (Bullish/Bearish/Neutral).

- [ ] **Step 2: Update AgentRegistry in Planner prompt**
Add `technical_analysis` to the `SYSTEM_PROMPT` in `planner.py`.

- [ ] **Step 3: Commit**
```bash
git add backend/agents/analysis/technical.py backend/agents/orchestration/planner.py
git commit -m "feat(agent): add technical analysis agent"
```

---

### Task 3: Create Contrarian ("Bear Case") Agent

**Files:**
- Create: `backend/agents/analysis/contrarian.py`

- [ ] **Step 1: Define ContrarianAgent**
This agent's system prompt strictly instructs it to find risks, regulatory issues, and competitive threats. It should use `web_search` and `sentiment_analysis` (or similar) results as context.

- [ ] **Step 2: Update Planner Registry**
Add `contrarian_analysis` to the `PlannerAgent`.

- [ ] **Step 3: Commit**
```bash
git add backend/agents/analysis/contrarian.py backend/agents/orchestration/planner.py
git commit -m "feat(agent): add contrarian analysis agent for risk detection"
```

---

### Task 4: Integrate New Agents into Orchestrator

**Files:**
- Modify: `backend/app/core/orchestrator.py`

- [ ] **Step 1: Register new agents in PipelineOrchestrator**
Initialize and add routing logic for `technical_analysis` and `contrarian_analysis`.

- [ ] **Step 2: Update Synthesis Prompt**
Ensure the synthesis step explicitly weights the Contrarian findings to avoid bias.

- [ ] **Step 3: Commit**
```bash
git add backend/app/core/orchestrator.py
git commit -m "feat(orchestrator): integrate technical and contrarian agents"
```

---

### Task 5: Final Verification

- [ ] **Step 1: End-to-End Test**
Run a query like "Deep analysis of RELIANCE including technicals and risks" and verify all agents trigger.

- [ ] **Step 2: Commit**
```bash
git commit -m "docs: finalize phase 3 implementation"
```
