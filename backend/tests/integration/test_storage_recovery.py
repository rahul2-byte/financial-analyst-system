from pathlib import Path

from finai.session_store import SessionStore


def test_atomic_context_write_leaves_no_temporary_file(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, "session")
    store.write_context({"status": "ok"})

    assert store.read_context() == {"status": "ok"}
    assert not list(store.session_dir.glob("*.tmp"))
