"""
Synthetic Samsung lifecycle demo (v0.3).
Uses clearly synthetic models — not production facts.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console
from rich.panel import Panel

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.models import Base, Device, TimelineEvent, Alias
from database.models_v03 import RegionalSighting, DeviceRelationship
from entity_resolution.confidence_ledger import ConfidenceLedger
from entity_resolution.timeline import TimelineService
from entity_resolution.aliases import AliasResolver
from entity_resolution.decay import ConfidenceDecay
from collectors.samsung.model_validator import SamsungModelValidator
from knowledge.enrichment import KnowledgeBase
from models.schemas import Discovery, Manufacturer, SourceType
from entity_resolution.resolver import EntityResolver
from config.settings import load_settings

console = Console()


def run_demo():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_c, _):
        dbapi_c.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    settings = load_settings()
    weights = settings.confidence_weights
    validator = SamsungModelValidator()
    kb = KnowledgeBase()
    ledger = ConfidenceLedger(session)
    timeline = TimelineService(session)
    aliases = AliasResolver(session)
    resolver = EntityResolver(session, weights=weights, regional_suffixes=["B", "U", "N", "W", "U1"])
    decay = ConfidenceDecay()

    def ingest(model: str, source: str, region: str, weight: int, rule: str, marketing: str | None = None, url: str = ""):
        v = validator.validate(model)
        assert v.valid, v
        disc = Discovery(
            manufacturer=Manufacturer.SAMSUNG,
            model_number=v.canonical_model,
            marketing_name=marketing,
            region=region,
            source=source,
            source_type=SourceType.SUPPORT_PAGE,
            url=url or f"https://example.invalid/{model}",
            raw={"_weight": weight, "region": region},
        )
        device, is_new, added = resolver.resolve(disc)
        session.flush()
        if added or is_new:
            entry = ledger.record(
                device,
                rule=rule,
                points=weight,
                evidence_id=device.evidence[-1].id if device.evidence else None,
                explanation=f"{rule} from {source} ({region})",
            )
            timeline.add_event(device, event_type="support_page", source=source, title=marketing or model, url=disc.url)
            aliases.ensure_core_aliases(device, source=source)
            if marketing:
                aliases.register(device, marketing, "marketing", source=source, confidence=80)
            # regional sighting
            existing = (
                session.query(RegionalSighting)
                .filter_by(device_id=device.id, source_id=source, region=region)
                .first()
            )
            if not existing:
                session.add(
                    RegionalSighting(
                        device_id=device.id,
                        source_id=source,
                        region=region,
                        model_as_presented=model,
                        marketing_name=marketing,
                        url=disc.url,
                        evidence_confidence=weight,
                    )
                )
            # enrichment
            en = kb.enrich(device.model_number, "samsung", marketing, None)
            if en.family:
                device.family_name = en.family
            if en.product_tier:
                device.product_tier = en.product_tier
            if en.variant:
                device.variant_label = en.variant
        session.flush()
        return device

    console.print(Panel("Samsung Lifecycle Demo (synthetic fixtures)", style="bold cyan"))

    steps = [
        ("1 Anonymous IN", lambda: ingest("SM-S957B", "samsung_in_support", "IN", 10, "support_new_page")),
        ("2 Same model UK", lambda: ingest("SM-S957B", "samsung_uk_support", "GB", 8, "regional_corroboration")),
        ("3 US variant", lambda: ingest("SM-S957U", "samsung_us_owners_product", "US", 10, "support_new_page")),
        ("4 Distinct model (no unsafe merge)", lambda: ingest("SM-S958B", "samsung_in_support", "IN", 10, "support_new_page")),
        ("5 Manual added", lambda: ingest("SM-S957B", "samsung_in_support", "IN", 18, "download_user_manual")),
        ("6 Marketing name", lambda: ingest(
            "SM-S957B", "samsung_in_support", "IN", 12, "marketing_name_revealed",
            marketing="Galaxy S27 Ultra [synthetic fixture]",
        )),
        ("7 Marketing name second region", lambda: ingest(
            "SM-S957B", "samsung_uk_support", "GB", 8, "marketing_name_corroboration",
            marketing="Galaxy S27 Ultra [synthetic fixture]",
        )),
    ]

    for label, fn in steps:
        d = fn()
        console.print(f"[green]{label}[/green]  → {d.model_number} conf={d.confidence} family={d.family_name}")

    # decay pass
    for d in session.query(Device).all():
        decay.recompute_device(session, d)
    console.print("[yellow]Decay recomputed (official would not decay; support evidence may)[/yellow]")

    console.print()
    console.print(Panel("Device dossiers", style="bold"))
    for d in session.query(Device).order_by(Device.model_number):
        console.print(f"\n[bold]{d.marketing_name or d.model_number}[/bold]")
        console.print(f"  model={d.model_number}  conf={d.confidence}  family={d.family_name}  variant={d.variant_label}  is_variant={d.is_variant}")
        summary = ledger.summary(d)
        for c in summary["contributions"]:
            console.print(f"    ledger +{c['points']:3}  {c['rule']:30}  {c['previous']}→{c['new']}")
        sights = session.query(RegionalSighting).filter_by(device_id=d.id).all()
        for s in sights:
            console.print(f"    sighting {s.region} via {s.source_id}")
        for a in session.query(Alias).filter_by(device_id=d.id):
            console.print(f"    alias [{a.alias_type}] {a.value}")

    console.print("\n[bold green]Lifecycle demo complete (synthetic).[/bold green]")
    session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_demo())
