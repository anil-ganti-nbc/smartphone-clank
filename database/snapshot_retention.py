"""
Bounded snapshot growth — keep newest N snapshots per (source, url).
Does not delete devices, evidence, or ledger rows.
"""

from __future__ import annotations

import logging
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.models import Snapshot

logger = logging.getLogger("clank.snapshots")


def prune_snapshots(session: Session, max_per_url: int = 20) -> int:
    """
    Delete oldest snapshots beyond max_per_url for each (source, url) pair.
    Returns number of rows deleted.
    """
    if max_per_url < 1:
        return 0
    # Distinct pairs
    pairs = (
        session.query(Snapshot.source, Snapshot.url)
        .group_by(Snapshot.source, Snapshot.url)
        .all()
    )
    deleted = 0
    for source, url in pairs:
        rows = (
            session.query(Snapshot)
            .filter(Snapshot.source == source, Snapshot.url == url)
            .order_by(Snapshot.fetched_at.desc())
            .all()
        )
        for old in rows[max_per_url:]:
            session.delete(old)
            deleted += 1
    if deleted:
        logger.info(f"Pruned {deleted} old snapshot(s) (max_per_url={max_per_url})")
    return deleted
