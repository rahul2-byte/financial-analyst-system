from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.pool import QueuePool
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

POOL_SIZE = 5
MAX_OVERFLOW = 10
POOL_TIMEOUT = 30

_ENGINE = None


def get_engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(
            settings.DATABASE_URL,
            poolclass=QueuePool,
            pool_size=POOL_SIZE,
            max_overflow=MAX_OVERFLOW,
            pool_timeout=POOL_TIMEOUT,
            pool_pre_ping=True,
            echo=False,
        )
    return _ENGINE


def create_tables() -> None:
    SQLModel.metadata.create_all(get_engine())


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = Session(get_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
