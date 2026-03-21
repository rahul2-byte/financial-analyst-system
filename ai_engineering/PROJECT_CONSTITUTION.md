# PROJECT CONSTITUTION

## Project Identity

This is a production-grade, modular, multi-agent, multi-LLM Financial Intelligence Platform.

The system:

- Fetches stock data, news, filings, and earnings transcripts
- Processes structured financial data deterministically
- Uses micro-models for classification tasks
- Uses a primary reasoning LLM for synthesis
- Orchestrates agents through a deterministic controller
- Produces structured, explainable financial reports
- Never executes trades
- Never guarantees financial returns

---

## Core Philosophy

Data → Deterministic Processing → AI Reasoning → Deterministic Decision → Visualization

LLM augments reasoning but does not perform computation.

---

## Non-Negotiable Rules

1. LLM must NEVER perform:
   - Mathematical computation
   - Financial ratio calculation
   - Indicator computation
   - Scoring weight calculation
   - Time-series forecasting

2. All computational logic must be implemented in Python.

3. One agent = one responsibility.

4. All components must be modular and replaceable.

5. No architectural drift without explicit approval.

---

## Trigger Logic

UI triggers full pipeline only when user requests:

- Detailed stock analysis
- Investment thesis
- Deep research
- Full breakdown

Otherwise only chat LLM is used.
