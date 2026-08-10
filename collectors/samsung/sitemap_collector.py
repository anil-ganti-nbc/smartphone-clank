"""
Production adapter: Samsung sitemap discovery with persistent traversal.
"""

from __future__ import annotations

import logging
from typing import Any

from collectors.base import BaseCollector
from collectors.samsung.sitemap_discovery import SamsungSitemapDiscovery, normalize_url
from collectors.samsung import traversal as trav
from models.schemas import Discovery, SourceType

logger = logging.getLogger("clank.collectors.samsung_sitemap")


class SamsungSitemapCollector(BaseCollector):
    name = "samsung_us_support_sitemap"
    source_type = SourceType.SUPPORT_PAGE
    capability = "discovery"
    validation_status = "LIVE_VALIDATED"

    def __init__(
        self,
        max_product_fetches: int = 60,
        fixtures_dir: str = "fixtures/samsung",
        use_fixture_sitemap: bool = False,
        min_refetch_hours: float = 12.0,
        failed_retry_minutes: float = 180.0,
        database_url: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.max_product_fetches = max_product_fetches
        self.fixtures_dir = fixtures_dir
        self.use_fixture_sitemap = use_fixture_sitemap
        self.min_refetch_hours = min_refetch_hours
        self.failed_retry_minutes = failed_retry_minutes
        self.database_url = database_url
        self._last_stats: Any = None
        self._last_http_metrics: dict = {}

    def collect(self) -> list[Discovery]:
        from database.session import get_session_factory
        from sqlalchemy.orm import Session

        # Prefer explicit URL; fall back to settings
        db_url = self.database_url
        if not db_url:
            try:
                from config.settings import load_settings
                db_url = load_settings("config/config.yaml").database_url
            except Exception:
                db_url = "sqlite:///./data/clank.db"

        # A collector's collect() runs on every cycle — it must never create
        # or alter schema itself, only refuse with a clear instruction if
        # its tables are missing. See database/schema_guard.py.
        from database.schema_guard import ensure_tables_present_or_refuse, SchemaError
        try:
            ensure_tables_present_or_refuse(
                db_url,
                ["sitemap_product_urls", "sitemap_traversal_state"],
                context="samsung_us_support_sitemap collector",
            )
        except SchemaError as e:
            logger.error("refusing to collect: %s", e)
            return []
        factory = get_session_factory(db_url)

        disc = SamsungSitemapDiscovery(
            user_agent=self.user_agent,
            min_delay=self.min_delay,
            timeout=float(self.timeout),
            max_product_fetches=self.max_product_fetches,
            fixtures_dir=self.fixtures_dir,
        )
        stats = disc.load_sitemap(use_fixture_sitemap=self.use_fixture_sitemap)
        if stats.validation_status == "UNAVAILABLE":
            self._last_stats = stats
            self._last_http_metrics = {
                "pages_requested": stats.pages_requested,
                "pages_fetched": stats.pages_fetched,
                "bytes_downloaded": stats.bytes_downloaded,
                "http_failures": stats.http_failures,
                "status_counts": stats.status_counts,
            }
            return []

        session: Session = factory()
        try:
            trav.sync_sitemap_urls(
                session,
                stats.parsed_urls,
                sitemap_body=stats.sitemap_body,
            )
            selected = trav.select_urls_to_fetch(
                session,
                budget=self.max_product_fetches,
                min_refetch_hours=self.min_refetch_hours,
                failed_retry_minutes=self.failed_retry_minutes,
            )
            targets = [
                (r.url, r.normalized_url, r.product_slug, r.series_hint) for r in selected
            ]
            stats = disc.fetch_product_urls(targets, stats)

            # record per-URL attempts
            st = trav.ensure_traversal_state(session)
            st.last_run_start_cursor = st.cursor_position
            attempted = 0
            succeeded = 0
            failed = 0
            for r in selected:
                fr = stats.fetch_results.get(r.normalized_url) or {}
                result = fr.get("result") or "FETCH_HTTP_ERROR"
                status = int(fr.get("status") or 0)
                models = fr.get("models") or []
                trav.record_attempt(
                    session,
                    r,
                    http_status=status,
                    result=result,
                    content_length=fr.get("bytes"),
                    model=models[0] if models else None,
                    failed_retry_minutes=self.failed_retry_minutes,
                )
                attempted += 1
                if result.startswith("FETCH_SUCCESS"):
                    succeeded += 1
                else:
                    failed += 1

            st.urls_attempted_in_cycle = (st.urls_attempted_in_cycle or 0) + attempted
            st.urls_succeeded_in_cycle = (st.urls_succeeded_in_cycle or 0) + succeeded
            st.urls_failed_in_cycle = (st.urls_failed_in_cycle or 0) + failed
            st.cursor_position = (st.cursor_position or 0) + attempted
            # complete cycle when never_attempted is 0 among active
            cov = trav.coverage_report(session)
            if cov["never_attempted"] == 0 and cov["sitemap_phone_urls"] > 0:
                from datetime import datetime
                st.cycles_completed = (st.cycles_completed or 0) + 1
                st.last_completed_cycle_at = datetime.utcnow()
                st.current_cycle_started_at = datetime.utcnow()
                st.urls_attempted_in_cycle = 0
                st.urls_succeeded_in_cycle = 0
                st.urls_failed_in_cycle = 0
                st.cursor_position = 0
            st.last_run_end_cursor = st.cursor_position
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        self._last_stats = stats
        self._last_http_metrics = {
            "pages_requested": stats.pages_requested,
            "pages_fetched": stats.pages_fetched,
            "bytes_downloaded": stats.bytes_downloaded,
            "http_failures": stats.http_failures,
            "status_counts": stats.status_counts,
            "selected_urls": stats.selected_urls,
            "fetch_results_summary": {
                k: v.get("result") for k, v in (stats.fetch_results or {}).items()
            },
        }
        discoveries = disc.to_pipeline_discoveries(stats)
        logger.info(
            f"[{self.name}] phone_urls={stats.phone_product_urls} selected={stats.selected_urls} "
            f"valid_mobile={stats.valid_mobile} pages_req={stats.pages_requested} "
            f"pages_ok={stats.pages_fetched} bytes={stats.bytes_downloaded}"
        )
        return discoveries
