import storage.sql.models as models


def test_text_chunk_model_schema_fields_present() -> None:
    assert hasattr(
        models, "TextChunk"
    ), "TextChunk model must exist in storage.sql.models"

    TextChunk = models.TextChunk
    assert getattr(TextChunk, "__tablename__", None) == "text_chunks"

    table = getattr(TextChunk, "__table__", None)
    assert table is not None, "TextChunk must be a SQLModel table"

    column_names = {col.name for col in table.columns}
    assert {
        "id",
        "ticker",
        "text",
        "metadata",
        "published_date",
        "embedding",
    }.issubset(column_names)

    embedding_type = table.c.embedding.type
    assert embedding_type.__class__.__name__.lower() == "vector"
    dim = getattr(embedding_type, "dim", getattr(embedding_type, "dimensions", None))
    assert dim == 1024
