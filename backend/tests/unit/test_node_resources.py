from app.core.node_resources import NodeResources
from storage.vector.client import PgVectorStorage


def test_node_resources_vector_db_is_pgvectorstorage():
    """Verify NodeResources().vector_db is an instance of PgVectorStorage."""
    # Reset singleton state for a clean test
    NodeResources._instance = None

    resources = NodeResources()
    vector_db = resources.vector_db

    assert isinstance(
        vector_db, PgVectorStorage
    ), f"Expected PgVectorStorage, got {type(vector_db)}"
