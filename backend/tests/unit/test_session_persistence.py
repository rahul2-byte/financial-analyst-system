from app.models.request_models import Message
from finai.session_persistence import SessionPersistence
from finai.session_store import SessionStore


def test_session_persistence_delegates_without_changing_store_format(tmp_path) -> None:
    store = SessionStore(tmp_path / ".finai", "session")
    persistence = SessionPersistence(store)

    persistence.append_message(Message(role="user", content="Analyze INFY"))
    persistence.write_pending({"kind": "approval", "query": "Analyze INFY"})

    assert persistence.load_history() == [Message(role="user", content="Analyze INFY")]
    pending = store.read_pending()
    assert pending is not None
    assert pending["kind"] == "approval"
