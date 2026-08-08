"""
Persistent Samsung sitemap catalog traversal (oldest-checked-first).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from database.models import SitemapProductUrl, SitemapTraversalState
from collectors.samsung.sitemap_discovery import DiscoveredURL, normalize_url

logger = logging.getLogger("clank.samsung.traversal")

SOURCE_ID = "samsung_us_support_sitemap"


def _now() -> datetime:
    return datetime.utcnow()


def ensure_traversal_state(session: Session, source_id: str = SOURCE_ID) -> SitemapTraversalState:
    st = (
        session.query(SitemapTraversalState)
        .filter(SitemapTraversalState.source_id == source_id)
        .first()
    )
    if not st:
        st = SitemapTraversalState(
            source_id=source_id,
            strategy="oldest_checked_first",
            current_cycle_started_at=_now(),
        )
        session.add(st)
        session.flush()
    return st


def sync_sitemap_urls(
    session: Session,
    urls: Iterable[DiscoveredURL],
    *,
    source_id: str = SOURCE_ID,
    sitemap_body: str | None = None,
) -> SitemapTraversalState:
    """Upsert product URLs from sitemap; mark missing as inactive."""
    st = ensure_traversal_state(session, source_id)
    now = _now()
    seen_norm: set[str] = set()
    sitemap_hash = None
    if sitemap_body:
        sitemap_hash = hashlib.sha256(sitemap_body.encode("utf-8", errors="replace")).hexdigest()[:32]
        st.sitemap_hash = sitemap_hash

    for u in urls:
        nurl = normalize_url(u.url).rstrip("/")
        if not nurl.endswith("/"):
            # consistent key
            pass
        key = nurl.rstrip("/")
        seen_norm.add(key)
        row = (
            session.query(SitemapProductUrl)
            .filter(
                SitemapProductUrl.source_id == source_id,
                SitemapProductUrl.normalized_url == key,
            )
            .first()
        )
        if row:
            row.last_discovered_in_sitemap_at = now
            row.active_in_sitemap = True
            row.product_slug = u.product_slug or row.product_slug
            row.series_hint = u.series or row.series_hint
            row.url = u.url
        else:
            row = SitemapProductUrl(
                source_id=source_id,
                url=u.url,
                normalized_url=key,
                product_slug=u.product_slug,
                series_hint=u.series,
                first_discovered_at=now,
                last_discovered_in_sitemap_at=now,
                active_in_sitemap=True,
            )
            session.add(row)

    # mark removed
    if seen_norm:
        all_rows = (
            session.query(SitemapProductUrl)
            .filter(SitemapProductUrl.source_id == source_id, SitemapProductUrl.active_in_sitemap.is_(True))
            .all()
        )
        for row in all_rows:
            if row.normalized_url not in seen_norm:
                row.active_in_sitemap = False

    st.total_eligible_urls = (
        session.query(SitemapProductUrl)
        .filter(SitemapProductUrl.source_id == source_id, SitemapProductUrl.active_in_sitemap.is_(True))
        .count()
    )
    session.flush()
    return st


def select_urls_to_fetch(
    session: Session,
    *,
    budget: int = 60,
    source_id: str = SOURCE_ID,
    min_refetch_hours: float = 12.0,
    failed_retry_minutes: float = 180.0,
) -> list[SitemapProductUrl]:
    """
    Oldest-checked-first:
    - Never attempted first (ordered by first_discovered_at)
    - Then oldest last_successful_fetch_at past min_refetch
    - Skip URLs still in backoff (next_eligible_fetch_at > now)
    - New sitemap URLs (never attempted) prioritized
    """
    now = _now()
    min_refetch = timedelta(hours=min_refetch_hours)
    rows = (
        session.query(SitemapProductUrl)
        .filter(SitemapProductUrl.source_id == source_id, SitemapProductUrl.active_in_sitemap.is_(True))
        .all()
    )

    eligible: list[SitemapProductUrl] = []
    for r in rows:
        if r.next_eligible_fetch_at and r.next_eligible_fetch_at > now:
            continue
        # never attempted
        if r.last_attempted_at is None:
            eligible.append(r)
            continue
        # failed — respect backoff already via next_eligible
        if r.last_successful_fetch_at is None:
            eligible.append(r)
            continue
        if r.last_successful_fetch_at <= now - min_refetch:
            eligible.append(r)

    def sort_key(r: SitemapProductUrl):
        # never attempted first, then oldest success, then oldest attempt
        never = 0 if r.last_attempted_at is None else 1
        success_ts = r.last_successful_fetch_at or datetime(1970, 1, 1)
        disc_ts = r.first_discovered_at or datetime(1970, 1, 1)
        return (never, success_ts, disc_ts)

    eligible.sort(key=sort_key)
    selected = eligible[: max(0, int(budget))]
    logger.info(
        "traversal select source=%s eligible=%s selected=%s budget=%s",
        source_id,
        len(eligible),
        len(selected),
        budget,
    )
    return selected


def record_attempt(
    session: Session,
    row: SitemapProductUrl,
    *,
    http_status: int,
    result: str,
    content_length: int | None = None,
    content_type: str | None = None,
    model: str | None = None,
    device_id: str | None = None,
    failed_retry_minutes: float = 180.0,
) -> None:
    now = _now()
    row.last_attempted_at = now
    row.attempt_count = (row.attempt_count or 0) + 1
    row.last_http_status = http_status
    row.last_content_length = content_length
    row.last_content_type = content_type
    row.last_result = result
    if model:
        row.last_model_extracted = model
    if device_id:
        row.associated_device_id = device_id

    successish = result in {
        "FETCH_SUCCESS_MODEL_FOUND",
        "FETCH_SUCCESS_NO_MODEL",
        "FETCH_SUCCESS_IRRELEVANT",
    }
    if successish and http_status == 200:
        row.success_count = (row.success_count or 0) + 1
        row.consecutive_failures = 0
        row.last_successful_fetch_at = now
        row.next_eligible_fetch_at = None
    else:
        row.failure_count = (row.failure_count or 0) + 1
        row.consecutive_failures = (row.consecutive_failures or 0) + 1
        # backoff scales with consecutive failures
        mins = failed_retry_minutes * max(1, min(row.consecutive_failures, 6))
        if http_status == 429:
            mins = max(mins, 360)
        if http_status == 403:
            mins = max(mins, 720)
        if http_status == 404:
            mins = max(mins, 24 * 60)
        row.next_eligible_fetch_at = now + timedelta(minutes=mins)


def coverage_report(session: Session, source_id: str = SOURCE_ID) -> dict:
    st = ensure_traversal_state(session, source_id)
    q = session.query(SitemapProductUrl).filter(SitemapProductUrl.source_id == source_id)
    active = q.filter(SitemapProductUrl.active_in_sitemap.is_(True)).all()
    total = len(active)
    attempted = sum(1 for r in active if r.attempt_count and r.attempt_count > 0)
    success = sum(1 for r in active if r.success_count and r.success_count > 0)
    failed = sum(1 for r in active if (r.failure_count or 0) > 0 and (r.success_count or 0) == 0)
    never = sum(1 for r in active if not r.attempt_count)
    models = sum(1 for r in active if r.last_model_extracted)
    no_model = sum(
        1
        for r in active
        if (r.success_count or 0) > 0 and not r.last_model_extracted
    )
    under_backoff = sum(
        1 for r in active if r.next_eligible_fetch_at and r.next_eligible_fetch_at > _now()
    )
    progress = (attempted / total * 100.0) if total else 0.0
    return {
        "source_id": source_id,
        "strategy": st.strategy,
        "sitemap_phone_urls": total,
        "ever_attempted": attempted,
        "successfully_fetched": success,
        "valid_mobile_models": models,
        "no_model_extracted": no_model,
        "failed_only": failed,
        "never_attempted": never,
        "under_backoff": under_backoff,
        "cycle_progress_pct": round(progress, 1),
        "cycles_completed": st.cycles_completed,
        "last_completed_cycle_at": st.last_completed_cycle_at.isoformat() if st.last_completed_cycle_at else None,
        "total_eligible_urls": st.total_eligible_urls,
        "sitemap_hash": st.sitemap_hash,
    }
