"""
Newsroom console — FastAPI + Jinja2, localhost by default.
No React/Vue/npm. Server-rendered.
"""

from __future__ import annotations

import html
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, Query, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker

from database.models import Base, Device, Evidence, TimelineEvent, Alias, Snapshot, WebhookDelivery
from observability.metrics import MetricsRecorder, CollectorRunRecord
from entity_resolution.confidence_service import ConfidenceService
from entity_resolution.confidence_ledger import ConfidenceLedger

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

app = FastAPI(title="Clank Newsroom", docs_url=None, redoc_url=None)

# DB session — set by create_app
_Session = None
_engine = None
_collection_controller = None
# Why no controller is wired, when there is none. Shown on /collect instead of
# a blank page, so "I can't run anything" always has a stated reason.
_collection_unavailable_reason = None


def create_app(database_url: str | None = None, collection_controller=None,
               collection_unavailable_reason: str | None = None) -> FastAPI:
    """The dashboard is a real production runtime path (launched by
    scripts/windows/start-dashboard.ps1, supervised by health-check.ps1) —
    it must never create or alter schema. Refuses via SchemaError if the
    tables it reads are missing, same as the daemon and `report`."""
    global _Session, _engine, _collection_controller, _collection_unavailable_reason
    if database_url is None:
        from config.settings import load_settings
        database_url = load_settings().database_url
    from database.schema_guard import ensure_tables_present_or_refuse

    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    _engine = create_engine(database_url, connect_args=connect_args)
    ensure_tables_present_or_refuse(
        database_url,
        ["devices", "evidence", "timeline_events", "aliases", "snapshots", "webhook_deliveries"],
        context="dashboard",
    )
    _Session = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    _collection_controller = collection_controller
    _collection_unavailable_reason = collection_unavailable_reason
    TEMPLATES.env.globals["collection_available"] = collection_controller is not None
    # Deliberately expose only non-secret runtime provenance in the local UI.
    # The database revision is evidence that the dashboard and collector are
    # pointed at the same state, while the build revision identifies a frozen
    # field-test bundle without reading any credentials.
    from database.schema_guard import current_revision
    TEMPLATES.env.globals["runtime_identity"] = {
        "build_revision": os.getenv("CLANK_BUILD_REVISION", "local-source"),
        "database_revision": current_revision(database_url) or "unstamped",
    }
    # Collector UI design system v1: the stylesheet is shared byte-for-byte
    # across the six collector Clanks; only the accent is Smartphone's own.
    from dashboard.collector_ui import CSS as _UI_CSS
    TEMPLATES.env.globals["ui_css"] = _UI_CSS
    TEMPLATES.env.globals["ui_accent"] = SMARTPHONE_ACCENT
    TEMPLATES.env.globals["ui_accent_soft"] = SMARTPHONE_ACCENT_SOFT
    return app


# Smartphone Clank domain accent (the only visual token this Clank overrides).
SMARTPHONE_ACCENT = "#4c8dff"
SMARTPHONE_ACCENT_SOFT = "#16283f"


