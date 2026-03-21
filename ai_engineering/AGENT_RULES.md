# AGENT RULES

## Core Principles

- One agent = one task
- Agents are stateless
- Agents return structured JSON
- Agents do NOT modify database
- Agents do NOT call other agents

---

## Approved Agents

SentimentAgent

- Uses FinBERT
- Only performs sentiment classification

RetrievalAgent

- Uses embedding model + FAISS
- Only retrieves context

ResearchAgent

- Uses primary LLM
- Only synthesizes structured + unstructured data

ValidationAgent

- Applies deterministic scoring logic
- Ensures consistency

---

## Output Schema Format

{
"status": "success | failure",
"data": {},
"errors": null
}

No raw text allowed.
