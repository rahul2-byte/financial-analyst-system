"""News helpers for financial data nodes.

This subpackage contains utilities used by `data_fetch_node` for:

- Loading recent news from the vector store.
- Normalizing and deduplicating article payloads.
- Computing cache summary metadata stored in the SQL cache index.
- Building vector chunk metadata.

All functions are behavior-preserving extractions from the legacy
`agents.financial.data.data_fetch_node` module.
"""
