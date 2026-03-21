# Design Spec: Intelligence & RAG Hardening (Phase 2)

**Date:** 2026-03-21
**Topic:** Hybrid Search, Temporal Decay, and Self-Correction for the Retrieval Agent.
**Status:** Draft

---

## 1. Problem Statement

The current RAG implementation is limited to semantic (vector) search, which often misses specific financial keywords (e.g., ticker symbols, regulatory terms). Additionally, it treats all data equally regardless of age, which is problematic in the fast-moving financial sector. Finally, the retrieval agent lacks the ability to self-correct if the search results are poor.

---

## 2. Goals & Success Criteria

- **Hybrid Search:** Combine Vector search (semantic) and Keyword search (BM25) to improve recall.
- **Temporal Relevance:** Boost recent news/data points in search results.
- **Self-Correction:** Enable the agent to retry searches with adjusted parameters if initial results are unsatisfactory.
- **Accuracy:** Ensure the most relevant and up-to-date context is provided for report synthesis.

---

## 3. Technical Approach

### 3.1 Hybrid Search with Reciprocal Rank Fusion (RRF)
- **Keyword Search:** Add a full-text index to the `text` field in the Qdrant collection.
- **Fusion:** Implement a re-ranking function that combines results from vector search and full-text search.
- **Formula:** $Score(d) = \sum_{r \in R} \frac{1}{k + rank(r, d)}$, where $k=60$ is a constant.

### 3.2 Temporal Decay Scoring
- **Implementation:** Apply a decay factor to the search results based on the `published_date` metadata.
- **Decay Formula:** $Score_{final} = Score_{hybrid} \times e^{-\lambda \times \Delta t}$, where $\Delta t$ is the age of the data in days and $\lambda$ is the decay constant (e.g., $0.1$).
- **Python-side Re-ranking:** To keep implementation simple and flexible, re-ranking will be performed in the `QdrantStorage` client after fetching a larger candidate pool (e.g., top 20 from both vector and keyword search).

### 3.3 Agent Self-Correction Loop
- **Logic:**
    1. Agent performs initial search.
    2. If results are empty OR the top relevance score is below a threshold (e.g., 0.5):
        - The agent generates a broader search query (e.g., removing specific constraints or using synonyms).
        - Retries the search once.
    3. If still no results, the agent explicitly reports "Insufficient Data" rather than guessing.

---

## 4. Implementation Plan

### Task 1: Qdrant Indexing & Hybrid Client
- Modify `backend/storage/vector/client.py` to:
    - Create a full-text index on the `text` field during collection initialization.
    - Add a `hybrid_search` method that performs both vector and text searches.
    - Implement RRF and Temporal Decay in Python.

### Task 2: Refactor Retrieval Agent
- Update `backend/agents/retrieval/agent.py` to:
    - Use the new `hybrid_search` method.
    - Implement the retry logic for low-confidence results.
    - Update system prompt to emphasize temporal accuracy.

### Task 3: Verification & Tests
- Write unit tests for RRF and Temporal Decay logic.
- Add an integration test for the retrieval loop.

---

## 5. Testing Plan

- **Recall Test:** Verify that hybrid search finds documents that vector search misses (e.g., specific rare keywords).
- **Recency Test:** Verify that a more recent document is ranked higher than an older identical document.
- **Retry Test:** Mock empty results and verify the agent attempts a second query.
