#!/usr/bin/env python3
"""
Smartphone Intel Clank v0.2
CLI entry point.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import typer
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from config.settings import load_settings
from database.session import get_session_factory, init_db, session_scope
from database.models import Device, CollectorRun, TimelineEvent, Alias, DeviceFamily, HistoricalStat
from pipeline import IntelligencePipeline
from collectors import build_collectors
from runtime.environment import (
    PRODUCTION,
    STAGING,
    Banner,
    assert_db_matches_environment,
    assert_safe_to_destroy,
)


def _resolve_config_path(config: str, environment: str) -> str:
    """--environment staging with the default config path switches to config.staging.yaml."""
    if environment == STAGING and config == "config/config.yaml":
        return "config/config.staging.yaml"
    return config


def _load_environment(config: str, environment: str):
    """Load settings for (config, environment), print the banner, and enforce
    the DB/environment safety guard before anything touches the database."""
    resolved_config = _resolve_config_path(config, environment)
    settings = load_settings(resolved_config)
    assert_db_matches_environment(settings.database_url, environment)
    console.print(Banner(environment, settings.database_url, resolved_config).render())
    return settings

app = typer.Typer(help="Smartphone Intel Clank — Evidence Engine — smartphone intelligence")
console = Console()


def setup_logging(level: str = "INFO", log_file: str = "logs/clank.log"):
    Path("logs").mkdir(exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Console
    rich_handler = RichHandler(console=console, rich_tracebacks=True, markup=True)
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(rich_handler)

    # File
    file_handler = RotatingFileHandler(log_file, maxBytes=10_485_760, backupCount=5)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root.addHandler(file_handler)


@app.command()
def init(
    config: str = typer.Option("config/config.yaml", help="Path to config YAML"),
    environment: str = typer.Option(PRODUCTION, "--environment", help="production | staging"),
):
    """Initialize database and verify configuration."""
    settings = _load_environment(config, environment)
    setup_logging(settings.get("logging", "level", default="INFO"))
    if environment == PRODUCTION:
        # Production schema evolves only through explicit `db init`/`db
        # adopt`/`db upgrade` — never implicitly via create_all() on a normal
        # command. See docs/infra/MIGRATION_AUDIT.md.
        from database.schema_guard import ensure_schema_or_refuse, SchemaError
        try:
            ensure_schema_or_refuse(settings.database_url, context="main.py init")
        except SchemaError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
    else:
        init_db(settings.database_url, echo=settings.get("database", "echo", default=False))
    console.print("[green]Database initialized.[/green]")
    console.print(f"Manufacturers: {', '.join(settings.manufacturers)}")
    collectors = build_collectors(settings)
    console.print(f"Enabled collectors: {len(collectors)}")
    for c in collectors:
        console.print(f"  • {c.name}")
    if environment == STAGING:
        from collectors.wave1 import build_wave1_collectors
        wave1 = build_wave1_collectors(settings)
        console.print(f"Wave 1 (staging-only) collectors: {len(wave1)}")
        for c in wave1:
            console.print(f"  • {c.manufacturer}/{c.source_name} [{c.validation_state}]")


@app.command()
def run(
    config: str = typer.Option("config/config.yaml", help="Path to config YAML"),
    once: bool = typer.Option(False, "--once", help="Run all collectors once and exit"),
    environment: str = typer.Option(PRODUCTION, "--environment", help="production | staging"),
):
    """Start the intelligence pipeline (scheduled or one-shot)."""
    settings = _load_environment(config, environment)
    setup_logging(settings.get("logging", "level", default="INFO"))
    if environment == PRODUCTION:
        from database.schema_guard import ensure_schema_or_refuse, SchemaError
        try:
            ensure_schema_or_refuse(settings.database_url, context="main.py run")
        except SchemaError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
    else:
        init_db(settings.database_url)
    session_factory = get_session_factory(settings.database_url)
    pipeline = IntelligencePipeline(settings, session_factory)

    if once:
        console.print("[bold]Running one-shot collection…[/bold]")
        pipeline.run_once()
        if environment == STAGING:
            from collectors.wave1 import run_wave1_once
            run_wave1_once(settings, session_factory, pipeline=pipeline)
        console.print("[green]Done.[/green]")
        return

    if environment == STAGING:
        console.print("[red]Scheduled daemon mode is production-only. Use --once for staging runs.[/red]")
        raise typer.Exit(1)

    # Production scheduled mode — delegate to runtime.daemon
    # (startup jobs, Python-owned logs, registry-driven collectors)
    console.print("[bold green]Starting production runtime daemon…[/bold green]")
    from collectors import describe_registry
    for row in describe_registry(settings):
        console.print(f"  • {row['collector_id']} ({row['capability']}) [{row['validation_status']}]")
    from runtime.daemon import main as daemon_main
    raise typer.Exit(daemon_main())


@app.command("reset-staging")
def reset_staging(
    config: str = typer.Option("config/config.staging.yaml", help="Path to staging config YAML"),
    confirm: bool = typer.Option(False, "--yes", help="Actually delete the staging database"),
):
    """Destructive reset of the STAGING database only. Refuses anything that isn't a staging path."""
    settings = load_settings(config)
    assert_safe_to_destroy(settings.database_url)
    db_path = Path(settings.database_url.replace("sqlite:///", ""))
    console.print(Banner(STAGING, settings.database_url, config).render())
    if not confirm:
        console.print(f"[yellow]Dry run — pass --yes to actually delete {db_path}[/yellow]")
        raise typer.Exit(0)
    if db_path.exists():
        db_path.unlink()
        console.print(f"[green]Deleted {db_path}[/green]")
    else:
        console.print(f"[yellow]{db_path} did not exist[/yellow]")
    # Staging goes through the same schema_guard path production's `db init`
    # uses (spec: staging convenience must not mean a different
    # schema-creation mechanism) — see docs/infra/MIGRATION_AUDIT.md for why
    # this is create_all-on-empty-db + stamp rather than pure Alembic DDL
    # replay today.
    from database.schema_guard import init_fresh_database
    rev = init_fresh_database(settings.database_url)
    console.print(f"[green]Staging database re-initialized, now at {rev}.[/green]")