def _overview(session):
    """Operator overview facts: is it healthy, when did it last run, what came
    of it. STD-UI-COM-008 keeps health (did contact succeed) separate from
    coverage (how much was seen)."""
    from datetime import timedelta

    from dashboard.collector_ui import badge
    from observability.metrics import CollectorRunRecord

    now = datetime.utcnow()
    recent = (
        session.query(CollectorRunRecord)
        .order_by(CollectorRunRecord.started_at.desc())
        .limit(50)
        .all()
    )
    last = recent[0] if recent else None
    day = [r for r in recent if r.started_at and r.started_at >= now - timedelta(hours=24)]
    failed = [r for r in day if (r.status or "") not in ("success", "ok")]

    if last is None:
        health, note = "UNKNOWN", "no collector run recorded yet"
    elif failed:
        health, note = "DEGRADED", f"{len(failed)} of {len(day)} runs failed in 24h"
    else:
        health, note = "HEALTHY", f"{len(day)} run(s) in the last 24h, none failed"

    attention = []
    for r in failed[:8]:
        attention.append({
            "what": r.collector_name or "unknown collector",
            "badge": badge(r.status or "FAILED"),
            "detail": (r.notes or r.meta or "no cause recorded on this run"),
        })

    from collectors.wave1 import PRODUCTION_OEM_SCOPE

    return {
        "health": health,
        "health_badge": badge(health),
        "health_note": note,
        "device_count": session.query(Device).count(),
        "oem_count": len(PRODUCTION_OEM_SCOPE),
        "last_run_at": last.started_at.strftime("%Y-%m-%d %H:%M") if last and last.started_at else None,
        "last_run_note": ("trigger " + (last.run_reason or "unknown")) if last else "runs appear here after the first cycle",
        "last_run_badge": badge(last.status if last else "UNKNOWN"),
        "last_run_collector": last.collector_name if last else None,
        "runs_24h": len(day),
        "failed_24h": len(failed),
        # STD-UI-COM-011: delivery state is its own axis, never a boolean.
        "delivery_badge": badge("DISABLED"),
        "delivery_note": "no destination configured in this console",
        "attention": attention,
    }


def get_session():
    return _Session()

@app.get("/healthz")
def healthz():
    """Lightweight liveness for Windows health-check. No secrets."""
    db_ok = "ok"
    try:
        session = get_session()
        try:
            session.execute(__import__("sqlalchemy").text("SELECT 1"))
        finally:
            session.close()
    except Exception:
        db_ok = "error"
    return {
        "status": "ok" if db_ok == "ok" else "degraded",
        "database": db_ok,
        "scheduler": "separate",
        "version": "0.3.5",
    }



def esc(s):
    return html.escape(str(s) if s is not None else "")


TEMPLATES.env.filters["esc"] = esc


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    session = get_session()
    try:
        devices = session.query(Device).order_by(Device.last_seen.desc()).limit(20).all()
        rising = session.query(Device).order_by(Device.confidence.desc()).limit(10).all()
        return TEMPLATES.TemplateResponse(request, "home.html", {
                "devices": devices,
                "rising": rising,
                "active": "home",
                "overview": _overview(session),
            },
        )
    finally:
        session.close()


@app.get("/api/local-collection/status")
def local_collection_status():
    """Read-only poll for the Collect page. Reports state; never starts one."""
    if _collection_controller is None:
        return JSONResponse({"error": "local_collection_unavailable"}, status_code=404)
    return _collection_controller.snapshot()


def _require_local_operator(request: Request) -> None:
    """Local-operator authority for mutating endpoints.

    This console has no authenticated remote profile, so the authority model is
    the one the rest of the app already uses: the server binds loopback only
    (native/windows/launcher.py binds 127.0.0.1 on an ephemeral port; `main.py
    dashboard` refuses a non-loopback --host via require_loopback_host), and a
    mutation is additionally accepted only from a loopback peer. Reusing
    main.require_loopback_host keeps ONE definition of "loopback" rather than a
    second, drifting copy here.

    Raises ValueError when the caller is not a local operator.
    """
    from main import require_loopback_host

    client = request.client
    host = client.host if client else ""
    # A TestClient request has a synthetic client host; an absent peer is
    # treated as untrusted rather than assumed local.
    require_loopback_host(host)


