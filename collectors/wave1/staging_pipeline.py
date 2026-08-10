"""
Orchestrates one Wave1 OEM adapter through the real shared intelligence
pipeline, entirely inside the staging DB.

Every arrow in the required chain (spec section 2) is exercised here:
  adapter.discover() -> validator -> bridge.normalize_wave1_discovery()
  -> IntelligencePipeline.process_discoveries() [entity resolution, aliases,
     families, evidence, ConfidenceService, timeline, alerts]
  -> BaselineTracker (baseline/post-baseline classification, survives restart)
  -> MetricsRecorder (operational metrics)
  -> RejectedCandidate rows for everything that didn't validate

Xiaomi is intentionally never passed to this module in this phase (KEEP_STAGING,
per operator instruction) — its adapter/validator stay exercised only via
tests/wave1/, never baselined into the intelligence DB.

Environment-agnostic by design: this function only knows about a
session_factory, not which database it points at. Callers are responsible
for the environment check before invoking it — main.py's `--environment
staging` path asserts via runtime.environment.assert_db_matches_environment(
..., "staging") at process startup; runtime/daemon.py's production Google
canary asserts (..., "production") before scheduling this against the
production DB, and only for OEMs in collectors.wave1.WAVE1_PRODUCTION_SCOPE.
This module does not re-check either assertion itself.
"""

from __future__ import annotations

import logging

from database.session import session_scope
from models.schemas import Discovery
from observability.metrics import MetricsRecorder
from database.models_v03 import RejectedCandidate

from collectors.wave1.adapter import DiscoveryAdapter
from collectors.wave1.baseline import BaselineTracker
from collectors.wave1.bridge import UnsupportedManufacturerError, UNSUPPORTED_MANUFACTURER, normalize_wave1_discovery
from collectors.wave1.validator import AMBIGUOUS, VALID

logger = logging.getLogger("clank.wave1.staging_pipeline")

VALIDATORS = {}  # populated lazily to avoid import cycles; see _validator_for


def _validator_for(manufacturer: str):
    if not VALIDATORS:
        from collectors.wave1.google.model_validator import validate as v_google
        from collectors.wave1.nothing.model_validator import validate as v_nothing
        from collectors.wave1.oneplus.model_validator import validate as v_oneplus
        from collectors.wave2.motorola.model_validator import validate as v_motorola
        from collectors.wave2.honor.model_validator import validate as v_honor
        from collectors.wave2.oppo.model_validator import validate as v_oppo
        from collectors.wave2.realme.model_validator import validate as v_realme
        VALIDATORS.update({
            "google": v_google, "oneplus": v_oneplus, "nothing": v_nothing,
            # Wave 2 (docs/wave2/) — staging qualification only, never
            # WAVE1_PRODUCTION_SCOPE. Only BUILD_NOW/BUILD_WITH_LIMITS OEMs
            # get an entry here; see docs/wave2/WAVE2_RANKING.md.
            "motorola": v_motorola, "honor": v_honor,
            "oppo": v_oppo, "realme": v_realme,
        })
    return VALIDATORS[manufacturer]


class OEMCycleResult:
    def __init__(self, source_id: str, manufacturer: str):
        self.source_id = source_id
        self.manufacturer = manufacturer
        self.candidates_found = 0
        self.valid = 0
        self.rejected = 0
        self.baseline_just_completed = False
        self.baseline_was_complete_before = False
        self.new_devices = 0
        self.updated_devices = 0
        self.resighted = 0
        self.dropped_out_of_scope = 0
        self.http_failures = 0
        self.pages_fetched = 0
        self.pages_requested = 0
        self.bytes_downloaded = 0
        self.errors: list[str] = []

    def __repr__(self):
        return (
            f"OEMCycleResult({self.source_id}: candidates={self.candidates_found} "
            f"valid={self.valid} rejected={self.rejected} new={self.new_devices} "
            f"updated={self.updated_devices} resighted={self.resighted} "
            f"dropped_out_of_scope={self.dropped_out_of_scope} "
            f"baseline_complete_before={self.baseline_was_complete_before} "
            f"baseline_just_completed={self.baseline_just_completed})"
        )