@app.command()
def status(config: str = typer.Option("config/config.yaml")):
    """Show current devices and recent collector runs."""
    settings = load_settings(config)
    session_factory = get_session_factory(settings.database_url)

    with session_scope(session_factory) as session:
        devices = session.query(Device).order_by(Device.confidence.desc()).limit(30).all()
        runs = session.query(CollectorRun).order_by(CollectorRun.started_at.desc()).limit(15).all()

    table = Table(title="Tracked Devices (top 30 by confidence)")
    table.add_column("Manufacturer")
    table.add_column("Model")
    table.add_column("Name")
    table.add_column("Conf")
    table.add_column("Evidence")
    table.add_column("First Seen")

    for d in devices:
        sources = ", ".join(sorted({e.source for e in d.evidence}))
        table.add_row(
            d.manufacturer,
            d.model_number,
            d.marketing_name or "—",
            str(d.confidence),
            sources or "—",
            d.first_seen.strftime("%Y-%m-%d") if d.first_seen else "—",
        )
    console.print(table)

    run_table = Table(title="Recent Collector Runs")
    run_table.add_column("Collector")
    run_table.add_column("Started")
    run_table.add_column("Duration")
    run_table.add_column("New")
    run_table.add_column("Updated")
    run_table.add_column("OK")

    for r in runs:
        run_table.add_row(
            r.collector,
            r.started_at.strftime("%m-%d %H:%M") if r.started_at else "—",
            f"{r.duration_seconds:.1f}s" if r.duration_seconds else "—",
            str(r.new_devices),
            str(r.updated_devices),
            "✓" if r.success else "✗",
        )
    console.print(run_table)


@app.command()
def test_alert(config: str = typer.Option("config/config.yaml")):
    """Send a test Discord message (if webhook configured)."""
    settings = load_settings(config)
    from alerts.discord import DiscordAlerter
    alerter = DiscordAlerter(settings.discord_webhook, enabled=True)
    result = alerter._send("**Clank test** — Discord webhook is working.")
    if result:
        console.print("[green]Test alert sent.[/green]")
    else:
        console.print("[red]Failed or webhook not configured. Set DISCORD_WEBHOOK_URL.[/red]")

@app.command()
def timeline(
    model: str = typer.Argument(..., help="Model number, e.g. SM-S957B"),
    config: str = typer.Option("config/config.yaml"),
):
    """Show chronological evidence timeline for a device."""
    settings = load_settings(config)
    session_factory = get_session_factory(settings.database_url)
    from entity_resolution.timeline import TimelineService

    with session_scope(session_factory) as session:
        device = (
            session.query(Device)
            .filter(Device.model_number == model.upper())
            .first()
        )
        if not device:
            console.print(f"[red]No device found for {model}[/red]")
            raise typer.Exit(1)
        svc = TimelineService(session)
        events = svc.get_timeline(device.id)

    console.print(f"[bold]{device.marketing_name or device.model_number}[/bold]  ({device.model_number})")
    console.print(f"Manufacturer: {device.manufacturer}  |  Confidence: {device.confidence}  |  Family: {device.family_name or '—'}")
    console.print()
    table = Table(title="Timeline")
    table.add_column("Date")
    table.add_column("Source")
    table.add_column("Type")
    table.add_column("URL")
    for ev in events:
        table.add_row(
            ev.occurred_at.strftime("%Y-%m-%d") if ev.occurred_at else "—",
            ev.source or "—",
            ev.event_type or "—",
            (ev.url[:60] + "…") if ev.url and len(ev.url) > 60 else (ev.url or "—"),
        )
    console.print(table)


@app.command()
def inspect(
    model: str = typer.Argument(..., help="Model number"),
    config: str = typer.Option("config/config.yaml"),
):
    """What do we know about this device? Full intelligence view."""
    settings = load_settings(config)
    session_factory = get_session_factory(settings.database_url)

    with session_scope(session_factory) as session:
        device = (
            session.query(Device)
            .filter(Device.model_number == model.upper())
            .first()
        )
        if not device:
            console.print(f"[red]No device found for {model}[/red]")
            raise typer.Exit(1)

        aliases = session.query(Alias).filter(Alias.device_id == device.id).all()
        events = (
            session.query(TimelineEvent)
            .filter(TimelineEvent.device_id == device.id)
            .order_by(TimelineEvent.occurred_at)
            .all()
        )

    console.print(f"[bold cyan]{device.marketing_name or device.model_number}[/bold cyan]")
    console.print(f"Model:          {device.model_number}")
    console.print(f"Manufacturer:   {device.manufacturer}")
    console.print(f"Codename:       {device.codename or '—'}")
    console.print(f"Family:         {device.family_name or '—'}")
    console.print(f"Tier:           {device.product_tier or '—'}")
    console.print(f"Variant:        {device.variant_label or device.region or '—'}")
    console.print(f"Launch month:   {device.possible_launch_month or '—'}")
    console.print(f"Chipset class:  {device.expected_chipset_class or '—'}")
    console.print(f"Confidence:     {device.confidence}  (base {getattr(device, 'base_confidence', '—')})")
    console.print(f"KB confidence:  {device.knowledge_confidence or '—'}")
    console.print(f"First seen:     {device.first_seen}")
    console.print(f"Last seen:      {device.last_seen}")
    console.print()
    console.print("[bold]Aliases[/bold]")
    for a in aliases:
        console.print(f"  [{a.alias_type}] {a.value}")
    console.print()
    console.print("[bold]Evidence[/bold]")
    for e in device.evidence:
        console.print(
            f"  {e.source:20}  weight={e.confidence_contribution:3}  "
            f"(orig {getattr(e, 'original_weight', e.confidence_contribution)})  "
            f"{e.first_seen.strftime('%Y-%m-%d') if e.first_seen else ''}"
        )
    console.print()
    console.print("[bold]Timeline[/bold]")
    for ev in events:
        console.print(f"  {ev.occurred_at.strftime('%Y-%m-%d') if ev.occurred_at else '?'}  {ev.source or ev.event_type}")