@app.post("/api/local-collection/run")
def local_collection_run(request: Request, payload: dict = Body(...)):
    """Start exactly one collection run. EXPLICIT OPERATOR ACTION ONLY.

    This used to hard-return 403 "Phase 0 dashboard is read-only", which left
    the console with no way to collect at all. The invariant it was protecting
    is narrower than that and is still fully enforced: opening or refreshing a
    page never collects. Collection begins only on this POST, only for a named
    source in SMARTPHONE_FIELD_TEST_SOURCES, only from a loopback operator, and
    only one run at a time.
    """
    if _collection_controller is None:
        return JSONResponse(
            {
                "error": "local_collection_unavailable",
                "detail": _collection_unavailable_reason
                or "No collection controller is wired into this dashboard process.",
            },
            status_code=404,
        )
    try:
        _require_local_operator(request)
    except ValueError as exc:
        return JSONResponse(
            {"error": "local_operator_required", "detail": str(exc)}, status_code=403
        )

    source_id = (payload or {}).get("source_id")
    if not isinstance(source_id, str) or not source_id:
        return JSONResponse(
            {"error": "source_id_required",
             "detail": "Name exactly one source to run."},
            status_code=400,
        )

    started, state = _collection_controller.start(source_id)
    if not started:
        # 409 for "already running" (a real, retryable operator condition);
        # 400 for a source this console is not allowed to run.
        code = 409 if state.get("error") == "collection_already_running" else 400
        return JSONResponse(state, status_code=code)
    return JSONResponse(state, status_code=202)


@app.get("/collect", response_class=HTMLResponse)
def collect_page(request: Request):
    """Operator collection surface. This GET renders state only — it reads the
    controller's snapshot and the canonical run history, and starts nothing."""
    from dashboard.collector_ui import badge
    from dashboard.local_collection import SMARTPHONE_FIELD_TEST_SOURCES

    controller = _collection_controller
    sources = controller.sources() if controller is not None else []
    status = controller.snapshot() if controller is not None else None
    for source in sources:
        source["maturity_badge"] = badge(
            "PRODUCTION" if source["maturity"] == "production" else "EXPERIMENTAL"
        )
        source["enabled_badge"] = badge("MANUAL" if source["enabled"] else "DISABLED")
        source["last_badge"] = badge(
            _RUN_STATUS_LABELS.get(source["last_status"], source["last_status"])
            if source["last_status"] else "UNKNOWN"
        )
    return TEMPLATES.TemplateResponse(request, "collect.html", {
        "active": "collect",
        "sources": sources,
        "status": status,
        "available": controller is not None,
        "unavailable_reason": _collection_unavailable_reason,
        "database_url": str(_engine.url) if _engine is not None else "",
        "source_count": len(SMARTPHONE_FIELD_TEST_SOURCES),
    })


# Canonical run statuses mapped onto the shared design-system vocabulary, so
# the Collect page and Run History label the same state the same way.
_RUN_STATUS_LABELS = {
    "success": "SUCCESS",
    "partial": "PARTIAL",
    "degraded": "DEGRADED",
    "unexpected_zero": "PARTIAL",
    "failed": "FAILED",
    "blocked": "BLOCKED",
    "running": "RUNNING",
}


@app.get("/about", response_class=HTMLResponse)
def about_page(request: Request):
    """Common About/identity surface for the collector family. Deliberately
    exposes only non-secret provenance: no credential, webhook or token."""
    from collectors.wave1 import PRODUCTION_OEM_SCOPE
    from dashboard.collector_ui import DESIGN_SYSTEM_VERSION, badge
    from observability.metrics import CollectorRunRecord

    session = get_session()
    try:
        identity = TEMPLATES.env.globals.get("runtime_identity", {})
        return TEMPLATES.TemplateResponse(request, "about.html", {
            "active": "about",
            "about": {
                "build_revision": identity.get("build_revision", "unknown"),
                "database_revision": identity.get("database_revision", "unstamped"),
                "schema_badge": badge("HEALTHY" if identity.get("database_revision") not in (None, "unstamped") else "UNKNOWN"),
                "design_system": DESIGN_SYSTEM_VERSION,
                "oems": sorted(PRODUCTION_OEM_SCOPE),
                "device_count": session.query(Device).count(),
                "run_count": session.query(CollectorRunRecord).count(),
                # Collection posture is an axis, not a boolean: MANUAL means
                # operator-triggered only, DISABLED means not runnable here.
                "collection_badge": badge(
                    "MANUAL" if _collection_controller is not None else "DISABLED"
                ),
                "collection_note": (
                    "operator-triggered only — opening a page never collects"
                    if _collection_controller is not None
                    else "no collection controller wired into this process"
                ),
                "delivery_badge": badge("DISABLED"),
            },
        })
    finally:
        session.close()


