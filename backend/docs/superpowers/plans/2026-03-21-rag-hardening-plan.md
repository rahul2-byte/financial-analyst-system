# Phase 2: Intelligence & RAG Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Hybrid Search (Vector + Keyword), Temporal Decay, and Self-Correction for the RAG pipeline.

**Architecture:** 
- `QdrantStorage` updated to support full-text indexing and Reciprocal Rank Fusion (RRF).
- `RetrievalAgent` refactored to handle search retries and leverage hybrid results.
- Python-side re-ranking for temporal relevance.

**Tech Stack:** Python 3.11+, Qdrant, NumPy, Pydantic v2.

---

### Task 1: Update Qdrant Client for Hybrid Search

**Files:**
- Modify: `backend/storage/vector/client.py`

- [ ] **Step 1: Add full-text index creation**
Update `_ensure_collection` to create a text index on the `text` payload field.

```python
self.client.create_payload_index(
    collection_name=self.collection_name,
    field_name="text",
    field_schema=models.TextIndexParams(
        type="text",
        tokenizer=models.TokenizerType.WORD,
        min_token_len=2,
        max_token_len=15,
        lowercase=True,
    ),
)
```

- [ ] **Step 2: Implement Hybrid Search & RRF**
Add `hybrid_search` method that runs `client.search` (vector) and `client.scroll` (with keyword filter - actually Qdrant uses `search` with `filter` for text, but for BM25-like behavior we use `search` with a `FullText` filter or `discover`). Wait, Qdrant's keyword search is usually done via filters. I will use a combination of vector search and filtered search.

- [ ] **Step 3: Implement Temporal Decay**
In the re-ranking step, adjust scores based on `metadata['published_date']`.

- [ ] **Step 4: Commit**
```bash
git add backend/storage/vector/client.py
git commit -m "feat(storage): implement hybrid search and temporal decay"
```

---

### Task 2: Refactor Retrieval Agent for Self-Correction

**Files:**
- Modify: `backend/agents/retrieval/agent.py`

- [ ] **Step 1: Update tool to use hybrid search**
Change the `search_vector_db` tool to a more descriptive `search_intelligence_db`.

- [ ] **Step 2: Implement Retry Logic**
If results are poor (e.g., top score < 0.4), the agent should automatically attempt a "broader" search query.

- [ ] **Step 3: Update System Prompt**
Emphasize the importance of recent data and using the hybrid search tool effectively.

- [ ] **Step 4: Commit**
```bash
git add backend/agents/retrieval/agent.py
git commit -m "feat(agent): add self-correction and hybrid search support to retrieval"
```

---

### Task 3: Verification & Performance Tests

**Files:**
- Create: `backend/tests/unit/test_rag_hardening.py`

- [ ] **Step 1: Write unit tests for RRF**
Verify that rank-fusion correctly combines two lists of results.

- [ ] **Step 2: Write unit tests for Temporal Decay**
Verify that more recent documents get a score boost.

- [ ] **Step 3: Run all tests**
```bash
pytest backend/tests/unit/test_rag_hardening.py
```

- [ ] **Step 4: Commit**
```bash
git add backend/tests/unit/test_rag_hardening.py
git commit -m "test(rag): add unit tests for hybrid search and decay"
```