@app.command("family")
def family_cmd(
    name: str = typer.Argument(..., help="Family name or model number to look up"),
    config: str = typer.Option("config/config.yaml"),
):
    """Show device family tree."""
    settings = load_settings(config)
    session_factory = get_session_factory(settings.database_url)

    with session_scope(session_factory) as session:
        fam = (
            session.query(DeviceFamily)
            .filter(DeviceFamily.name.ilike(f"%{name}%"))
            .first()
        )
        if not fam:
            # try via device
            device = session.query(Device).filter(Device.model_number == name.upper()).first()
            if device and device.explicit_family_id:
                fam = session.query(DeviceFamily).filter(DeviceFamily.id == device.explicit_family_id).first()
        if not fam:
            console.print(f"[red]No family found for {name}[/red]")
            raise typer.Exit(1)

        from entity_resolution.families import FamilyService
        tree = FamilyService(session).family_tree(fam.id)

    console.print(f"[bold]{tree.get('family')}[/bold]  ({tree.get('manufacturer')})")
    console.print(f"Tier: {tree.get('tier') or '—'}")
    console.print()
    for m in tree.get("members", []):
        console.print(
            f"  {m['model']:16}  {m.get('marketing') or '—':24}  "
            f"var={m.get('variant') or '—':12}  conf={m['confidence']}"
        )


@app.command()
def decay(
    config: str = typer.Option("config/config.yaml"),
):
    """Recompute confidence decay across all devices."""
    settings = load_settings(config)
    setup_logging(settings.get("logging", "level", default="INFO"))
    init_db(settings.database_url)
    session_factory = get_session_factory(settings.database_url)
    pipeline = IntelligencePipeline(settings, session_factory)
    n = pipeline.recompute_decay()
    console.print(f"[green]Decay recomputed for {n} devices.[/green]")


@app.command()
def stats(config: str = typer.Option("config/config.yaml")):
    """Show historical statistics (when available)."""
    settings = load_settings(config)
    session_factory = get_session_factory(settings.database_url)
    with session_scope(session_factory) as session:
        rows = session.query(HistoricalStat).order_by(HistoricalStat.metric).all()
        device_count = session.query(Device).count()
        evidence_count = session.query(Device).count()  # placeholder; real count via join if needed

    console.print(f"Tracked devices: {device_count}")
    if not rows:
        console.print("[yellow]No historical stats computed yet.[/yellow]")
        console.print("Stats accumulate as devices reach official announcement.")
        return
    table = Table(title="Historical Stats")
    table.add_column("Manufacturer")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_column("Samples")
    for r in rows:
        table.add_row(r.manufacturer or "all", r.metric, f"{r.value:.1f}", str(r.sample_size))
    console.print(table)


@app.command()
def snapshots(
    model: str = typer.Argument(..., help="Model number"),
    config: str = typer.Option("config/config.yaml"),
):
    """List stored snapshots for a model."""
    settings = load_settings(config)
    session_factory = get_session_factory(settings.database_url)
    from database.models import Snapshot
    with session_scope(session_factory) as session:
        rows = (
            session.query(Snapshot)
            .filter(Snapshot.model_number == model.upper())
            .order_by(Snapshot.fetched_at.desc())
            .limit(30)
            .all()
        )
    if not rows:
        console.print(f"[yellow]No snapshots for {model}[/yellow]")
        return
    table = Table(title=f"Snapshots · {model}")
    table.add_column("ID", max_width=10)
    table.add_column("Fetched")
    table.add_column("Status")
    table.add_column("Meaningful")
    table.add_column("Classifications")
    for s in rows:
        table.add_row(
            s.id[:8],
            s.fetched_at.strftime("%Y-%m-%d %H:%M") if s.fetched_at else "—",
            str(s.status_code or "—"),
            "yes" if s.meaningful else "no",
            ", ".join(s.classifications or []),
        )
    console.print(table)


