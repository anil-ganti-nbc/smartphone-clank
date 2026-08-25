"""
Core intelligence pipeline v0.2:
  Collect → (Normalize) → Knowledge Enrichment → Entity Resolution
  → Aliases → Timeline → Confidence (+ Decay) → Alerts

Collectors stay dumb. Intelligence lives downstream.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from alerts.discord import DiscordAlerter
from collectors import build_collectors
from config.settings import Settings
from database.models import CollectorRun, Device, Evidence
from database.session import session_scope
from entity_resolution.resolver import EntityResolver
from entity_resolution.aliases import AliasResolver
from entity_resolution.timeline import TimelineService
from entity_resolution.decay import ConfidenceDecay
from entity_resolution.confidence_service import ConfidenceService
from observability.metrics import MetricsRecorder, CollectorRunRecord
from entity_resolution.families import FamilyService
from knowledge.enrichment import KnowledgeBase
from models.schemas import Discovery

logger = logging.getLogger("clank.pipeline")


class IntelligencePipeline:
    def __init__(self, settings: Settings, session_factory):
        self.settings = settings
        self.session_factory = session_factory
        self.weights = settings.confidence_weights

        intel = settings.get("intelligence", default={}) or {}
        data_dir = intel.get("knowledge_data_dir", "knowledge/data")
        self.kb = KnowledgeBase(data_dir=data_dir)

        decay_sched = intel.get("decay_schedule")
        schedule = None
        if decay_sched:
            schedule = [(int(d), float(f)) for d, f in decay_sched]
        never = set(intel.get("never_decay_source_types", ["official"]))
        self.decay = ConfidenceDecay(schedule=schedule, never_decay_types=never)
        self.apply_decay = intel.get("apply_decay_on_resolve", True)

        self.alerter = DiscordAlerter(
            webhook_url=settings.discord_webhook,
            min_confidence=settings.get("discord", "min_confidence_for_alert", default=20),
            significant_delta=settings.get("discord", "significant_confidence_delta", default=15),
            enabled=settings.get("discord", "enabled", default=True),
            session_factory=session_factory,
            staging_label=(settings.environment == "staging"),
        )

    def _apply_knowledge(self, device: Device) -> dict:
        """Enrich device fields from knowledge base. Returns bits for alerts."""
        enriched = self.kb.enrich(
            model_number=device.model_number,
            manufacturer=device.manufacturer,
            marketing_name=device.marketing_name,
            codename=device.codename,
        )
        if enriched.family and not device.family_name:
            device.family_name = enriched.family
        if enriched.product_tier and not device.product_tier:
            device.product_tier = enriched.product_tier
        if enriched.variant and not device.variant_label:
            device.variant_label = enriched.variant
        if enriched.possible_launch_month and not device.possible_launch_month:
            device.possible_launch_month = enriched.possible_launch_month
        if enriched.expected_chipset_class and not device.expected_chipset_class:
            device.expected_chipset_class = enriched.expected_chipset_class
        device.knowledge_confidence = enriched.confidence
        return {
            "family": enriched.family,
            "tier": enriched.product_tier,
            "variant": enriched.variant,
            "launch_month": enriched.possible_launch_month,
            "chipset_class": enriched.expected_chipset_class,
            "kb_confidence": enriched.confidence,
        }

    def process_discoveries(self, discoveries: list[Discovery], session: Session) -> tuple[int, int, int, int]:
        """Returns (new_count, updated_count, resighted, dropped_out_of_scope).

        `dropped_out_of_scope` counts discoveries whose manufacturer isn't in
        `self.settings.manufacturers` — this is the exact mechanism behind
        the Motorola incident (docs/wave2/MOTOROLA_CANARY_REPORT.md): a
        validated, adapter-produced candidate can still be silently dropped
        here if the manufacturer allowlist (a config-level gate, independent
        of collectors.wave1.PRODUCTION_OEM_SCOPE) omits it. Callers —
        especially collectors/wave1/staging_pipeline.py's baseline-completion
        logic — must treat a nonzero value here as a signal, not silently
        discard it. See docs/infra/PRODUCTION_SCOPE_AUDIT.md."""
        resolver = EntityResolver(
            session,
            weights=self.weights,
            regional_suffixes=self.settings.get("entity_resolution", "regional_suffixes"),
        )
        aliases = AliasResolver(session)
        timeline = TimelineService(session)
        families = FamilyService(session, knowledge=self.kb)

        new_count = 0
        updated_count = 0
        resighted = 0
        dropped_out_of_scope = 0

        for disc in discoveries:
            if disc.manufacturer and disc.manufacturer.value not in self.settings.manufacturers:
                dropped_out_of_scope += 1
                logger.warning(
                    "process_discoveries: dropping candidate for manufacturer=%s "
                    "(source=%s) — not in settings.manufacturers %s. This is not "
                    "necessarily a bug (deliberately-unconfigured manufacturer), "
                    "but callers must not treat the resulting 0 as ordinary quiet "
                    "success — see docs/infra/PRODUCTION_SCOPE_AUDIT.md.",
                    disc.manufacturer.value if disc.manufacturer else "unknown",
                    disc.source, sorted(self.settings.manufacturers),
                )
                continue

            # Capture pre-resolve confidence if device already exists
            existing = resolver.find_existing(
                (disc.manufacturer.value if disc.manufacturer else "unknown"),
                disc.model_number,
            )
            old_confidence = existing.confidence if existing else 0

            device, is_new, evidence_added = resolver.resolve(disc)

            # Ensure original_weight is set on new evidence
            for ev in device.evidence:
                if getattr(ev, "original_weight", 0) == 0 and ev.confidence_contribution:
                    ev.original_weight = ev.confidence_contribution
                if disc.source_type and str(disc.source_type.value if hasattr(disc.source_type, "value") else disc.source_type) == "official":
                    ev.decays = False

            # Knowledge enrichment
            kb_bits = self._apply_knowledge(device)

            # Aliases
            aliases.ensure_core_aliases(device, source=disc.source)
            if disc.codename:
                aliases.link_codename(device, disc.codename, source=disc.source)
            if disc.marketing_name:
                aliases.register(device, disc.marketing_name, "marketing", source=disc.source, confidence=80)

            # Family
            families.infer_and_attach(device)

            # Timeline (append-only)
            if is_new or evidence_added:
                timeline.add_event(
                    device,
                    event_type=disc.source_type.value if hasattr(disc.source_type, "value") else str(disc.source_type),
                    source=disc.source,
                    title=disc.marketing_name or disc.model_number,
                    url=disc.url,
                    occurred_at=disc.published_at or disc.discovered_at or datetime.utcnow(),
                    meta={"model": disc.model_number},
                )

            # Confidence via central service only
            session.flush()
            conf_svc = ConfidenceService(session, decay=self.decay)
            if evidence_added:
                from database.models import Evidence as EvModel
                weight = 10
                if disc.raw and isinstance(disc.raw.get("_weight"), int) and disc.raw["_weight"] > 0:
                    weight = int(disc.raw["_weight"])
                latest_ev = (
                    session.query(EvModel)
                    .filter(EvModel.device_id == device.id)
                    .order_by(EvModel.first_seen.desc())
                    .first()
                )
                if latest_ev:
                    weight = latest_ev.original_weight or latest_ev.confidence_contribution or weight
                rule = "support_new_page" if is_new else f"evidence:{disc.source}"
                if disc.raw and disc.raw.get("origin_type") == "sitemap":
                    rule = "sitemap_discovery"
                conf_svc.apply(
                    device,
                    rule_id=rule,
                    points=weight,
                    evidence_id=latest_ev.id if latest_ev else None,
                    explanation=f"{rule} from {disc.source}",
                    meta={"source": disc.source, "url": disc.url},
                )
            if self.apply_decay:
                # Update evidence contribution values only; confidence projection stays ledger-based
                self.decay.recompute_device(session, device)

            # Alerts. Idempotency: `is_new`/`evidence_added` are derived from
            # a DB comparison (resolver.resolve()), and device creation +
            # record_alert() commit together in the same session — so a
            # retried/restarted run that reprocesses the same discovery
            # after a successful commit will find the device already exists
            # with unchanged evidence, take neither branch below, and cannot
            # re-fire either alert. No separate dedupe table is needed; this
            # reuses the resolver's own existing device/evidence identity —
            # see tests/wave1/test_alert_semantics.py::test_reprocessing_a_delivered_event_does_not_duplicate_the_alert.
            tl = timeline.get_timeline(device.id)
            if is_new:
                new_count += 1
                session.flush()
                msg_id = self.alerter.alert_new_device(device, timeline=tl, knowledge_bits=kb_bits, session=session,
                                                       source_id=disc.source)
                if msg_id:
                    self.alerter.record_alert(
                        session, device, "new_device",
                        f"New device {device.model_number}", msg_id, payload=kb_bits,
                    )
                logger.info(
                    f"NEW DEVICE: {device.manufacturer} {device.model_number} "
                    f"(conf={device.confidence}, family={device.family_name})"
                )
            elif evidence_added:
                updated_count += 1
                msg_id = self.alerter.alert_device_updated(
                    device, old_confidence=old_confidence, new_source=disc.source, timeline=tl,
                    session=session,
                )
                if msg_id:
                    self.alerter.record_alert(
                        session, device, "confidence_up",
                        f"Evidence from {disc.source}", msg_id,
                    )
                logger.info(
                    f"UPDATED: {device.manufacturer} {device.model_number} "
                    f"{old_confidence} -> {device.confidence}"
                )
            else:
                # Known device, unchanged evidence — re-sight only
                resighted += 1

        return new_count, updated_count, resighted, dropped_out_of_scope

    def run_collector(self, collector, run_reason: str = "production_manual") -> None:
        result, discoveries = collector.run()

        with session_scope(self.session_factory) as session:
            # Ensure metrics tables exist (additive)
            try:
                CollectorRunRecord.__table__.create(bind=session.get_bind(), checkfirst=True)
            except Exception:
                pass
            rec = MetricsRecorder(session)
            ctx = rec.start(collector.name, source_name=getattr(collector, "name", collector.name), run_reason=run_reason)
            ctx.started_at = result.started_at
            ctx.candidates_found = len(discoveries)
            ctx.valid_devices = len(discoveries)
            if result.errors:
                ctx.status = "failed"
                ctx.notes = "; ".join(result.errors)[:500]
                ctx.parser_failures = 1 if discoveries == [] else 0
            else:
                ctx.status = "success"

            new_c, upd_c, resight_c, dropped_c = self.process_discoveries(discoveries, session)
            ctx.new_devices = new_c
            ctx.updated_devices = upd_c
            ctx.evidence_added = new_c + upd_c
            # v0.3.8: wire report counters that were previously always zero
            ctx.meaningful_changes = new_c + upd_c
            ctx.resighted = resight_c
            if dropped_c:
                # See docs/infra/PRODUCTION_SCOPE_AUDIT.md — surfaced, never silent.
                note = f"dropped_out_of_scope={dropped_c}"
                ctx.notes = (ctx.notes + " | " + note) if ctx.notes else note
            # HTTP metrics from collector if available
            http_m = getattr(collector, "_last_http_metrics", None) or {}
            if http_m:
                ctx.pages_requested = int(http_m.get("pages_requested") or 0)
                ctx.pages_fetched = int(http_m.get("pages_fetched") or 0)
                ctx.bytes_downloaded = int(http_m.get("bytes_downloaded") or 0)
                ctx.http_failures = int(http_m.get("http_failures") or 0)
                extra = {
                    "status_counts": http_m.get("status_counts") or {},
                    "selected_urls": http_m.get("selected_urls"),
                }
                import json as _json
                ctx.notes = (ctx.notes or "") + (" | " if ctx.notes else "") + _json.dumps(extra)

            # Legacy CollectorRun row (compat)
            run = CollectorRun(
                collector=result.collector,
                started_at=result.started_at,
                finished_at=result.finished_at,
                duration_seconds=result.duration_seconds,
                discoveries=len(discoveries),
                new_devices=new_c,
                updated_devices=upd_c,
                errors=result.errors or None,
                retries=result.retries,
                success=len(result.errors) == 0,
                run_reason=run_reason,
            )
            session.add(run)

            # Immutable metrics row — every attempt, success or failure
            m = rec.finish(ctx)
            if result.duration_seconds is not None:
                m.duration_ms = int(result.duration_seconds * 1000)
            m.started_at = result.started_at
            m.finished_at = result.finished_at

            # Snapshot retention (bounded growth)
            try:
                from database.snapshot_retention import prune_snapshots
                max_per_url = int(self.settings.get("snapshots", "max_per_url", default=20) or 20)
                prune_snapshots(session, max_per_url=max_per_url)
            except Exception as e:
                logger.debug(f"snapshot prune skipped: {e}")

        logger.info(
            f"[{collector.name}] done — discoveries={len(discoveries)} "
            f"new={new_c} updated={upd_c} resighted={resight_c} "
            f"duration={result.duration_seconds:.1f}s metrics_status={ctx.status} "
            f"pages={getattr(ctx,'pages_fetched',None)}/{getattr(ctx,'pages_requested',None)} "
            f"bytes={getattr(ctx,'bytes_downloaded',None)}"
        )

    def run_once(self, run_reason: str = "production_manual") -> None:
        collectors = build_collectors(self.settings)
        logger.info(f"Running {len(collectors)} collectors")
        for col in collectors:
            try:
                self.run_collector(col, run_reason=run_reason)
            except Exception as e:
                logger.exception(f"Collector {col.name} crashed: {e}")

    def recompute_decay(self) -> int:
        with session_scope(self.session_factory) as session:
            return self.decay.recompute_all(session)
