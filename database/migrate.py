"""
Lightweight schema migration for SQLite (Alembic-compatible philosophy without
requiring alembic install for minimal environments).

Tracks version in schema_version table.
create_all remains for disposable demo/test DBs.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

from database.models import Base
from database.models_v03 import SchemaVersion, RegionalSighting, DeviceRelationship, SourceHealth, RejectedCandidate
from entity_resolution.confidence_ledger import ConfidenceLedgerEntry

CURRENT_VERSION = "0.3.0"


def _engine(url: str):
    return create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})


def get_version(url: str) -> Optional[str]:
    engine = _engine(url)
    insp = inspect(engine)
    if "schema_version" not in insp.get_table_names():
        return None
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version FROM schema_version ORDER BY id DESC LIMIT 1")).fetchone()
        return row[0] if row else None


def backup_db(url: str, backup_dir: str = "data/backups") -> Optional[str]:
    if not url.startswith("sqlite:///"):
        return None
    path = url.replace("sqlite:///", "")
    if not Path(path).exists():
        return None
    Path(backup_dir).mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest = str(Path(backup_dir) / f"clank_{stamp}.db")
    shutil.copy2(path, dest)
    return dest


def upgrade(url: str) -> str:
    """Create all tables including v0.3 and stamp version."""
    engine = _engine(url)
    # Ensure parent dir for sqlite
    if url.startswith("sqlite:///"):
        Path(url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    # models_v03 and ledger share Base
    Session = sessionmaker(bind=engine)
    with Session() as session:
        current = session.query(SchemaVersion).order_by(SchemaVersion.id.desc()).first()
        if not current or current.version != CURRENT_VERSION:
            session.add(SchemaVersion(version=CURRENT_VERSION, description="v0.3 production samsung + ledger"))
            session.commit()
    return CURRENT_VERSION


def ensure_v03(url: str) -> str:
    return upgrade(url)