@app.get("/devices", response_class=HTMLResponse)
def device_queue(
    request: Request,
    q: Optional[str] = None,
    manufacturer: Optional[str] = None,
    min_conf: Optional[int] = None,
):
    session = get_session()
    try:
        query = session.query(Device)
        if manufacturer:
            query = query.filter(Device.manufacturer == manufacturer.lower())
        if min_conf is not None:
            query = query.filter(Device.confidence >= min_conf)
        if q:
            like = f"%{q}%"
            query = query.filter(
                or_(
                    Device.model_number.ilike(like),
                    Device.marketing_name.ilike(like),
                    Device.family_name.ilike(like),
                    Device.codename.ilike(like),
                )
            )
        devices = query.order_by(Device.last_seen.desc()).limit(100).all()
        # "No matches for your filter" and "this database has no devices" are
        # different facts. The page needs both to tell them apart, otherwise an
        # empty database reads as a bad search.
        return TEMPLATES.TemplateResponse(request, "devices.html", {
            "devices": devices,
            "q": q or "",
            "manufacturer": manufacturer or "",
            "filtered": bool(q or manufacturer or min_conf is not None),
            "total_devices": session.query(Device).count(),
        })
    finally:
        session.close()


@app.get("/devices/{model}", response_class=HTMLResponse)
def device_dossier(request: Request, model: str):
    session = get_session()
    try:
        device = session.query(Device).filter(Device.model_number == model.upper()).first()
        if not device:
            return HTMLResponse(f"<h1>Not found: {esc(model)}</h1>", status_code=404)
        evidence = session.query(Evidence).filter(Evidence.device_id == device.id).all()
        timeline = (
            session.query(TimelineEvent)
            .filter(TimelineEvent.device_id == device.id)
            .order_by(TimelineEvent.occurred_at)
            .all()
        )
        aliases = session.query(Alias).filter(Alias.device_id == device.id).all()
        ledger = ConfidenceLedger(session).summary(device)
        snapshots = (
            session.query(Snapshot)
            .filter(Snapshot.model_number == device.model_number)
            .order_by(Snapshot.fetched_at.desc())
            .limit(10)
            .all()
        )
        return TEMPLATES.TemplateResponse(request, "dossier.html", {
                "device": device,
                "evidence": evidence,
                "timeline": timeline,
                "aliases": aliases,
                "ledger": ledger,
                "snapshots": snapshots,
            },
        )
    finally:
        session.close()


@app.get("/health", response_class=HTMLResponse)
def source_health(request: Request):
    # Read registry YAML
    import yaml
    path = ROOT / "config" / "samsung_sources.yaml"
    sources = {}
    if path.exists():
        data = yaml.safe_load(path.read_text()) or {}
        sources = (data.get("samsung") or {}).get("sources") or {}
    return TEMPLATES.TemplateResponse(request, "health.html", { "sources": sources},
    )




@app.get("/metrics", response_class=HTMLResponse)
def metrics_page(request: Request):
    from collectors import production_scope
    from config.settings import load_settings

    session = get_session()
    try:
        names = [
            r[0]
            for r in session.query(CollectorRunRecord.collector_name).distinct().all()
        ]
        scope = production_scope(load_settings())
        rec = MetricsRecorder(session)
        rows = [
            rec.collector_summary(n, in_scope=(scope is None or n in scope))
            for n in sorted(names)
        ]
        recent_runs = (
            session.query(CollectorRunRecord)
            .order_by(CollectorRunRecord.started_at.desc())
            .limit(20)
            .all()
        )
        db = rec.database_health()
        return TEMPLATES.TemplateResponse(
            request,
            "metrics.html",
            {"rows": rows, "db": db, "recent_runs": recent_runs},
        )
    finally:
        session.close()

