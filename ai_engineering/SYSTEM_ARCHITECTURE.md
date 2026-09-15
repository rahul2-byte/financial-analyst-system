# SYSTEM ARCHITECTURE

## High-Level Flow

User → CLI → Orchestrator → 1. Clarification 2. Human approval 3. Data fetch 4. Quant engine 5. Specialist agents 6. Evidence synthesis 7. Validation 8. Structured report

---

## Layer Separation

1. Data Pipeline Layer
2. Run-artifact layer
3. Quantitative Engine
4. Agent Layer
5. Orchestrator Layer
6. API Layer (optional programmatic client)
7. Terminal Presentation Layer

Each layer must remain isolated.

No cross-layer shortcuts allowed.
