"""Local field-test collection controller for the existing newsroom UI.

This is orchestration only: every run is built and executed by the canonical
production one-shot registry/lock path.  The UI never imports or calls an OEM
collector directly.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone


SMARTPHONE_FIELD_TEST_SOURCES = (
    ("samsung_us_support_sitemap", "Samsung"),
    ("google_store_category_phones", "Google"),
    ("nothing_products_sitemap", "Nothing"),
    ("oneplus_regional_sitemap", "OnePlus"),
    ("motorola_regional_sitemap", "Motorola"),
    ("honor_global_sitemap", "Honor"),
    ("oppo_global_sitemap", "Oppo"),
    ("realme_regional_sitemap", "Realme"),
)


class LocalCollectionController:
    def __init__(self, settings, session_factory, pipeline, *, project_root):
        from runtime.run_once import build_targets

        allowed = dict(SMARTPHONE_FIELD_TEST_SOURCES)
        targets = build_targets(
            settings, pipeline, session_factory, project_root=project_root,
            run_reason="field_test_manual",
        )
        self._targets = {target.source_id: target for target in targets if target.source_id in allowed}
        missing = set(allowed) - set(self._targets)
        if missing:
            raise RuntimeError(f"field-test source(s) missing from canonical registry: {sorted(missing)}")
        self._settings = settings
        self._session_factory = session_factory
        self._guard = threading.Lock()
        self._state = {
            "state": "idle", "source_id": None, "source_label": None,
            "message": "Ready for manual local collection.", "started_at": None,
            "finished_at": None, "metrics": None,
        }

    def snapshot(self) -> dict:
        with self._guard:
            return dict(self._state)

    def start(self, source_id: str) -> tuple[bool, dict]:
        labels = dict(SMARTPHONE_FIELD_TEST_SOURCES)
        if source_id not in self._targets:
            return False, {"error": "source_not_allowed", "allowed": list(labels)}
        with self._guard:
            if self._state["state"] in {"queued", "running"}:
                return False, {"error": "collection_already_running", **self._state}
            self._state = {
                "state": "queued", "source_id": source_id,
                "source_label": labels[source_id], "message": "Collection queued.",
                "started_at": None, "finished_at": None, "metrics": None,
            }
        threading.Thread(target=self._run, args=(source_id,), daemon=True).start()
        return True, self.snapshot()

    def _run(self, source_id: str) -> None:
        from observability.metrics import CollectorRunRecord
        from runtime.run_once import run_target

        started = datetime.now(timezone.utc).isoformat()
        with self._guard:
            self._state.update(state="running", message="Collecting from the public source…", started_at=started)
        try:
            outcome = run_target(
                self._targets[source_id], self._session_factory,
                self._settings.database_url, force=True,
            )
            session = self._session_factory()
            try:
                row = (
                    session.query(CollectorRunRecord)
                    .filter(CollectorRunRecord.collector_name == source_id)
                    .order_by(CollectorRunRecord.started_at.desc())
                    .first()
                )
                metrics = None if row is None else {
                    "status": row.status, "candidates_found": row.candidates_found,
                    "valid_devices": row.valid_devices, "new_devices": row.new_devices,
                    "updated_devices": row.updated_devices, "resighted": row.resighted,
                    "pages_fetched": row.pages_fetched, "pages_requested": row.pages_requested,
                    "http_failures": row.http_failures, "notes": row.notes,
                }
            finally:
                session.close()
            if outcome == "already_running":
                state, message = "already_running", "This source is already running in another process."
            elif metrics is None:
                state, message = "failed", "Collection ended without a canonical metrics record."
            elif metrics["status"] in {"success"}:
                state = "completed"
                message = "Collection completed. The newsroom has been refreshed."
            else:
                state = metrics["status"] or "failed"
                message = f"Collection finished with status: {state}."
            with self._guard:
                self._state.update(
                    state=state, message=message, metrics=metrics,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
        except Exception as exc:
            with self._guard:
                self._state.update(
                    state="failed", message=f"Collection failed: {type(exc).__name__}: {exc}",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
