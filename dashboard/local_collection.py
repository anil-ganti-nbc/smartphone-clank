"""Local collection controller behind the operator Collect surface.

This is orchestration only: every run is built and executed by the canonical
production one-shot registry/lock path (``runtime.run_once.build_targets`` /
``run_target``).  The UI never imports or calls an OEM collector directly, so
scope, maturity, due-checks and cross-process locking keep exactly the meaning
they have for scheduled production runs.

Invariant: nothing here is reachable from a GET handler. ``start()`` is called
only from the explicit POST an operator triggers with the Run button.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

log = logging.getLogger("clank.dashboard.local_collection")

# States in which a further run must be refused. One explicit action = one run.
_BUSY_STATES = frozenset({"queued", "running"})


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
    def __init__(self, settings, session_factory, pipeline, *, project_root,
                 database_url: str | None = None):
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
        # The URL the caller actually wired the dashboard to. Passing it in
        # (rather than re-reading settings.database_url here) is what makes
        # "the UI and the collector use the same database" a checkable
        # property of one wiring step instead of two independent lookups that
        # a chdir or an env change between them could silently separate.
        self.database_url = database_url or settings.database_url
        self._guard = threading.Lock()
        self._state = self._idle_state()

    @staticmethod
    def _idle_state() -> dict:
        return {
            "state": "idle", "source_id": None, "source_label": None,
            "message": "Ready. No collection is running.", "started_at": None,
            "finished_at": None, "duration_seconds": None, "metrics": None,
            "run_id": None, "errors": [],
        }

    @property
    def busy(self) -> bool:
        with self._guard:
            return self._state["state"] in _BUSY_STATES

    def snapshot(self) -> dict:
        with self._guard:
            state = dict(self._state)
        state["busy"] = state["state"] in _BUSY_STATES
        return state

    def sources(self) -> list[dict]:
        """Inventory for the Collect surface: what can be run, and what the
        canonical run history already says about each one.

        Maturity comes from alerts/source_maturity.py — the same fail-closed
        registry that governs notification authority — so this page can never
        present a soak/experimental source as a production one.
        """
        from alerts.source_maturity import source_maturity
        from observability.metrics import CollectorRunRecord

        session = self._session_factory()
        try:
            rows = {}
            for source_id, _ in SMARTPHONE_FIELD_TEST_SOURCES:
                rows[source_id] = (
                    session.query(CollectorRunRecord)
                    .filter(CollectorRunRecord.collector_name == source_id)
                    .order_by(CollectorRunRecord.started_at.desc())
                    .first()
                )
            out = []
            for source_id, label in SMARTPHONE_FIELD_TEST_SOURCES:
                last = rows[source_id]
                out.append({
                    "source_id": source_id,
                    "label": label,
                    "maturity": source_maturity(source_id),
                    "enabled": source_id in self._targets,
                    "interval_minutes": (
                        self._targets[source_id].interval_minutes
                        if source_id in self._targets else None
                    ),
                    "last_status": last.status if last else None,
                    "last_started_at": last.started_at if last else None,
                    "last_duration_ms": last.duration_ms if last else None,
                    "last_run_id": last.id if last else None,
                    "last_candidates": last.candidates_found if last else None,
                    "last_new_devices": last.new_devices if last else None,
                })
            return out
        finally:
            session.close()

    def start(self, source_id: str) -> tuple[bool, dict]:
        """Begin exactly ONE run of one named source. Explicit operator action
        only — nothing on this object is ever reached from a GET handler."""
        labels = dict(SMARTPHONE_FIELD_TEST_SOURCES)
        if source_id not in self._targets:
            return False, {"error": "source_not_allowed", "allowed": list(labels)}
        with self._guard:
            # Busy check and state claim happen under ONE lock acquisition, so
            # two simultaneous button presses cannot both observe "idle" and
            # both spawn a worker.
            if self._state["state"] in _BUSY_STATES:
                return False, {"error": "collection_already_running", **self._state}
            self._state = self._idle_state()
            self._state.update(
                state="queued", source_id=source_id,
                source_label=labels[source_id], message="Collection queued.",
            )
        threading.Thread(target=self._run, args=(source_id,), daemon=True).start()
        return True, self.snapshot()

    def _run(self, source_id: str) -> None:
        from observability.metrics import CollectorRunRecord
        from runtime.run_once import run_target

        monotonic_start = time.monotonic()
        started = datetime.now(timezone.utc).isoformat()
        with self._guard:
            self._state.update(state="running", message="Collecting from the public source…", started_at=started)
        try:
            outcome = run_target(
                self._targets[source_id], self._session_factory,
                self.database_url, force=True,
            )
            session = self._session_factory()
            try:
                row = (
                    session.query(CollectorRunRecord)
                    .filter(CollectorRunRecord.collector_name == source_id)
                    .order_by(CollectorRunRecord.started_at.desc())
                    .first()
                )
                run_id = None if row is None else row.id
                metrics = None if row is None else {
                    "status": row.status, "candidates_found": row.candidates_found,
                    "valid_devices": row.valid_devices, "new_devices": row.new_devices,
                    "updated_devices": row.updated_devices, "resighted": row.resighted,
                    "pages_fetched": row.pages_fetched, "pages_requested": row.pages_requested,
                    "http_requests": row.http_requests, "http_failures": row.http_failures,
                    "parser_failures": row.parser_failures,
                    "evidence_added": row.evidence_added,
                    "duration_ms": row.duration_ms, "notes": row.notes,
                }
            finally:
                session.close()
            errors = []
            if outcome == "already_running":
                state, message = "already_running", "This source is already running in another process."
            elif metrics is None:
                state = "failed"
                message = "Collection ended without a canonical metrics record."
                errors.append(message)
            elif metrics["status"] == "success":
                state = "success"
                message = (
                    f"Collection succeeded: {metrics['candidates_found']} discovered, "
                    f"{metrics['valid_devices']} accepted, {metrics['new_devices']} new."
                )
            else:
                state = metrics["status"] or "failed"
                message = f"Collection finished with status: {state}."
                if metrics.get("notes"):
                    errors.append(str(metrics["notes"]))
                if metrics.get("http_failures"):
                    errors.append(f"{metrics['http_failures']} HTTP failure(s)")
                if metrics.get("parser_failures"):
                    errors.append(f"{metrics['parser_failures']} parser failure(s)")
            with self._guard:
                self._state.update(
                    state=state, message=message, metrics=metrics, run_id=run_id,
                    errors=errors,
                    duration_seconds=round(time.monotonic() - monotonic_start, 1),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
        except Exception as exc:
            # Surfaced, never swallowed: the operator sees the real exception
            # type and message on the Collect page instead of a silent no-op.
            log.exception("local collection failed source=%s", source_id)
            detail = f"{type(exc).__name__}: {exc}"
            with self._guard:
                self._state.update(
                    state="failed", message=f"Collection failed: {detail}",
                    errors=[detail],
                    duration_seconds=round(time.monotonic() - monotonic_start, 1),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