@app.command()
def diff(
    old_id: str = typer.Argument(..., help="Old snapshot id (prefix ok)"),
    new_id: str = typer.Argument(..., help="New snapshot id (prefix ok)"),
    config: str = typer.Option("config/config.yaml"),
):
    """Readable diff between two snapshots."""
    settings = load_settings(config)
    session_factory = get_session_factory(settings.database_url)
    from database.models import Snapshot
    from knowledge.change_detection import compare_fingerprints, PageFingerprint, ContentHashes, AssetRef

    def load_snap(prefix: str):
        with session_scope(session_factory) as session:
            s = session.query(Snapshot).filter(Snapshot.id.startswith(prefix)).first()
            if not s:
                return None
            return s

    old_s = load_snap(old_id)
    new_s = load_snap(new_id)
    if not old_s or not new_s:
        console.print("[red]Snapshot not found[/red]")
        raise typer.Exit(1)

    def to_fp(s):
        data = s.fingerprint_json or {}
        hashes = ContentHashes(**data.get("hashes", {"content_hash": s.content_hash}))
        downloads = [AssetRef(**d) for d in data.get("downloads", [])]
        images = [AssetRef(**i) for i in data.get("images", [])]
        return PageFingerprint(
            hashes=hashes,
            title=data.get("title") or s.title,
            downloads=downloads,
            images=images,
            model_references=data.get("model_references", []),
            visible_text=data.get("visible_text"),
            content_length=data.get("content_length") or 0,
        )

    result = compare_fingerprints(to_fp(old_s), to_fp(new_s))
    console.print(f"Classifications: {result.classifications}")
    console.print(f"Meaningful: {result.meaningful}")
    d = result.details
    if d.get("new_downloads"):
        console.print("[green]Meaningful changes:[/green]")
        for x in d["new_downloads"]:
            console.print(f"  + {x.get('title')} ({x.get('category')})")
    if d.get("new_images"):
        for x in d["new_images"]:
            if x.get("category") == "product_render":
                console.print(f"  + product image: {x.get('alt') or x.get('url')}")
    if d.get("title", {}).get("new"):
        console.print(f"  + title → {d['title'].get('new')}")
    if "FORMAT_ONLY" in result.classifications or "NO_CHANGE" in result.classifications:
        console.print("[yellow]Ignored changes:[/yellow] formatting / analytics / no material delta")


@app.command()
def changes(
    model: str = typer.Argument(...),
    config: str = typer.Option("config/config.yaml"),
):
    """Show meaningful change history for a model."""
    settings = load_settings(config)
    session_factory = get_session_factory(settings.database_url)
    from database.models import Snapshot
    with session_scope(session_factory) as session:
        rows = (
            session.query(Snapshot)
            .filter(Snapshot.model_number == model.upper(), Snapshot.meaningful == True)  # noqa
            .order_by(Snapshot.fetched_at)
            .all()
        )
    if not rows:
        console.print(f"[yellow]No meaningful changes recorded for {model}[/yellow]")
        return
    for s in rows:
        console.print(
            f"{s.fetched_at.strftime('%Y-%m-%d %H:%M') if s.fetched_at else '?'}  "
            f"{', '.join(s.classifications or [])}"
        )


# ---------------------------------------------------------------------------
# v0.3 Samsung production commands
# ---------------------------------------------------------------------------

samsung_app = typer.Typer(help="Samsung production collector")
app.add_typer(samsung_app, name="samsung")

db_app = typer.Typer(help="Database migrations")
app.add_typer(db_app, name="db")


@db_app.command("version")
def db_version(config: str = typer.Option("config/config.yaml")):
    """Deprecated — use `db current`. Kept for backward compatibility."""
    from database.migrate import get_version
    settings = load_settings(config)
    v = get_version(settings.database_url)
    console.print(f"[yellow]Deprecated, use `db current`.[/yellow] Legacy schema version: {v or '(none)'}")


@db_app.command("current")
def db_current(config: str = typer.Option("config/config.yaml")):
    """Alembic revision this database is actually stamped at."""
    from database.schema_guard import current_revision, head_revision
    settings = load_settings(config)
    cur = current_revision(settings.database_url)
    head = head_revision(settings.database_url)
    status = "[green]up to date[/green]" if cur == head else "[yellow]BEHIND HEAD[/yellow]" if cur else "[red]NOT STAMPED[/red]"
    console.print(f"Database:  {settings.database_url}")
    console.print(f"Current:   {cur or '(none)'}")
    console.print(f"Head:      {head}")
    console.print(f"Status:    {status}")


@db_app.command("history")
def db_history(config: str = typer.Option("config/config.yaml")):
    """Full Alembic revision history (not DB-specific — this is the migration lineage)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config(str(Path(__file__).resolve().parent / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    for rev in script.walk_revisions():
        console.print(f"  {rev.revision}  <-  {rev.down_revision or '(base)'}   {rev.doc}")


@db_app.command("check")
def db_check(config: str = typer.Option("config/config.yaml")):
    """Non-mutating: exits 0 if schema is up to date, 1 otherwise. Safe to run
    before a scheduled collection cycle without risk of side effects."""
    from database.schema_guard import ensure_schema_or_refuse, SchemaError
    settings = load_settings(config)
    try:
        ensure_schema_or_refuse(settings.database_url, context="db check")
        console.print("[green]Schema up to date.[/green]")
    except SchemaError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@db_app.command("init")
def db_init(config: str = typer.Option("config/config.yaml")):
    """New database only: create the file, build full schema, stamp at head,
    verify. Refuses if the database already has tables — use `db adopt` for
    those. See database/schema_guard.py::init_fresh_database for exactly why
    this isn't pure Alembic DDL replay yet (10 tables have no migration
    history — docs/infra/MIGRATION_AUDIT.md)."""
    from pathlib import Path as _Path
    from database.schema_guard import init_fresh_database, SchemaError
    settings = load_settings(config)
    url = settings.database_url
    if url.startswith("sqlite"):
        db_path = _Path(url.replace("sqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        rev = init_fresh_database(url)
    except SchemaError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Initialized empty database, now at {rev}.[/green]")


@db_app.command("adopt")
def db_adopt(
    config: str = typer.Option("config/config.yaml"),
    revision: str = typer.Option("0006_run_provenance", help="Revision to verify shape against and stamp to"),
    yes: bool = typer.Option(False, "--yes", help="Actually stamp (dry run otherwise)"),
):
    """Existing, unstamped database whose tables already look right: verify
    shape, create only genuinely-missing tables via known-safe CREATE-only
    DDL (never touches an existing table), back up, then stamp. Never blindly
    stamps head — the operator names the revision they've verified matches."""
    from database.migrate import backup_db
    from database.schema_guard import verify_schema_shape, create_missing_tables_safely, stamp, current_revision
    settings = load_settings(config)
    url = settings.database_url

    already = current_revision(url)
    if already:
        console.print(f"[yellow]Already stamped at {already} — nothing to adopt.[/yellow]")
        raise typer.Exit(0)

    shape = verify_schema_shape(url, revision)
    console.print(f"Expected tables (through {revision}): {len(shape.tables_expected)}")
    console.print(f"Missing: {shape.tables_missing or '(none)'}")

    if not yes:
        console.print("[yellow]Dry run — pass --yes to create missing tables (safe, CREATE-only) and stamp.[/yellow]")
        raise typer.Exit(0)

    b = backup_db(url)
    if b:
        console.print(f"Backup: {b}")

    created = create_missing_tables_safely(url, revision)
    if created:
        console.print(f"Created (previously missing, empty, safe): {created}")

    recheck = verify_schema_shape(url, revision)
    if not recheck.matches:
        console.print(f"[red]Refusing to stamp — still missing after safe-create: {recheck.tables_missing}[/red]")
        raise typer.Exit(1)

    stamp(url, revision)
    console.print(f"[green]Stamped {url} at {revision}.[/green]")


