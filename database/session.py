"""
Database session management. SQLite for v0.1, PostgreSQL-ready.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from database.models import Base

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_database_url(database_url: str) -> str:
    """Anchor a *relative* sqlite URL to the project root, once, at wiring time.

    ``config/config.yaml`` ships ``sqlite:///./data/clank.db``, which SQLite
    resolves against the process CWD **at connect time**, not at engine
    construction. That is a real split-brain hazard for this app: importing
    ``runtime.run_once`` performs ``os.chdir(ROOT)`` as an import side effect,
    so a dashboard started from an unrelated directory could open
    ``<launch dir>/data/clank.db`` while the collector it triggers writes to
    ``<repo>/data/clank.db`` — the operator then sees a permanently empty UI
    with no error anywhere.

    Callers that wire a dashboard and a collection controller together resolve
    the URL through here ONCE and hand the same absolute string to both, so
    "the UI and the collector read the same database" is a property of the
    wiring rather than of whatever directory the operator happened to launch
    from. An absolute sqlite URL (what CLANK_DATA_DIR always produces) and any
    non-sqlite URL are returned untouched.

    Deliberately NOT applied inside ``Settings.database_url``: the configured
    default is a documented, tested value and other deployments depend on it
    verbatim.
    """
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return database_url
    raw = database_url[len(prefix):]
    if not raw or raw.startswith(":memory:"):
        return database_url
    path = Path(raw)
    if path.is_absolute():
        return database_url
    return prefix + str((PROJECT_ROOT / path).resolve())


def get_engine(database_url: str, echo: bool = False):
    # Ensure SQLite directory exists
    if database_url.startswith("sqlite"):
        db_path = database_url.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        database_url,
        echo=echo,
        connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
    )

    # Enable foreign keys for SQLite
    if "sqlite" in database_url:
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def init_db(database_url: str, echo: bool = False) -> None:
    engine = get_engine(database_url, echo)
    Base.metadata.create_all(bind=engine)


def get_session_factory(database_url: str, echo: bool = False) -> sessionmaker[Session]:
    engine = get_engine(database_url, echo)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
