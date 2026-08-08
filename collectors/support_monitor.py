"""
Support-page monitoring service.

Connects collectors → multi-hash fingerprints → classifier →
snapshots / page monitors / download assets → discoveries for the pipeline.

Collectors remain thin; this module owns change intelligence.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from database.models import DownloadAsset, PageMonitor, Snapshot
from knowledge.change_detection import (
    ChangeResult,
    PageFingerprint,
    compare_fingerprints,
    extract_fingerprint,
    score_change,
    DEFAULT_SUPPORT_CHANGE_WEIGHTS,
)
from models.schemas import Discovery, Manufacturer, SourceType

logger = logging.getLogger("clank.support_monitor")


class SupportPageMonitor:
    def __init__(
        self,
        session: Session,
        collector_name: str,
        manufacturer: str,
        *,
        ignore_selectors: list[str] | None = None,
        strip_query_params: set[str] | None = None,
        removal_cfg: dict | None = None,
        change_weights: dict | None = None,
    ):
        self.session = session
        self.collector_name = collector_name
        self.manufacturer = manufacturer.lower()
        self.ignore_selectors = ignore_selectors
        self.strip_query_params = strip_query_params
        self.removal_cfg = removal_cfg or {
            "consecutive_not_found_required": 3,
            "confirmation_window_hours": 24,
            "treat_403_as_removed": False,
            "treat_429_as_removed": False,
            "treat_5xx_as_removed": False,
        }
        self.change_weights = change_weights or DEFAULT_SUPPORT_CHANGE_WEIGHTS

    def _get_or_create_monitor(self, url: str, model_number: Optional[str] = None) -> PageMonitor:
        mon = (
            self.session.query(PageMonitor)
            .filter(PageMonitor.source == self.collector_name, PageMonitor.url == url)
            .first()
        )
        if not mon:
            mon = PageMonitor(
                source=self.collector_name,
                url=url,
                manufacturer=self.manufacturer,
                model_number=model_number,
            )
            self.session.add(mon)
            self.session.flush()
        return mon

    def _last_snapshot(self, url: str) -> Optional[Snapshot]:
        return (
            self.session.query(Snapshot)
            .filter(Snapshot.source == self.collector_name, Snapshot.url == url)
            .order_by(Snapshot.fetched_at.desc())
            .first()
        )

    def _fp_from_snapshot(self, snap: Snapshot) -> Optional[PageFingerprint]:
        if not snap.fingerprint_json:
            return None
        data = snap.fingerprint_json
        from knowledge.change_detection import ContentHashes, AssetRef

        hashes = ContentHashes(**data.get("hashes", {}))
        downloads = [AssetRef(**d) for d in data.get("downloads", [])]
        images = [AssetRef(**i) for i in data.get("images", [])]
        return PageFingerprint(
            hashes=hashes,
            title=data.get("title"),
            downloads=downloads,
            images=images,
            model_references=data.get("model_references", []),
            visible_text=data.get("visible_text"),
            content_length=data.get("content_length", 0),
        )

    def _serialize_fp(self, fp: PageFingerprint) -> dict:
        return {
            "hashes": asdict(fp.hashes),
            "title": fp.title,
            "downloads": [asdict(d) for d in fp.downloads],
            "images": [asdict(i) for i in fp.images],
            "model_references": fp.model_references,
            "visible_text": fp.visible_text,
            "content_length": fp.content_length,
        }

    def process_fetch(
        self,
        url: str,
        html: Optional[str],
        status_code: int,
        *,
        model_number: Optional[str] = None,
    ) -> tuple[ChangeResult, Optional[Snapshot], list[Discovery]]:
        """
        Core entry point after a collector fetches a page.

        Returns (change_result, snapshot, discoveries_to_emit).
        """
        mon = self._get_or_create_monitor(url, model_number)
        mon.last_checked = datetime.utcnow()
        mon.last_status = status_code
        discoveries: list[Discovery] = []

        # --- error / removal path ---
        if status_code >= 500 or status_code in (403, 429):
            # transient by default
            result = ChangeResult(
                classifications=["FETCH_ERROR"],
                meaningful=False,
                details={"status_code": status_code},
                hashes=extract_fingerprint(html or "").hashes if html else extract_fingerprint("<html></html>").hashes,
            )
            return result, None, []

        if status_code in (404, 410):
            mon.consecutive_not_found = (mon.consecutive_not_found or 0) + 1
            required = int(self.removal_cfg.get("consecutive_not_found_required", 3))
            if mon.consecutive_not_found >= required and not mon.is_removed:
                mon.is_removed = True
                mon.removed_at = datetime.utcnow()
                result = ChangeResult(
                    classifications=["PAGE_REMOVED"],
                    meaningful=True,
                    details={"status_code": status_code, "consecutive": mon.consecutive_not_found},
                    hashes=extract_fingerprint("<html></html>").hashes,
                )
                # timeline-worthy but no confidence boost for removal itself
                snap = self._store_snapshot(url, None, status_code, result, model_number)
                return result, snap, []
            result = ChangeResult(
                classifications=["FETCH_ERROR"],
                meaningful=False,
                details={"status_code": status_code, "consecutive": mon.consecutive_not_found},
                hashes=extract_fingerprint("<html></html>").hashes,
            )
            return result, None, []

        # success path
        was_removed = mon.is_removed
        mon.consecutive_not_found = 0
        if was_removed:
            mon.is_removed = False
            mon.restored_at = datetime.utcnow()

        fp = extract_fingerprint(
            html or "",
            ignore_selectors=self.ignore_selectors,
            strip_query_params=self.strip_query_params,
        )
        prev_snap = self._last_snapshot(url)
        old_fp = self._fp_from_snapshot(prev_snap) if prev_snap else None

        result = compare_fingerprints(old_fp, fp, status_code=status_code)
        if was_removed:
            result.classifications = ["PAGE_RESTORED"] + [
                c for c in result.classifications if c != "NEW_PAGE"
            ]
            result.meaningful = True

        snap = self._store_snapshot(url, fp, status_code, result, model_number or (
            fp.model_references[0] if fp.model_references else None
        ))

        # Track downloads idempotently
        if result.meaningful:
            self._upsert_downloads(fp, model_number)

        # Emit discoveries only for meaningful intelligence
        if result.meaningful:
            discoveries = self._discoveries_from_result(url, fp, result, model_number)

        return result, snap, discoveries

    def _store_snapshot(
        self,
        url: str,
        fp: Optional[PageFingerprint],
        status_code: int,
        result: ChangeResult,
        model_number: Optional[str],
    ) -> Snapshot:
        hashes = result.hashes
        snap = Snapshot(
            source=self.collector_name,
            url=url,
            content_hash=hashes.content_hash,
            text_hash=hashes.text_hash,
            dom_hash=hashes.dom_hash,
            download_hash=hashes.download_hash,
            image_hash=hashes.image_hash,
            status_code=status_code,
            manufacturer=self.manufacturer,
            model_number=model_number,
            collector=self.collector_name,
            content_length=fp.content_length if fp else None,
            title=fp.title if fp else None,
            classifications=result.classifications,
            meaningful=result.meaningful,
            change_summary=result.details,
            fingerprint_json=self._serialize_fp(fp) if fp else None,
        )
        self.session.add(snap)
        self.session.flush()
        return snap

    def _upsert_downloads(self, fp: PageFingerprint, model_number: Optional[str]) -> None:
        for d in fp.downloads:
            existing = (
                self.session.query(DownloadAsset)
                .filter(
                    DownloadAsset.source == self.collector_name,
                    DownloadAsset.normalized_url == d.normalized_url,
                )
                .first()
            )
            if existing:
                existing.last_seen = datetime.utcnow()
                existing.active = True
                if d.title and not existing.title:
                    existing.title = d.title
                continue
            asset = DownloadAsset(
                source=self.collector_name,
                url=d.url,
                normalized_url=d.normalized_url,
                title=d.title,
                filename=d.filename,
                file_type=d.file_type,
                category=d.category,
            )
            self.session.add(asset)

    def _discoveries_from_result(
        self,
        url: str,
        fp: PageFingerprint,
        result: ChangeResult,
        model_number: Optional[str],
    ) -> list[Discovery]:
        """Turn meaningful changes into Discovery objects for the main pipeline."""
        models = list(fp.model_references)
        if model_number and model_number not in models:
            models.insert(0, model_number)
        if not models:
            # still emit a page-level discovery if NEW_PAGE and we have a model hint
            return []

        weight = score_change(result, self.change_weights)
        out: list[Discovery] = []
        mfr_enum = None
        try:
            mfr_enum = Manufacturer(self.manufacturer)
        except Exception:
            pass

        # marketing name from title heuristics
        marketing = None
        if fp.title:
            # very light: if title contains "Galaxy" / "Pixel" / "OnePlus" / "Nothing"
            for token in ("Galaxy", "Pixel", "OnePlus", "Nothing", "Redmi", "POCO"):
                if token.lower() in fp.title.lower():
                    marketing = fp.title.strip()
                    break

        for model in models:
            raw = {
                "classifications": result.classifications,
                "details": result.details,
                "weight": weight,
                "snapshot_hashes": asdict(result.hashes),
                "_weight": weight,
            }
            out.append(
                Discovery(
                    manufacturer=mfr_enum,
                    model_number=model,
                    marketing_name=marketing,
                    source=self.collector_name,
                    source_type=SourceType.SUPPORT_PAGE,
                    url=url,
                    content_hash=result.hashes.content_hash,
                    raw=raw,
                )
            )
        return out