@app.get("/metrics/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: str):
    """STD-UI-COM-009 remediation (2026-08-31): the metrics page links each
    recent run here, so the per-run state the backend already records —
    status, phase-attributable counters, and the regression notes it
    writes into run records — is directly reachable and discoverable."""
    session = get_session()
    try:
        run = session.get(CollectorRunRecord, run_id)
        if run is None:
            return HTMLResponse(f"<h1>Not found: run {esc(run_id)}</h1>", status_code=404)
        return TEMPLATES.TemplateResponse(request, "run_detail.html", {"run": run})
    finally:
        session.close()


@app.get("/discord", response_class=HTMLResponse)
def discord_status_page(request: Request):
    from alerts.delivery import redact_webhook_url, channel_summary
    from config.settings import load_settings

    settings = load_settings()
    session = get_session()
    try:
        channels = []
        for channel, url in (
            ("newsroom", settings.discord_webhook),
            ("maintenance", settings.maintenance_webhook),
        ):
            counts = channel_summary(session, channel, test_mode=False)
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
                .filter(
                    WebhookDelivery.channel == channel,
                    WebhookDelivery.attempted.is_(True),
                    WebhookDelivery.delivered.is_(False),
                )
                .order_by(WebhookDelivery.attempted_at.desc())
                .limit(10)
                .all()
            )
            channels.append({
                "name": channel,
                "configured": redact_webhook_url(url) == "configured",
                "last_attempted": last_attempt.attempted_at if last_attempt else None,
                "last_delivered": last_success.delivered_at if last_success else None,
                "eligible": counts["eligible"],
                "attempted": counts["attempted"],
                "delivered": counts["delivered"],
                "suppressed": counts["suppressed"],
                "failed": counts["failed"],
                "recent_failures": recent_failures,
            })
        return TEMPLATES.TemplateResponse(request, "discord.html", {"channels": channels})
    finally:
        session.close()


@app.get("/api/device/{model}")
def api_device(model: str):
    session = get_session()
    try:
        device = session.query(Device).filter(Device.model_number == model.upper()).first()
        if not device:
            return JSONResponse({"error": "not found"}, status_code=404)
        ledger = ConfidenceLedger(session).summary(device)
        return {
            "model": device.model_number,
            "manufacturer": device.manufacturer,
            "marketing_name": device.marketing_name,
            "confidence": device.confidence,
            "family": device.family_name,
            "tier": device.product_tier,
            "ledger": ledger,
        }
    finally:
        session.close()


@app.get("/export/device/{model}.md", response_class=PlainTextResponse)
def export_markdown(model: str):
    session = get_session()
    try:
        device = session.query(Device).filter(Device.model_number == model.upper()).first()
        if not device:
            return PlainTextResponse("Not found", status_code=404)
        ledger = ConfidenceLedger(session).summary(device)
        lines = [
            f"# {device.marketing_name or device.model_number}",
            f"",
            f"- Model: `{device.model_number}`",
            f"- Manufacturer: {device.manufacturer}",
            f"- Family: {device.family_name or '—'}",
            f"- Tier: {device.product_tier or '—'}",
            f"- Confidence: {device.confidence}",
            f"- First seen: {device.first_seen}",
            f"- Last seen: {device.last_seen}",
            f"",
            f"## Confidence ledger",
        ]
        for c in ledger.get("contributions", []):
            lines.append(f"- +{c['points']} {c['rule']}: {c.get('explanation')}")
        return PlainTextResponse("\n".join(lines))
    finally:
        session.close()