def run_oem_staging_cycle(adapter: DiscoveryAdapter, pipeline, session_factory, run_reason: str = "wave1_staging") -> OEMCycleResult:
    """
    Run one adapter cycle end to end against the staging DB via `pipeline`
    (an IntelligencePipeline already constructed against session_factory).
    """
    manufacturer = adapter.manufacturer
    source_id = adapter.source_name
    result = OEMCycleResult(source_id, manufacturer)
    validate = _validator_for(manufacturer)

    candidates, adapter_metrics = adapter.discover()
    result.candidates_found = len(candidates)
    result.pages_requested = adapter_metrics.pages_requested
    result.pages_fetched = adapter_metrics.pages_fetched
    result.bytes_downloaded = adapter_metrics.bytes_downloaded
    result.http_failures = adapter_metrics.http_failures
    result.errors = list(adapter_metrics.errors)

    run_succeeded = adapter_metrics.pages_fetched > 0 and adapter_metrics.http_failures == 0

    with session_scope(session_factory) as session:
        tracker = BaselineTracker(session)
        result.baseline_was_complete_before = tracker.is_complete(source_id)

        discoveries: list[Discovery] = []
        for candidate in candidates:
            outcome = validate(candidate.candidate_identifier)
            if outcome.outcome != VALID:
                session.add(RejectedCandidate(
                    source_id=source_id,
                    raw_value=candidate.candidate_identifier[:128],
                    reason=outcome.reason or outcome.outcome,
                    url=candidate.canonical_url or candidate.source_url,
                    category_hint=outcome.outcome,
                ))
                result.rejected += 1
                continue
            try:
                discoveries.append(normalize_wave1_discovery(candidate, outcome))
                result.valid += 1
            except UnsupportedManufacturerError:
                session.add(RejectedCandidate(
                    source_id=source_id,
                    raw_value=candidate.candidate_identifier[:128],
                    reason=UNSUPPORTED_MANUFACTURER,
                    url=candidate.canonical_url or candidate.source_url,
                    category_hint="deferred",
                ))
                result.rejected += 1

        # Baseline gate: every new device from this run is backfill (no
        # newsroom alert) until this source's baseline is already complete
        # BEFORE this run started. This must be evaluated pre-run, not
        # post-run — otherwise the very run that completes baseline would
        # also alert on everything it just imported.
        pipeline.alerter.backfill = not result.baseline_was_complete_before

        rec = MetricsRecorder(session)
        ctx = rec.start(source_id, source_name=source_id, run_reason=run_reason)
        ctx.pages_requested = result.pages_requested
        ctx.pages_fetched = result.pages_fetched
        ctx.bytes_downloaded = result.bytes_downloaded
        ctx.http_failures = result.http_failures
        ctx.candidates_found = result.candidates_found
        ctx.valid_devices = result.valid
        ctx.status = "success" if run_succeeded else ("blocked" if adapter_metrics.http_failures else "partial")
        if result.errors:
            ctx.notes = "; ".join(result.errors)[:500]

        try:
            new_c, upd_c, resight_c, dropped_c = pipeline.process_discoveries(discoveries, session)
        finally:
            # Never leave a shared IntelligencePipeline instance mutated for
            # the next caller (another OEM, or a future non-staging use).
            pipeline.alerter.backfill = False

        result.new_devices = new_c
        result.updated_devices = upd_c
        result.resighted = resight_c
        result.dropped_out_of_scope = dropped_c
        ctx.new_devices = new_c
        ctx.updated_devices = upd_c
        ctx.evidence_added = new_c + upd_c
        ctx.meaningful_changes = new_c + upd_c
        ctx.resighted = resight_c

        # No-silent-drop invariant (docs/infra/PRODUCTION_SCOPE_AUDIT.md,
        # part 6): validated candidates existed but the pipeline accepted
        # none of them. For a production/staging OEM cycle this is
        # suspicious by default — the exact shape of the Motorola incident,
        # where config.yaml's manufacturers allowlist silently dropped every
        # candidate while the source/adapter/validator all looked healthy.
        pipeline_accepted_something = (new_c + upd_c + resight_c) > 0
        silent_drop = result.valid > 0 and not pipeline_accepted_something
        if silent_drop:
            ctx.status = "regression"
            note = (
                f"SILENT_DROP: {result.valid} validated candidate(s) for "
                f"manufacturer={manufacturer} but pipeline accepted 0 "
                f"(new=0 updated=0 resighted=0, dropped_out_of_scope={dropped_c}). "
                "This OEM is very likely missing from settings.manufacturers "
                "— see docs/infra/PRODUCTION_SCOPE_AUDIT.md."
            )
            ctx.notes = (ctx.notes + " | " + note) if ctx.notes else note
            logger.error("wave1_cycle SILENT_DROP source=%s manufacturer=%s valid=%d dropped_out_of_scope=%d",
                         source_id, manufacturer, result.valid, dropped_c)
        rec.finish(ctx)

        # Baseline completion now requires more than "the fetch worked": the
        # pipeline must have actually accepted at least one valid device
        # observation whenever valid candidates existed. A silent drop must
        # never be able to complete a baseline — see part 5,
        # docs/infra/PRODUCTION_SCOPE_AUDIT.md.
        result.baseline_just_completed = tracker.record_run(
            source_id, manufacturer,
            run_succeeded=run_succeeded and not silent_drop,
        )

    logger.info("wave1_cycle %s", result)
    return result