@db_app.command("upgrade")
def db_upgrade(config: str = typer.Option("config/config.yaml")):
    """Alembic is the sole migration authority — see docs/infra/MIGRATION_AUDIT.md.
    Backs up, applies pending revisions in order, verifies, reports the
    revision transition. Refuses (via db_adopt's own guard) rather than
    guessing if the database was never stamped — run `db adopt` first."""
    from database.migrate import backup_db
    from database.schema_guard import current_revision, head_revision, upgrade_to_head, SchemaError
    settings = load_settings(config)
    url = settings.database_url

    before = current_revision(url)
    if before is None:
        console.print(
            "[red]Database is not stamped with any Alembic revision. "
            "Run `python main.py db adopt` (existing DB) or `python main.py db init` (new DB) first.[/red]"
        )
        raise typer.Exit(1)

    head = head_revision(url)
    if before == head:
        console.print(f"[green]Already up to date at {before}.[/green]")
        raise typer.Exit(0)

    b = backup_db(url)
    if b:
        console.print(f"Backup: {b}")
    after = upgrade_to_head(url)
    console.print(f"[green]Upgraded {before} -> {after}[/green]")


@db_app.command("backup")
def db_backup(config: str = typer.Option("config/config.yaml")):
    from database.migrate import backup_db
    settings = load_settings(config)
    b = backup_db(settings.database_url)
    if b:
        console.print(f"[green]Backup written: {b}[/green]")
    else:
        console.print("[yellow]No sqlite file to backup (or DB missing)[/yellow]")


production_app = typer.Typer(help="Effective production scope / config provenance")
app.add_typer(production_app, name="production")


@production_app.command("scope")
def production_scope_cmd(config: str = typer.Option("config/config.yaml")):
    """Show the effective production scope, config provenance, and collector registry."""
    from collectors import build_collectors, production_scope, describe_registry

    settings = load_settings(config)
    root = Path(__file__).resolve().parent

    summary = settings.effective_source_summary()
    console.print("[bold]Config provenance[/bold]")
    console.print(f"  repo defaults: {summary['repo_defaults']}")
    console.print(f"  local override: {summary['local_override'] or '(none — running on tracked defaults)'}")
    console.print(f"  production.samsung_only: {summary['production_samsung_only']}")

    scope = production_scope(settings, project_root=root)
    console.print()
    console.print("[bold]Production scope[/bold]")
    if scope is None:
        console.print("  [yellow]UNRESTRICTED — production.samsung_only is false[/yellow]")
    else:
        for c in sorted(scope):
            console.print(f"  • {c}")

    console.print()
    console.print("[bold]Live collector registry[/bold]")
    for row in describe_registry(settings, project_root=root):
        console.print(f"  RUNNING  {row['collector_id']:32} {row['capability']:12} {row['validation_status']}")

    collectors_cfg = settings.get("collectors", default={}) or {}
    all_known = set(collectors_cfg.keys()) | (scope or set())
    running_ids = {c.name for c in build_collectors(settings, project_root=root)}
    for cid in sorted(all_known - running_ids):
        console.print(f"  skipped  {cid}")


@production_app.command("validate")
def production_validate_cmd(config: str = typer.Option("config/config.yaml")):
    """Config <-> registry <-> runtime consistency for every Wave1/Wave2 OEM.

    The operator's single command for proving production scope is coherent
    (docs/infra/PRODUCTION_SCOPE_AUDIT.md Part 7) — this is the same check
    runtime/daemon.py runs at startup (and refuses to start on failure), run
    here read-only for diagnosis. Exits non-zero on any mismatch."""
    from collectors.wave1 import validate_production_scope, ADAPTER_REGISTRY

    settings = load_settings(config)
    result = validate_production_scope(settings)

    console.print("[bold]OEM        approved configured adapter enabled scheduled status[/bold]")
    all_known = sorted(set(ADAPTER_REGISTRY.keys()) | {s.oem for s in result.statuses})
    by_oem = {s.oem: s for s in result.statuses}
    for oem in all_known:
        s = by_oem.get(oem)
        if s is None:
            continue

        def yn(b: bool) -> str:
            return "YES" if b else " NO"

        status = "OK" if s.ok else ("STAGING_ONLY" if not s.approved else "MISMATCH")
        color = "green" if s.ok else ("dim" if not s.approved else "red")
        console.print(
            f"[{color}]{oem:<10} {yn(s.approved):>8} {yn(s.manufacturer_configured):>10} "
            f"{yn(s.adapter_registered):>7} {yn(s.config_enabled):>7} {yn(s.scheduled):>9} {status}[/{color}]"
        )

    console.print()
    if result.ok:
        console.print("[bold green]Production scope: OK — no mismatches[/bold green]")
    else:
        console.print("[bold red]Production scope: MISMATCH[/bold red]")
        console.print(result.render())
        raise typer.Exit(code=1)


