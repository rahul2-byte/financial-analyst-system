"""Vector storage client bindings.

Bindings for the configured vector storage implementation.

This project uses Postgres/pgvector while preserving the `IVectorStorage` API.
"""

from __future__ import annotations

from storage.vector.pgvector_storage import PgVectorStorage

__all__ = ["PgVectorStorage"]
