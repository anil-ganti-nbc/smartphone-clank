"""
Per-source baseline epoch tracker (spec: Wave 1 integration, sections 6-8).

Wave 1 sources are fetched in full on every run (no cursor-based incremental
traversal like Samsung's sitemap collector) — so the deterministic completion
criterion is simply "the first successful run finished", which is honest for
these particular sources (each adapter enumerates its source's entire current
surface in one call) and is recorded explicitly rather than inferred.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from database.models_v03 import SourceBaselineState


class BaselineTracker:
    def __init__(self, session: Session):
        self.session = session

    def _get_or_create(self, source_id: str, manufacturer: str, criterion: str) -> SourceBaselineState:
        state = (
            self.session.query(SourceBaselineState)
            .filter(SourceBaselineState.source_id == source_id)
            .first()
        )
        if state is None:
            state = SourceBaselineState(
                source_id=source_id,
                manufacturer=manufacturer,
                completion_criterion=criterion,
            )
            self.session.add(state)
            self.session.flush()
        return state

    def is_complete(self, source_id: str) -> bool:
        state = (
            self.session.query(SourceBaselineState)
            .filter(SourceBaselineState.source_id == source_id)
            .first()
        )
        return bool(state and state.baseline_completed_at is not None)

    def record_run(
        self,
        source_id: str,
        manufacturer: str,
        *,
        run_succeeded: bool,
        criterion: str = "single_full_enumeration",
    ) -> bool:
        """
        Record one adapter run against this source. Returns True if this run
        just completed the baseline (i.e. it was the first successful run).
        A failed/empty run (run_succeeded=False, e.g. HTTP 403) never marks
        baseline complete — an unstable source must not fake a baseline off a
        broken fetch (spec section 30: HTTP 403 must not produce a false
        "nothing changed"/false-complete conclusion).
        """
        state = self._get_or_create(source_id, manufacturer, criterion)
        now = datetime.utcnow()
        if state.baseline_started_at is None:
            state.baseline_started_at = now
        state.run_count += 1
        state.last_run_at = now

        just_completed = False
        if run_succeeded and state.baseline_completed_at is None:
            state.baseline_completed_at = now
            just_completed = True
        return just_completed