discord_app = typer.Typer(help="Discord webhook delivery (newsroom + maintenance)")
app.add_typer(discord_app, name="discord")

discord_test_app = typer.Typer(help="Send synthetic test webhook deliveries")
discord_app.add_typer(discord_test_app, name="test")


def _parse_iso(value):
    from datetime import datetime
    return datetime.fromisoformat(value) if value else None


def _channel_counts(session, channel: str) -> dict:
    from alerts.delivery import channel_summary
    return channel_summary(session, channel, test_mode=False)


@discord_app.command("status")
def discord_status(config: str = typer.Option("config/config.yaml")):
    """Show webhook configuration + delivery health for both channels. Never prints URLs."""
    from alerts.delivery import redact_webhook_url
    from database.models import WebhookDelivery

    settings = load_settings(config)
    init_db(settings.database_url)
    session_factory = get_session_factory(settings.database_url)

    with session_scope(session_factory) as session:
        for channel, url in (
            ("newsroom", settings.discord_webhook),
            ("maintenance", settings.maintenance_webhook),
        ):
            console.print(f"[bold]{channel}[/bold]  webhook: {redact_webhook_url(url)}")
            last_attempt = (
                session.query(WebhookDelivery)
                .filter(WebhookDelivery.channel == channel, WebhookDelivery.attempted.is_(True))
                .order_by(WebhookDelivery.attempted_at.desc())
                .first()
            )
            last_success = (
                session.query(WebhookDelivery)
                .filter(WebhookDelivery.channel == channel, WebhookDelivery.delivered.is_(True))
                .order_by(WebhookDelivery.delivered_at.desc())
                .first()
            )
            recent_failures = (
                session.query(WebhookDelivery)
                .filter(WebhookDelivery.channel == channel, WebhookDelivery.attempted.is_(True), WebhookDelivery.delivered.is_(False))
                .count()
            )
            console.print(f"  last attempted delivery: {last_attempt.attempted_at if last_attempt else '—'}")
            console.print(f"  last successful delivery: {last_success.delivered_at if last_success else '—'}")
            console.print(f"  recent failures: {recent_failures}")
            counts = _channel_counts(session, channel)
            console.print(
                f"  eligible={counts['eligible']}  attempted={counts['attempted']}  "
                f"delivered={counts['delivered']}  suppressed={counts['suppressed']}  failed={counts['failed']}"
            )


def _send_test(channel: str, webhook_url: str, session_factory) -> bool:
    from alerts.delivery import WebhookTransport
    from database.models import WebhookDelivery

    label = "Newsroom" if channel == "newsroom" else "Maintenance"
    content = (
        "🧪 Smartphone Intel Clank Test\n\n"
        f"Channel: {label}\n"
        "Environment: test\n"
        "Source: Manual transport test\n"
        "No device intelligence was created."
    )
    transport = WebhookTransport(webhook_url)
    result = transport.send({"content": content}, eligible=True)

    with session_scope(session_factory) as session:
        session.add(
            WebhookDelivery(
                channel=channel,
                reason="synthetic_test",
                dedupe_key=None,
                test_mode=True,
                eligible=result.eligible,
                suppressed=result.suppressed,
                attempted=result.attempted,
                delivered=result.delivered,
                status_code=result.status_code,
                error_type=result.error_type,
                error_message=result.error_message,
                attempted_at=_parse_iso(result.attempted_at),
                delivered_at=_parse_iso(result.delivered_at),
            )
        )

    if result.delivered:
        console.print(f"[green]Test message delivered to {label} channel.[/green]")
    else:
        console.print(f"[red]Delivery failed: {result.error_type or 'unknown error'}[/red]")
    return result.delivered


@discord_test_app.command("newsroom")
def discord_test_newsroom(config: str = typer.Option("config/config.yaml")):
    """Send a synthetic test message to the newsroom webhook. Creates no device/evidence rows."""
    settings = load_settings(config)
    init_db(settings.database_url)
    session_factory = get_session_factory(settings.database_url)
    if not _send_test("newsroom", settings.discord_webhook, session_factory):
        raise typer.Exit(1)


@discord_test_app.command("maintenance")
def discord_test_maintenance(config: str = typer.Option("config/config.yaml")):
    """Send a synthetic test message to the maintenance webhook. Creates no device/evidence rows."""
    settings = load_settings(config)
    init_db(settings.database_url)
    session_factory = get_session_factory(settings.database_url)
    if not _send_test("maintenance", settings.maintenance_webhook, session_factory):
        raise typer.Exit(1)


@samsung_app.command("sources")
def samsung_sources():
    from collectors.samsung.discovery import SamsungDiscovery
    disc = SamsungDiscovery()
    for sid, src in disc.sources().items():
        enabled = "ON " if src.get("enabled") else "off"
        console.print(
            f"{enabled}  {sid:30}  {src.get('validation_status', '?'):16}  "
            f"{src.get('region', ''):4}  {src.get('display_name', '')}"
        )


