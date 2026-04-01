# Financial Intelligence Platform (FIN-AI)

A production-grade, modular, multi-agent Financial Intelligence Platform designed to provide structured, deterministic, and AI-reasoned financial analysis and investment theses.

---

## 🚀 Overview

FIN-AI is an advanced platform that bridges the gap between raw financial data and human-level reasoning. By utilizing a multi-agent orchestration layer, the system performs deep research, technical analysis, and fundamental evaluation to produce comprehensive, explainable reports.

### Key Pillars
1. **Data Integrity**: All quantitative processing is done deterministically in Python using industry-standard libraries like NumPy and Pandas.
2. **Reasoning Layer**: LLMs are used for synthesis, strategy, and qualitative reasoning, but never for direct mathematical calculations.
3. **Modular Agents**: Each analytical task (Fundamental, Technical, Sentiment, etc.) is handled by a dedicated, stateless agent.
4. **Verification Loop**: A strict verification mechanism cross-checks LLM outputs against raw data to eliminate hallucinations.

---

## 🏗 Architecture

The platform is structured into three distinct layers:

### 1. **Backend** (`backend/`)
Built with **FastAPI**, this is the core engine of the platform.
- **Orchestrator**: Manages the multi-turn agent execution flow.
- **Llama.cpp Integration**: Provides on-demand LLM inference using GGUF models.
- **Quant Engine**: Deterministic Python logic for financial indicators and scanners.
- **Storage**: Hybrid storage utilizing **PostgreSQL** for structured market data and **Qdrant** for vector-based search (News, Filings).

### 2. **Frontend** (`frontend/`)
A high-performance **React/Next.js** application.
- **Interactive Dashboard**: Modern UI for stock analysis and deep research.
- **Streaming UI**: Server-Sent Events (SSE) support for real-time analysis streaming.
- **Visualization**: Professional charting widgets for technical and fundamental metrics.

### 3. **AI Engineering & Governance** (`ai_engineering/`)
The governance layer that defines the system's behavior and ethics.
- **Project Constitution**: Hard rules for AI reasoning and safety.
- **Coding Standards**: Strict guidelines for Python development and typing.

---

## 🤖 Agent Capabilities

| Agent | Responsibility | Output |
| :--- | :--- | :--- |
| **Market Offline** | Local Data Verification | Availability status of cached data |
| **Market Online** | Real-time Data Fetching | Latest OHLCV, Metrics, and Quotes |
| **Web Research** | Contextual Search | News, Regulatory updates, Macro context |
| **Fundamental Analysis** | Valuation & Health | P/E, ROE, Debt/Equity, Value Thesis |
| **Technical Analysis** | Momentum & Trends | RSI, MACD, Trend Reversals |
| **Contrarian Analysis** | Risk & Blindspots | Bearish scenarios and risk assessment |
| **Validation** | Compliance & Truth | Hallucination checks & risk disclosures |

---

## 🛠 Setup & Installation

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- `llama.cpp` compiled locally

### 1. Backend Setup
1. Clone the repository and navigate to the root.
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
4. Configure LLM settings in `backend/config/llm_config.yaml`:
   - Set the absolute path to your `llama-server` binary.
   - Set the absolute path to your `.gguf` model file.
5. Start the backend:
   ```bash
   cd backend
   uvicorn app.main:app --reload --port 8000
   ```

### 2. Frontend Setup
1. Navigate to the `frontend` directory.
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```

### 3. Infrastructure
Start the required services using Docker:
```bash
docker compose -f backend/docker-compose.yml up -d
```
This will spin up **PostgreSQL**, **Qdrant**, and **Phoenix** (for observability).

---

## 🛡 Verification & Standards

To ensure the platform meets its production-grade mandates, run backend checks:
```bash
pytest backend/tests
ruff check backend/
mypy backend/
```

- **Testing**: Run tests using `pytest backend/tests`.
- **Linting**: Ensure PEP8 compliance with `ruff check backend/`.
- **Type Checking**: Run `mypy backend/` for strict typing verification.

---

## 📜 Project Constitution (Excerpts)
- **Rule #1**: LLMs must NEVER perform mathematical computation or ratio calculation.
- **Rule #2**: All components must be modular and replaceable.
- **Rule #3**: One agent = One responsibility.

For full guidelines, see `ai_engineering/PROJECT_CONSTITUTION.md`.
