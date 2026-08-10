"""
Newsroom console — FastAPI + Jinja2, localhost by default.
No React/Vue/npm. Server-rendered.
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, Query
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


def create_app(database_url: str = "sqlite:///./data/clank.db") -> FastAPI:
    """The dashboard is a real production runtime path (launched by
    scripts/windows/start-dashboard.ps1, supervised by health-check.ps1) —
    it must never create or alter schema. Refuses via SchemaError if the
    tables it reads are missing, same as the daemon and `report`."""
    global _Session, _engine
    from database.schema_guard import ensure_tables_present_or_refuse

    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    _engine = create_engine(database_url, connect_args=connect_args)
    ensure_tables_present_or_refuse(
        database_url,
        ["devices", "evidence", "timeline_events", "aliases", "snapshots", "webhook_deliveries"],
        context="dashboard",
    )
    _Session = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return app


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
                "now": datetime.utcnow().isoformat(),
            },
        )
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
        return TEMPLATES.TemplateResponse(request, "devices.html", { "devices": devices, "q": q or "", "manufacturer": manufacturer or ""},
        )
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
        db = rec.database_health()
        return TEMPLATES.TemplateResponse(
            request,
            "metrics.html",
            {"rows": rows, "db": db},
        )
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