@samsung_app.command("discover")
def samsung_discover(
    dry_run: bool = typer.Option(True, "--dry-run/--live"),
    source: str = typer.Option(None, "--source"),
    json_out: bool = typer.Option(False, "--json"),
):
    from collectors.samsung.discovery import SamsungDiscovery
    import json as _json
    disc = SamsungDiscovery()
    if source:
        stats_list = [disc.discover_source(source)]
    else:
        stats_list = disc.discover_all(enabled_only=True, dry_run=dry_run)
    if json_out:
        console.print(_json.dumps([
            {
                "source": s.source_id,
                "status": s.validation_status,
                "pages": s.pages_fetched,
                "extracted": s.candidates_extracted,
                "valid": s.valid_mobile,
                "rejected": s.rejected,
                "models": s.models,
                "errors": s.errors,
            }
            for s in stats_list
        ], indent=2))
        return
    for s in stats_list:
        console.print(f"[bold]Source:[/bold] {s.display_name}  ({s.validation_status})")
        console.print(f"  Pages fetched: {s.pages_fetched}")
        console.print(f"  Candidates extracted: {s.candidates_extracted}")
        console.print(f"  Valid mobile candidates: {s.valid_mobile}")
        console.print(f"  Rejected: {s.rejected}")
        console.print(f"  Parser warnings: {s.parser_warnings}")
        for m in s.models[:20]:
            console.print(f"    • {m['canonical']:16}  {m.get('series') or ''}  {m.get('category')}  {m.get('url','')[:60]}")
        if s.errors:
            console.print(f"  [yellow]Notes: {s.errors[:3]}[/yellow]")


@samsung_app.command("health")
def samsung_health(source: str = typer.Option(None, "--source"), json_out: bool = typer.Option(False, "--json")):
    from collectors.samsung.discovery import SamsungDiscovery
    disc = SamsungDiscovery()
    rows = []
    for sid, src in disc.sources().items():
        if source and sid != source:
            continue
        rows.append({
            "source": sid,
            "enabled": src.get("enabled"),
            "validation_status": src.get("validation_status"),
            "region": src.get("region"),
            "notes": src.get("notes"),
        })
    if json_out:
        import json as _json
        console.print(_json.dumps(rows, indent=2))
    else:
        for r in rows:
            console.print(
                f"{r['source']:30}  enabled={r['enabled']}  "
                f"status={r['validation_status']:16}  {r.get('notes','')[:60]}"
            )


@samsung_app.command("source-audit")
def samsung_source_audit():
    """Print the static audit document path and live registry status."""
    console.print("Audit document: docs/samsung_collector_audit.md")
    console.print("Live validation: docs/samsung_live_validation.md")
    from collectors.samsung.discovery import SamsungDiscovery
    disc = SamsungDiscovery()
    for sid, src in disc.sources().items():
        console.print(f"  {sid}: {src.get('validation_status')}")


@app.command("confidence")
def confidence_cmd(
    model: str = typer.Argument(...),
    json_out: bool = typer.Option(False, "--json"),
    config: str = typer.Option("config/config.yaml"),
):
    settings = load_settings(config)
    session_factory = get_session_factory(settings.database_url)
    from entity_resolution.confidence_ledger import ConfidenceLedger
    with session_scope(session_factory) as session:
        device = session.query(Device).filter(Device.model_number == model.upper()).first()
        if not device:
            console.print(f"[red]No device {model}[/red]")
            raise typer.Exit(1)
        ledger = ConfidenceLedger(session)
        summary = ledger.summary(device)
    if json_out:
        import json as _json
        console.print(_json.dumps(summary, indent=2, default=str))
    else:
        console.print(f"[bold]{summary['device']}[/bold]  confidence={summary['confidence']}")
        for c in summary["contributions"]:
            console.print(
                f"  {c['previous']} → {c['new']}  +{c['points']:3}  {c['rule']:28}  {c.get('explanation') or ''}"
            )



@samsung_app.command("coverage")
def samsung_coverage(
    json_out: bool = typer.Option(False, "--json"),
    config: str = typer.Option("config/config.yaml"),
):
    """Samsung sitemap catalog coverage report."""
    import json as _json
    from config.settings import load_settings
    from database.session import get_session_factory, init_db, get_engine
    from database.models import SitemapProductUrl, SitemapTraversalState
    from collectors.samsung.traversal import coverage_report

    settings = load_settings(config)
    init_db(settings.database_url)
    eng = get_engine(settings.database_url)
    SitemapProductUrl.__table__.create(bind=eng, checkfirst=True)
    SitemapTraversalState.__table__.create(bind=eng, checkfirst=True)
    sf = get_session_factory(settings.database_url)
    with session_scope(sf) as session:
        rep = coverage_report(session)
    if json_out:
        console.print(_json.dumps(rep, indent=2, default=str))
    else:
        console.print("[bold]Samsung sitemap coverage[/bold]")
        console.print(f"  Sitemap phone URLs:     {rep['sitemap_phone_urls']}")
        console.print(f"  Ever attempted:         {rep['ever_attempted']}")
        console.print(f"  Successfully fetched:   {rep['successfully_fetched']}")
        console.print(f"  Valid mobile models:    {rep['valid_mobile_models']}")
        console.print(f"  No model extracted:     {rep['no_model_extracted']}")
        console.print(f"  Failed only:            {rep['failed_only']}")
        console.print(f"  Never attempted:        {rep['never_attempted']}")
        console.print(f"  Under backoff:          {rep['under_backoff']}")
        console.print(f"  Current cycle progress: {rep['cycle_progress_pct']}%")
        console.print(f"  Cycles completed:       {rep['cycles_completed']}")
        console.print(f"  Last complete cycle:    {rep['last_completed_cycle_at'] or 'Never'}")
        console.print(f"  Strategy:               {rep['strategy']}")


@samsung_app.command("verify-upgrade")
def samsung_verify_upgrade(config: str = typer.Option("config/config.yaml")):
    """Verify v0.3.7 upgrade preserved production data."""
    from config.settings import load_settings
    from database.session import get_session_factory, init_db
    from database.models import Device, Evidence, CollectorRun
    from sqlalchemy import text

    settings = load_settings(config)
    init_db(settings.database_url)
    sf = get_session_factory(settings.database_url)
    with session_scope(sf) as session:
        n_dev = session.query(Device).count()
        n_ev = session.query(Evidence).count()
        n_runs = session.query(CollectorRun).count()
        junk = session.query(Device).filter(Device.manufacturer != "samsung").count()
        console.print(f"devices={n_dev} evidence={n_ev} runs={n_runs} non_samsung={junk}")
        if junk:
            console.print("[red]FAIL: junk OEMs present[/red]")
            raise typer.Exit(1)
        if n_dev < 15:
            console.print("[yellow]WARN: fewer than 15 devices (expected if DB was wiped)[/yellow]")
        console.print("[green]OK[/green]")


@samsung_app.command("discover-sitemap")
def samsung_discover_sitemap(
    dry_run: bool = typer.Option(True, "--dry-run/--live"),
    fetch_products: bool = typer.Option(False, "--fetch-products"),
    max_fetches: int = typer.Option(10, "--max-fetches"),
    fixture: bool = typer.Option(False, "--fixture"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Discover phone support URLs from Samsung US public support sitemap (true discovery)."""
    from collectors.samsung.sitemap_discovery import SamsungSitemapDiscovery
    import json as _json
    disc = SamsungSitemapDiscovery(max_product_fetches=max_fetches)
    stats = disc.discover(fetch_products=fetch_products, use_fixture_sitemap=fixture, max_fetches=max_fetches)
    if json_out:
        console.print(_json.dumps({
            "status": stats.validation_status,
            "sitemap_urls": stats.sitemap_urls,
            "phone_product_urls": stats.phone_product_urls,
            "new_urls": stats.new_urls,
            "valid_mobile": stats.valid_mobile,
            "discoveries": stats.discoveries[:50],
            "errors": stats.errors,
        }, indent=2))
        return
    console.print(f"[bold]Samsung US Support Sitemap Discovery[/bold]  ({stats.validation_status})")
    console.print(f"  Sitemap locs: {stats.sitemap_urls}")
    console.print(f"  Phone product URLs: {stats.phone_product_urls}")
    console.print(f"  New vs known: {stats.new_urls}")
    console.print(f"  Valid mobile models: {stats.valid_mobile}")
    for d in stats.discoveries[:15]:
        console.print(f"  • {d.get('model') or d.get('product_slug')}  {d.get('novelty')}  {d.get('url','')[:70]}")
    if stats.errors:
        console.print(f"  [yellow]{stats.errors[:5]}[/yellow]")


@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1", help="Bind host (default localhost only)"),
    port: int = typer.Option(8200),
    config: str = typer.Option("config/config.yaml"),
):
    """Launch local newsroom console (FastAPI + Jinja2)."""
    if host not in ("127.0.0.1", "localhost", "::1"):
        console.print("[bold red]WARNING: Binding outside loopback. Dashboard is not hardened for public exposure.[/bold red]")
    settings = load_settings(config)
    try:
        from dashboard.app import create_app, app as dash_app
        import uvicorn
    except ImportError as e:
        console.print(f"[red]Missing dashboard dependency: {e}[/red]")
        console.print("Run: .\\.venv\\Scripts\\python.exe -m pip install fastapi uvicorn jinja2")
        raise typer.Exit(1)
    create_app(settings.database_url)
    console.print(f"[green]Newsroom console: http://{host}:{port}/[/green]")
    uvicorn.run(dash_app, host=host, port=port, reload=False, log_level="info")


@app.command("audit")
def audit_cmd(what: str = typer.Argument("confidence-writes")):
    if what == "confidence-writes":
        from tests.test_confidence_write_enforcement import test_no_illegal_confidence_writes
        test_no_illegal_confidence_writes()
        console.print("[green]OK[/green]")
    else:
        console.print(f"Unknown audit: {what}")
        raise typer.Exit(1)


@app.command()
def report(
    kind: str = typer.Argument("daily"),
    json_out: bool = typer.Option(False, "--json"),
    config: str = typer.Option("config/config.yaml"),
    tz: str = typer.Option("Asia/Kolkata", "--tz", help="Report day-boundary timezone"),
):
    """Operational reports (daily). Production activity only, IST by default."""
    from observability.metrics import daily_report, format_daily_report_md
    import json as _json
    settings = load_settings(config)
    session_factory = get_session_factory(settings.database_url)
    # report is a read-path command — it must never create or alter schema,
    # only refuse with a clear instruction if required tables are missing.
    from database.schema_guard import ensure_tables_present_or_refuse, SchemaError
    try:
        ensure_tables_present_or_refuse(
            settings.database_url,
            ["collector_run_metrics", "metrics_baselines", "rolling_stats"],
            context="report",
        )
    except SchemaError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    with session_scope(session_factory) as session:
        from collectors import production_scope
        scope = production_scope(settings, project_root=Path(__file__).resolve().parent)
        rep = daily_report(session, tz=tz, production_scope=scope)
    if json_out:
        console.print(_json.dumps(rep, indent=2, default=str))
    else:
        console.print(format_daily_report_md(rep))


@app.command()
def demo(
    scenario: str = typer.Argument("support-diff"),
    config: str = typer.Option("config/config.yaml"),
):
    """Run offline demos."""
    if scenario == "long-run":
        from demo.long_run_sim import run_demo
        raise typer.Exit(run_demo())
    if scenario == "support-diff":
        from demo.support_diff_demo import run_demo
        raise typer.Exit(run_demo(config))
    if scenario in ("samsung-discovery", "samsung-lifecycle"):
        if scenario == "samsung-discovery":
            from demo.samsung_discovery_demo import run_demo as rd
        else:
            from demo.samsung_lifecycle_demo import run_demo as rd
        raise typer.Exit(rd())
    console.print(f"[red]Unknown demo: {scenario}[/red]")
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
