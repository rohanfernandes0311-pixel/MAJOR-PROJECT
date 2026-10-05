"""
FastAPI backend for LandSense:
- Public API for risk prediction and geofencing
- Geo-fencing entry/exit detection
- Real-time ML risk prediction
- PostgreSQL-backed users, locations, alerts, and location events
- Twilio SMS alert queue with cooldown protection
"""

from __future__ import annotations

import re
import os
import hashlib
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from backend.auth.router import router as auth_router
from backend.citizen_weather import router as citizen_weather_router
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from alert_system import SensorReading, process_reading
from auth_security import (
    SlidingWindowLimiter,
    utc_now,
)
from landslide_extraction import router as landslide_extraction_router
from backend.auth import router as auth_router
from backend.auth.dependencies import require_auth
from backend.auth.middleware import JWTAuthMiddleware, require_admin
from backend.auth.otp_store import init_store as init_auth_store
from local_store import (
    create_alert,
    get_user,
    init_store,
    list_alerts,
    set_alert_subscription,
    store_location,
    upsert_user,
)
from database.connection import SessionLocal, engine, get_db
from database.models import Alert, AuditEvent, LandslideInventory, Location, LocationEvent, User
from geofencing import (
    detect_fence_event,
    find_zone_matches,
    highest_zone_risk,
    load_zones,
    primary_zone_id,
    point_in_polygon,
)
from predict import predict
from route_planner import plan_safe_route
from sms_service import send_sms_alert, sms_configuration_status
from services.extension_loader import ExtensionLoader
from services.safe_route_service import SafeRouteService
from services.phase6_intelligence import (
    build_zone_intelligence,
    find_incident_for_zone,
    load_incident_catalog,
    polygon_centroid,
)
from services.simulation_mode_service import KODAGU_LOCATIONS, SimulationModeService
from services.simulation_demonstration import router as simulation_demonstration_router
from services.audit_service import public_audit_event, try_record_audit_event
from services.offline_alert_transport import simulate_offline_deliveries
from services.httpsms_export import (
    MISSING_SENDER, build_workbook, export_filename, generate_alert_message, select_sms_recipients,
)


BASE_DIR = Path(__file__).parent
ZONE_PATH = BASE_DIR / "config" / "risk_zones.geojson"
WEB_UI_DIR = BASE_DIR / "web-ui"
WEB_UI_DIST_DIR = WEB_UI_DIR / "dist"
WEB_UI_ASSETS_DIR = WEB_UI_DIST_DIR / "assets"
INCIDENT_CATALOG_PATH = WEB_UI_DIR / "src" / "data" / "incidentScenarios.json"

ALERT_TEXT = "Landslide warning: You are in a high-risk zone. Move to a safer location immediately."
RISK_SCORE = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
ALERT_COOLDOWN_SECONDS = 600
 


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


ENFORCE_HTTPS = _env_flag("ENFORCE_HTTPS", True)
ALLOW_INSECURE_LOCALHOST = _env_flag("ALLOW_INSECURE_LOCALHOST", True)
LOCALHOST_NAMES = {"127.0.0.1", "localhost", "::1"}


app = FastAPI(title="LandSense Secure API", version="2.0.0")
app.add_middleware(JWTAuthMiddleware)
simulation_mode = SimulationModeService(BASE_DIR)
extensions = ExtensionLoader(base_dir=BASE_DIR)
weather_service = extensions.weather()
safe_route_service = SafeRouteService()
app.include_router(auth_router)
app.include_router(landslide_extraction_router)
app.include_router(simulation_demonstration_router)
app.include_router(citizen_weather_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _web_ui_asset(path: str, media_type: str | None = None) -> FileResponse:
    target = WEB_UI_DIST_DIR / path
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Missing web-ui asset: {path}")
    headers = {"Cache-Control": "no-store"}
    return FileResponse(target, media_type=media_type, headers=headers)


class LocationUpdateRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    latitude: float
    longitude: float
    deformation_mm: float = 5.0
    velocity_mm_yr: float = 12.0
    coherence: float = 0.8
    slope_deg: float = 24.0
    soil_moisture_pct: float = 45.0
    elevation_m: float = 900.0
    ndvi: float = 0.4
    model: str = "ensemble"
    location_name: str = "Unknown"
    phone_number: Optional[str] = None


class ProtectedLocationUpdateRequest(BaseModel):
    latitude: float
    longitude: float
    deformation_mm: float = 5.0
    velocity_mm_yr: float = 12.0
    coherence: float = 0.8
    slope_deg: float = 24.0
    soil_moisture_pct: float = 45.0
    elevation_m: float = 900.0
    ndvi: float = 0.4
    model: str = "ensemble"
    location_name: str = "Mobile User"


class RouteRequest(BaseModel):
    start_latitude: float = Field(..., ge=-90, le=90)
    start_longitude: float = Field(..., ge=-180, le=180)
    end_latitude: float = Field(..., ge=-90, le=90)
    end_longitude: float = Field(..., ge=-180, le=180)


class PredictRequest(BaseModel):
    latitude: float
    longitude: float
    deformation_mm: float
    velocity_mm_yr: float
    coherence: float
    slope_deg: float
    soil_moisture_pct: float
    elevation_m: float = 900.0
    ndvi: float = 0.4
    model: str = "ensemble"


class AlertSubscriptionRequest(BaseModel):
    alert_enabled: bool


class SimulationToggleRequest(BaseModel):
    enabled: bool
    forced_risk: str = "LOW"
    escalation_enabled: bool = False
    scenario_name: str = "Normal"


class KodaguSimulationRequest(BaseModel):
    location: str = Field(..., min_length=1, max_length=80)
    risk_level: str = Field(..., min_length=1, max_length=16)

    class Config:
        extra = "forbid"


class KodaguSimulationTriggerRequest(BaseModel):
    recipient_ids: list[str] = Field(default_factory=list, max_length=500)

    class Config:
        extra = "forbid"


class SimulationDemoExportRequest(BaseModel):
    scenario_revision: str = Field(..., min_length=1, max_length=100)
    recipient_ids: list[str] = Field(default_factory=list, max_length=500)
    message: str = Field(..., min_length=1, max_length=1000)
    revision: str | None = None

    class Config:
        extra = "forbid"


class AffectedZonePreviewRequest(BaseModel):
    """Admin-only, non-persistent recipient preview for a configured zone."""

    zone_id: str = Field(..., min_length=1, max_length=100)
    risk_level: str = Field(..., min_length=1, max_length=16)
    message: str = Field(..., min_length=1, max_length=1000)
    duration_minutes: int = Field(..., ge=5, le=10080)
    send_sms: bool = False

    class Config:
        extra = "forbid"


class AdminAuditUiEventRequest(BaseModel):
    """Narrow, noncritical Admin UI audit input; details are derived server-side."""

    event_type: str = Field(..., min_length=1, max_length=64)
    zone_id: str | None = Field(default=None, max_length=100)
    incident_id: str | None = Field(default=None, max_length=120)
    simulated_count: int | None = Field(default=None, ge=0, le=1000)

    class Config:
        extra = "forbid"


class OfflineDemoAreaRequest(BaseModel):
    """Configured-zone or catalog-incident selection for the isolated demo."""

    zone_id: str | None = Field(default=None, min_length=1, max_length=100)
    incident_id: str | None = Field(default=None, min_length=1, max_length=120)

    class Config:
        extra = "forbid"


class OfflineDemoSendRequest(OfflineDemoAreaRequest):
    channels: list[str] = Field(..., min_length=1, max_length=2)
    confirmed: bool


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limiter: SlidingWindowLimiter):
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host if request.client else "unknown"
        key = f"global:{ip}:{request.url.path}"
        if not self.limiter.allow(key):
            return JSONResponse(status_code=429, content={"detail": "Too many requests"})
        return await call_next(request)


app.add_middleware(RateLimitMiddleware, limiter=SlidingWindowLimiter(window_seconds=60, max_requests=120))


@app.middleware("http")
async def enforce_https(request: Request, call_next):
    if not _is_secure_request(request):
        return JSONResponse(
            status_code=426,
            content={"detail": "HTTPS is required for this API"},
        )
    return await call_next(request)


_user_zone_state: dict[str, str | None] = {}
_last_high_risk_alert: dict[str, datetime] = {}


def init_db() -> None:
    """Fail startup if the runtime database is not PostgreSQL/Neon.

    Schema creation remains the responsibility of the existing migrations; the
    application must never recreate a local SQLite event store at startup.
    """
    if engine.dialect.name != "postgresql":
        raise RuntimeError("DATABASE_URL must target PostgreSQL/Neon for runtime persistence")


def save_event(payload: dict[str, Any]) -> None:
    """Persist one live location event through the configured SQLAlchemy DB."""
    db = SessionLocal()
    try:
        db.add(
            LocationEvent(
                user_id=payload["user_id"],
                timestamp_utc=payload["timestamp_utc"],
                latitude=payload["latitude"],
                longitude=payload["longitude"],
                rainfall_mm=payload["rainfall_mm"],
                ml_risk=payload["ml_risk"],
                zone_risk=payload["zone_risk"],
                final_risk=payload["final_risk"],
                geofence_event=payload.get("geofence_event"),
                active_zone_id=payload.get("active_zone_id"),
            )
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()


def combine_risk(ml_risk: str, zone_risk: str) -> str:
    return max([ml_risk.upper(), zone_risk.upper()], key=lambda k: RISK_SCORE.get(k, 0))


def _validate_e164(phone_number: str) -> str:
    normalized = phone_number.strip()
    if not E164_PATTERN.match(normalized):
        raise HTTPException(status_code=400, detail="Phone number must be in E.164 format")
    return normalized


def _is_secure_request(request: Request) -> bool:
    if request.url.scheme == "https":
        return True

    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto:
        primary_proto = forwarded_proto.split(",")[0].strip().lower()
        if primary_proto == "https":
            return True

    hostname = (request.url.hostname or "").lower()
    if ALLOW_INSECURE_LOCALHOST and hostname in LOCALHOST_NAMES:
        return True

    return not ENFORCE_HTTPS


def _queue_sms_alert(user_id: str, phone_number: str, risk_level: str, message: str) -> None:
    sms_result = send_sms_alert(phone_number, message)
    create_alert(
        user_id=user_id,
        risk_level=risk_level,
        message=message,
        delivered_status=sms_result.get("status", "unknown"),
    )


def _evaluate_location(
    req: LocationUpdateRequest,
    background_tasks: BackgroundTasks,
    user_phone: str | None,
    alert_enabled: bool,
) -> dict[str, Any]:
    zones_geo = load_zones(ZONE_PATH)
    simulation_location = simulation_mode.apply_location_override(req.latitude, req.longitude)
    eval_lat = float(simulation_location["latitude"])
    eval_lon = float(simulation_location["longitude"])

    weather = weather_service.fetch_weather_context(eval_lat, eval_lon)
    rain = weather_service.fetch_rainfall_mm(eval_lat, eval_lon)

    ml_pred = predict(
        deformation_mm=req.deformation_mm,
        velocity_mm_yr=req.velocity_mm_yr,
        coherence=req.coherence,
        rainfall_mm=rain["rainfall_mm"],
        slope_deg=req.slope_deg,
        soil_moisture_pct=req.soil_moisture_pct,
        elevation_m=req.elevation_m,
        aspect_deg=180.0,
        ndvi=req.ndvi,
        model=req.model,
    )

    matches = find_zone_matches(eval_lat, eval_lon, zones_geo)
    zone_risk = highest_zone_risk(matches)
    active_zone = simulation_location.get("zone_id") or primary_zone_id(matches)
    final_risk = combine_risk(ml_pred["risk_label"], zone_risk)

    simulation_state = simulation_mode.read_state()
    # The admin-only Kodagu workflow never decorates citizen predictions or ML
    # inputs. Legacy presentation simulation remains backward compatible.
    simulation_enabled = bool(simulation_state["enabled"] and not simulation_state.get("is_simulation"))
    simulated_risk = "LOW"
    if simulation_enabled:
        simulated_risk = simulation_mode.effective_forced_risk()
        zone_risk = max([zone_risk, simulated_risk], key=lambda k: RISK_SCORE.get(k, 0))
        final_risk = max([final_risk, simulated_risk], key=lambda k: RISK_SCORE.get(k, 0))

    evacuation = safe_route_service.build_guidance(eval_lat, eval_lon, zones_geo, final_risk, weather=weather)

    zone_matches_payload = [m.__dict__ for m in matches]
    if simulation_enabled and not zone_matches_payload and active_zone:
        zone_matches_payload = [
            {
                "zone_id": active_zone,
                "zone_name": simulation_location.get("zone_name") or "Simulated danger zone",
                "risk_level": zone_risk,
                "contains": True,
            }
        ]

    fence_event_payload: dict[str, Any] | None = None
    if simulation_enabled:
        fence_event_payload = {
            "user_id": req.user_id,
            "from_zone": None,
            "to_zone": active_zone,
            "event": "enter",
            "timestamp_utc": datetime.utcnow().isoformat(),
            "simulated": True,
        }
    else:
        prev_zone = _user_zone_state.get(req.user_id)
        fence_event = detect_fence_event(req.user_id, prev_zone, active_zone)
        _user_zone_state[req.user_id] = active_zone
        fence_event_payload = fence_event.__dict__ if fence_event else None

    reading = SensorReading(
        timestamp=datetime.utcnow().isoformat(),
        latitude=eval_lat,
        longitude=eval_lon,
        location_name=req.location_name if not simulation_enabled else f"{req.location_name} [SIMULATION]",
        deformation_mm=req.deformation_mm if not simulation_enabled else max(req.deformation_mm, 62.0),
        velocity_mm_yr=req.velocity_mm_yr if not simulation_enabled else max(req.velocity_mm_yr, 120.0),
        rainfall_mm=rain["rainfall_mm"],
        slope_deg=req.slope_deg,
        soil_moisture_pct=req.soil_moisture_pct,
        coherence=req.coherence,
        ml_risk_label=ml_pred["risk_label"] if not simulation_enabled else "High",
        ml_confidence=ml_pred["confidence"] if not simulation_enabled else 0.99,
    )

    alert_summary = None
    sms_result: dict[str, Any] | None = None

    if final_risk in {"HIGH", "CRITICAL"}:
        if simulation_enabled:
            # Simulation alerts are display-only.  They never invoke the real
            # alert pipeline, persist as a live alert, or queue SMS delivery.
            alert_summary = {
                "alert_id": None,
                "risk_level": final_risk,
                "message": f"SIMULATED ALERT: {final_risk} landslide risk in the demonstration zone.",
                "simulated": True,
            }
            sms_result = {"queued": False, "reason": "simulation_external_notifications_suppressed"}
        else:
            alert = process_reading(reading, send_only_above="HIGH")
            alert_summary = {
                "alert_id": alert.alert_id,
                "risk_level": alert.risk_level,
                "message": ALERT_TEXT,
                "simulated": False,
            }

            if alert_enabled and user_phone:
                now = utc_now()
                last_sent = _last_high_risk_alert.get(req.user_id)
                if (not last_sent) or ((now - last_sent).total_seconds() > ALERT_COOLDOWN_SECONDS):
                    _last_high_risk_alert[req.user_id] = now
                    background_tasks.add_task(
                        _queue_sms_alert,
                        req.user_id,
                        user_phone,
                        final_risk,
                        ALERT_TEXT,
                    )
                    sms_result = {"queued": True, "reason": "high_risk"}
                else:
                    create_alert(
                        user_id=req.user_id,
                        risk_level=final_risk,
                        message=ALERT_TEXT,
                        delivered_status="cooldown_skipped",
                    )
                    sms_result = {
                        "queued": False,
                        "reason": "cooldown",
                        "cooldown_seconds": ALERT_COOLDOWN_SECONDS,
                    }

    save_payload = {
        "user_id": req.user_id,
        "timestamp_utc": datetime.utcnow().isoformat(),
        "latitude": eval_lat,
        "longitude": eval_lon,
        "rainfall_mm": rain["rainfall_mm"],
        "ml_risk": ml_pred["risk_label"],
        "zone_risk": zone_risk,
        "final_risk": final_risk,
        "geofence_event": fence_event_payload["event"] if fence_event_payload else None,
        "active_zone_id": active_zone,
    }
    if simulation_enabled:
        simulation_mode.record_event("location_evaluation", {**save_payload, "simulation": simulation_state})
    else:
        save_event(save_payload)

    return {
        "user_id": req.user_id,
        "location": {
            "latitude": eval_lat,
            "longitude": eval_lon,
            "source": "simulation" if simulation_enabled else "live",
        },
        "rainfall": rain,
        "weather": weather,
        "ml_prediction": ml_pred,
        "zone_risk": zone_risk,
        "final_risk": final_risk,
        "inside_geofence": bool(matches) or simulation_enabled,
        "zone_matches": zone_matches_payload,
        "geofence_event": fence_event_payload,
        "voice_alert_text": ALERT_TEXT if final_risk in {"HIGH", "CRITICAL"} else "No critical warning.",
        "sms_result": sms_result,
        "alert": alert_summary,
        "evacuation": evacuation,
        "simulation": {
            "enabled": simulation_enabled,
            "scenario_name": simulation_state.get("scenario_name"),
            "effective_risk": simulated_risk if simulation_enabled else "LOW",
            "zone_id": active_zone,
            "escalation_enabled": simulation_state.get("escalation_enabled", False),
        },
    }


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    init_store()
    init_auth_store()


@app.get("/")
def root():
    index_path = WEB_UI_DIST_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return JSONResponse({"project": "LandSense", "status": "running", "ui": "/"})


@app.get("/admin")
def admin_root() -> FileResponse:
    return _web_ui_asset("index.html", media_type="text/html")


@app.get("/demo")
def demo_root() -> FileResponse:
    return _web_ui_asset("index.html", media_type="text/html")


@app.get("/frontend")
def frontend_root():
    return RedirectResponse(url="/")


@app.get("/frontend/index.html")
def frontend_index() -> FileResponse:
    return _web_ui_asset("index.html", media_type="text/html")


@app.get("/login")
def login_root() -> FileResponse:
    return _web_ui_asset("index.html", media_type="text/html")


@app.get("/otp")
def otp_root() -> FileResponse:
    return _web_ui_asset("index.html", media_type="text/html")


@app.get("/frontend/login")
def frontend_login() -> FileResponse:
    return _web_ui_asset("index.html", media_type="text/html")


@app.get("/frontend/otp")
def frontend_otp() -> FileResponse:
    return _web_ui_asset("index.html", media_type="text/html")


@app.get("/frontend/admin")
def frontend_admin() -> FileResponse:
    return _web_ui_asset("index.html", media_type="text/html")


@app.get("/frontend/demo")
def frontend_demo() -> FileResponse:
    return _web_ui_asset("index.html", media_type="text/html")


@app.get("/frontend/styles.css")
def frontend_styles() -> Response:
    return Response(content="/* Legacy frontend migrated to web-ui */", media_type="text/css")


@app.get("/frontend/app.js")
def frontend_app_js() -> Response:
    compatibility_js = "window.location.replace('/');"
    return Response(content=compatibility_js, media_type="application/javascript")


@app.get("/frontend/sw.js")
def frontend_sw_js() -> FileResponse:
    return _web_ui_asset("sw.js", media_type="application/javascript")


@app.get("/frontend/manifest.json")
def frontend_manifest() -> FileResponse:
    return _web_ui_asset("manifest.json", media_type="application/manifest+json")


@app.get("/sw.js")
def web_ui_sw_js() -> FileResponse:
    return _web_ui_asset("sw.js", media_type="application/javascript")


@app.get("/manifest.json")
def web_ui_manifest() -> FileResponse:
    return _web_ui_asset("manifest.json", media_type="application/manifest+json")


if WEB_UI_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_UI_ASSETS_DIR)), name="web-ui-assets")
    app.mount("/frontend/assets", StaticFiles(directory=str(WEB_UI_ASSETS_DIR)), name="frontend-assets")


@app.get("/frontend-reset")
def frontend_reset() -> Any:
        """Force-clear PWA caches/SW registrations.

        This route is intentionally NOT under /frontend so that a stale service worker
        (scoped to /frontend) cannot intercept it.
        """

        html = """<!doctype html>
<html lang=\"en\">
    <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>LandSense - Reset</title>
    </head>
    <body style=\"font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; padding: 18px;\">
        <h1 style=\"margin: 0 0 8px;\">Resetting LandSense…</h1>
        <p style=\"margin: 0 0 12px;\">Clearing service worker + cache, then reloading.</p>
        <pre id=\"log\" style=\"background:#111; color:#ddd; padding:12px; border-radius:10px; white-space: pre-wrap;\"></pre>
        <script>
            const log = (msg) => { document.getElementById('log').textContent += msg + '\n'; };
            (async () => {
                try {
                    if ('serviceWorker' in navigator) {
                        const regs = await navigator.serviceWorker.getRegistrations();
                        log(`Found ${regs.length} service worker registration(s).`);
                        await Promise.all(regs.map((r) => r.unregister()));
                        log('Unregistered service workers.');
                    } else {
                        log('No service worker support in this browser.');
                    }

                    if (window.caches && caches.keys) {
                        const keys = await caches.keys();
                        log(`Found ${keys.length} cache(s).`);
                        await Promise.all(keys.map((k) => caches.delete(k)));
                        log('Deleted caches.');
                    }
                } catch (e) {
                    log('Reset error: ' + (e && e.message ? e.message : String(e)));
                }

                const url = '/?reset=' + Date.now();
                log('Redirecting to ' + url);
                location.replace(url);
            })();
        </script>
    </body>
</html>"""

        return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "timestamp_utc": datetime.utcnow().isoformat()}


@app.get("/zones")
def zones() -> dict[str, Any]:
    return load_zones(ZONE_PATH)


@app.get("/alerts/my")
def my_alerts(
    limit: int = 20,
    payload: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return only the authenticated user's in-app alert history."""
    user_id = str(payload.get("sub", "")).strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid authenticated user")
    limit = max(1, min(limit, 100))
    alerts = db.scalars(
        select(Alert)
        .where(Alert.user_id == user_id)
        .order_by(Alert.id.desc())
        .limit(limit)
    ).all()
    return {
        "alerts": [
            {
                "id": alert.id,
                "risk_level": alert.risk_level,
                "message": alert.message,
                "timestamp": alert.timestamp,
                "delivery_status": alert.delivered_status,
                # All current in-app pending alerts are created by the Phase
                # 5.5 ADMIN_SIMULATION affected-zone workflow. No status is
                # changed when a citizen merely retrieves an alert.
                "source_type": "ADMIN_SIMULATION" if alert.delivered_status == "in_app_pending" else None,
            }
            for alert in alerts
        ],
        "count": len(alerts),
    }


@app.get("/landslides")
def landslide_inventory(
    limit: int = 1000,
    state: str | None = None,
    district: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return historical, dataset-backed landslide inventory points."""
    limit = max(1, min(limit, 5000))
    filters = []
    if state and state.strip():
        filters.append(func.lower(LandslideInventory.state) == state.strip().lower())
    if district and district.strip():
        filters.append(func.lower(LandslideInventory.district) == district.strip().lower())
    if year_from is not None:
        filters.append(LandslideInventory.initiation_year >= year_from)
    if year_to is not None:
        filters.append(LandslideInventory.initiation_year <= year_to)

    total = int(db.scalar(
        select(func.count()).select_from(LandslideInventory).where(*filters)
    ) or 0)
    records = db.scalars(
        select(LandslideInventory)
        .where(*filters)
        .order_by(LandslideInventory.initiation_year.desc().nullslast(), LandslideInventory.event_id)
        .limit(limit)
    ).all()
    date_range = db.execute(
        select(
            func.min(LandslideInventory.initiation_year),
            func.max(LandslideInventory.initiation_year),
        ).where(*filters)
    ).one()

    return {
        "source_type": "dataset",
        "source": "Field-validated landslide inventory",
        "classification": "historical landslide inventory",
        "total": total,
        "returned": len(records),
        "date_range": {"from": date_range[0], "to": date_range[1]},
        "landslides": [
            {
                "event_id": item.event_id,
                "latitude": item.latitude,
                "longitude": item.longitude,
                "initiation_year": item.initiation_year,
                "slide_name": item.slide_name,
                "state": item.state,
                "district": item.district,
                "subdivision_or_taluk": item.subdivision_or_taluk,
                "material_involved": item.material_involved,
                "movement_type": item.movement_type,
                "history_date_remarks": item.history_date_remarks,
                "source_page": item.source_page,
                "source": item.source_name,
                "source_type": item.source_type,
            }
            for item in records
        ],
    }


@app.get("/events")
def recent_events(limit: int = 30, db: Session = Depends(get_db)) -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    events = db.scalars(select(LocationEvent).order_by(LocationEvent.id.desc()).limit(limit)).all()
    return {"events": [
        {
            "id": item.id,
            "user_id": item.user_id,
            "timestamp_utc": item.timestamp_utc,
            "latitude": item.latitude,
            "longitude": item.longitude,
            "rainfall_mm": item.rainfall_mm,
            "ml_risk": item.ml_risk,
            "zone_risk": item.zone_risk,
            "final_risk": item.final_risk,
            "geofence_event": item.geofence_event,
            "active_zone_id": item.active_zone_id,
        }
        for item in events
    ]}


def _mask_phone(phone: str) -> str:
    value = str(phone or "")
    return f"{value[:3]}******{value[-4:]}" if len(value) >= 7 else ""


def _configured_zone(zone_id: str, zones_geojson: dict[str, Any]) -> dict[str, Any] | None:
    """Return a configured polygon by ID without accepting client geometry."""
    for feature in zones_geojson.get("features", []):
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        if str(properties.get("zone_id", "")) == zone_id and geometry.get("type") == "Polygon":
            return feature
    return None


def _historical_count_in_zone(db: Session, feature: dict[str, Any]) -> int:
    """Count historical inventory points in a configured polygon, not demo incidents."""
    ring = feature["geometry"]["coordinates"][0]
    longitudes = [float(point[0]) for point in ring]
    latitudes = [float(point[1]) for point in ring]
    rows = db.execute(
        select(LandslideInventory.latitude, LandslideInventory.longitude).where(
            LandslideInventory.latitude.between(min(latitudes), max(latitudes)),
            LandslideInventory.longitude.between(min(longitudes), max(longitudes)),
        )
    ).all()
    return sum(1 for latitude, longitude in rows if point_in_polygon(latitude, longitude, ring))


def _latest_zone_ml_prediction(db: Session, zone_id: str) -> tuple[str | None, float | None]:
    """Reuse the most recent persisted ML output for this zone when one exists."""
    event = db.scalar(
        select(LocationEvent)
        .where(LocationEvent.active_zone_id == zone_id)
        .order_by(LocationEvent.id.desc())
        .limit(1)
    )
    return (str(event.ml_risk).upper(), None) if event and event.ml_risk else (None, None)


def _admin_risk_summary(db: Session) -> dict[str, int]:
    """Return only aggregate risk counts; absent classifications remain zero."""
    summary = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    rows = db.execute(
        select(LocationEvent.final_risk, func.count(LocationEvent.id)).group_by(LocationEvent.final_risk)
    ).all()
    for risk, count in rows:
        normalized = str(risk or "").upper()
        if normalized in summary:
            summary[normalized] = int(count)
    return summary


@app.get("/admin/stats")
def admin_stats(
    _: dict = Depends(require_admin), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Read-only command-centre totals from the existing PostgreSQL tables."""
    total_users = int(db.scalar(select(func.count()).select_from(User)) or 0)
    active_locations = int(db.scalar(select(func.count()).select_from(Location)) or 0)
    alert_count = int(db.scalar(select(func.count()).select_from(Alert)) or 0)
    inventory_count = int(db.scalar(select(func.count()).select_from(LandslideInventory)) or 0)
    inventory_range = db.execute(select(
        func.min(LandslideInventory.initiation_year),
        func.max(LandslideInventory.initiation_year),
    )).one()
    zones_geo = load_zones(ZONE_PATH)
    zones = zones_geo.get("features", []) if isinstance(zones_geo, dict) else []
    return {
        "total_users": total_users,
        "active_locations": active_locations,
        "risk_zones": len(zones),
        "active_alerts": alert_count,
        "landslide_inventory": {
            "records": inventory_count,
            "source": "Field-validated landslide inventory",
            "source_type": "dataset",
            "status": "historical dataset",
            "date_range": {"from": inventory_range[0], "to": inventory_range[1]},
        },
        "risk_summary": _admin_risk_summary(db),
        "system": {
            "backend": "operational",
            "database": "connected",
            "authentication": "jwt-enabled",
        },
    }


@app.get("/admin/intelligence/zones/{zone_id}")
def admin_zone_intelligence(
    zone_id: str,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return evidence for one configured zone without triggering Phase 5 alerts."""
    feature = _configured_zone(zone_id.strip(), load_zones(ZONE_PATH))
    if not feature:
        raise HTTPException(status_code=404, detail="Configured intelligence zone not found")

    latitude, longitude = polygon_centroid(feature)
    try:
        weather = weather_service.fetch_weather_context(latitude, longitude)
    except Exception:
        weather = None

    try:
        historical_count = _historical_count_in_zone(db, feature)
        historical_available = True
    except (SQLAlchemyError, AttributeError, TypeError, ValueError):
        historical_count = None
        historical_available = False

    try:
        ml_risk, ml_confidence = _latest_zone_ml_prediction(db, zone_id.strip())
    except (SQLAlchemyError, AttributeError, TypeError, ValueError):
        ml_risk, ml_confidence = None, None

    try:
        incident = find_incident_for_zone(feature, load_incident_catalog(INCIDENT_CATALOG_PATH))
        incident_catalog_available = True
    except (OSError, ValueError, TypeError):
        incident = None
        incident_catalog_available = False

    intelligence = build_zone_intelligence(
        feature,
        weather=weather,
        historical_count=historical_count,
        historical_available=historical_available,
        ml_risk=ml_risk,
        ml_confidence=ml_confidence,
        overall_risk=combine_risk(ml_risk or "LOW", str(feature.get("properties", {}).get("risk_level") or "LOW")),
        incident=incident,
        incident_catalog_available=incident_catalog_available,
    )
    try:
        _population_feature, total_registered_users, members = _configured_zone_population(zone_id.strip(), db)
        inside_members = [member for member in members if member["inside"]]
        affected = {
            "status": "AVAILABLE",
            "totalRegisteredUsers": total_registered_users,
            "totalUsers": len(members),
            "insideUsers": len(inside_members),
            "outsideUsers": len(members) - len(inside_members),
            "realUsers": len(members),
            "recipientCount": len(inside_members),
            "smsEligibleCount": sum(bool(member["sms_eligible"]) for member in inside_members),
            "simulatedUsers": 0,
            "users": [_public_population_member(member) for member in members],
            "selectionAuthority": "EXISTING PHASE 5 SERVER GEOFENCE",
            "automaticAlert": False,
        }
    except (SQLAlchemyError, AttributeError, TypeError, ValueError):
        affected = {
            "status": "UNAVAILABLE", "totalRegisteredUsers": None, "totalUsers": None,
            "insideUsers": None, "outsideUsers": None, "realUsers": None,
            "recipientCount": None, "smsEligibleCount": None, "simulatedUsers": 0,
            "users": [], "selectionAuthority": "EXISTING PHASE 5 SERVER GEOFENCE",
            "automaticAlert": False,
        }
    intelligence["affected"] = affected
    assessment = intelligence.get("assessment") or {}
    audit_event_type = "INTELLIGENCE_UNAVAILABLE" if assessment.get("dataQuality") == "UNAVAILABLE" else "INTELLIGENCE_CALCULATED"
    try_record_audit_event(
        db,
        event_type=audit_event_type,
        mode="REAL",
        zone_id=str(feature.get("properties", {}).get("zone_id") or zone_id),
        zone_name=str(feature.get("properties", {}).get("name") or zone_id),
        risk=assessment.get("overallRisk"),
        message="Zone intelligence was unavailable." if audit_event_type == "INTELLIGENCE_UNAVAILABLE" else "Zone intelligence assessment calculated.",
        metadata={
            "confidence": assessment.get("confidence"),
            "dataQuality": assessment.get("dataQuality"),
            "recommendedAction": assessment.get("recommendedAction"),
            "automaticAlert": False,
        },
    )
    try_record_audit_event(
        db,
        event_type="AFFECTED_POPULATION_CALCULATED",
        mode="REAL",
        zone_id=str(feature.get("properties", {}).get("zone_id") or zone_id),
        zone_name=str(feature.get("properties", {}).get("name") or zone_id),
        risk=assessment.get("overallRisk"),
        message="Authoritative affected population calculated." if affected.get("status") == "AVAILABLE" else "Affected population was unavailable.",
        metadata={
            "affectedStatus": affected.get("status"),
            "realUsersInside": affected.get("insideUsers"),
            "realUsersOutside": affected.get("outsideUsers"),
            "eligibleRecipients": affected.get("recipientCount"),
            "smsEligibleRecipients": affected.get("smsEligibleCount"),
            "totalRegisteredUsers": affected.get("totalRegisteredUsers"),
        },
    )
    return intelligence


@app.get("/admin/audit/events")
def admin_audit_events(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category: str | None = Query(default=None, max_length=32),
    mode: str | None = Query(default=None, max_length=16),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return bounded, newest-first, privacy-safe Admin audit history."""
    normalized_category = str(category).strip().upper() if category else None
    normalized_mode = str(mode).strip().upper() if mode else None
    allowed_categories = {"SYSTEM", "INTELLIGENCE", "ADMIN_ACTION", "ALERT", "SIMULATION", "INCIDENT"}
    if normalized_category and normalized_category not in allowed_categories:
        raise HTTPException(status_code=422, detail="Unsupported audit category")
    if normalized_mode and normalized_mode not in {"REAL", "SIMULATION", "DEMO"}:
        raise HTTPException(status_code=422, detail="Unsupported audit mode")

    filters = []
    if normalized_category:
        filters.append(AuditEvent.category == normalized_category)
    if normalized_mode:
        filters.append(AuditEvent.mode == normalized_mode)
    count_statement = select(func.count()).select_from(AuditEvent)
    event_statement = select(AuditEvent)
    if filters:
        count_statement = count_statement.where(*filters)
        event_statement = event_statement.where(*filters)
    total = int(db.scalar(count_statement) or 0)
    events = db.scalars(event_statement.order_by(AuditEvent.id.desc()).offset(offset).limit(limit)).all()
    return {
        "events": [public_audit_event(event) for event in events],
        "total": total,
        "limit": limit,
        "offset": offset,
        "hasMore": offset + len(events) < total,
    }


@app.post("/admin/audit/events")
def record_admin_ui_audit_event(
    req: AdminAuditUiEventRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record controlled UI events; critical alert events are never accepted here."""
    event_type = req.event_type.strip().upper()
    if event_type not in {"ZONE_SELECTED", "INCIDENT_SELECTED", "DEMO_INCIDENT_LAUNCHED", "DEMO_ALERT_GENERATED"}:
        raise HTTPException(status_code=422, detail="This event must be recorded by its authoritative backend operation")

    zone = _configured_zone((req.zone_id or "").strip(), load_zones(ZONE_PATH)) if req.zone_id else None
    if event_type == "ZONE_SELECTED":
        if zone is None:
            raise HTTPException(status_code=404, detail="Configured audit zone not found")
        properties = zone.get("properties", {})
        event = try_record_audit_event(
            db,
            event_type=event_type,
            mode="REAL",
            zone_id=str(properties.get("zone_id") or ""),
            zone_name=str(properties.get("name") or properties.get("zone_id") or "Configured zone"),
            risk=properties.get("risk_level"),
            message="Configured zone selected for Admin review.",
            metadata={"automaticAlert": False},
            dedupe_seconds=30,
        )
    else:
        incidents = load_incident_catalog(INCIDENT_CATALOG_PATH)
        incident = next((item for item in incidents if str(item.get("id")) == str(req.incident_id or "")), None)
        if incident is None:
            raise HTTPException(status_code=404, detail="Audit incident scenario not found")
        if event_type.startswith("DEMO_") and not bool(simulation_mode.read_state().get("enabled")):
            raise HTTPException(status_code=409, detail="Simulation Mode must be active for demo audit events")
        mode = "DEMO" if event_type == "INCIDENT_SELECTED" else "SIMULATION"
        event = try_record_audit_event(
            db,
            event_type=event_type,
            mode=mode,
            risk=incident.get("demo_risk"),
            message="Demo incident scenario selected." if event_type == "INCIDENT_SELECTED" else "Demo incident launched." if event_type == "DEMO_INCIDENT_LAUNCHED" else "Demo alert generated; no real alert was sent.",
            metadata={
                "incidentTitle": incident.get("title"),
                "incidentStatus": incident.get("verification_status"),
                "sourceLabel": incident.get("source_label"),
                "locationPrecision": incident.get("location_precision"),
                "simulatedParticipants": req.simulated_count if event_type != "INCIDENT_SELECTED" else None,
                "externalNotificationsSuppressed": True,
            },
            dedupe_seconds=10 if event_type == "INCIDENT_SELECTED" else 0,
        )
    if event is None:
        raise HTTPException(status_code=503, detail="Audit persistence is unavailable")
    return {"event": public_audit_event(event)}


@app.get("/admin/users")
def admin_users(
    limit: int = 25,
    offset: int = 0,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    rows = db.execute(
        select(User, Location)
        .outerjoin(Location, Location.user_id == User.uid)
        .order_by(User.last_login.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    total = int(db.scalar(select(func.count()).select_from(User)) or 0)
    return {
        "users": [
            {
                "user_id": user.uid,
                "phone_masked": _mask_phone(user.phone_number),
                "role": user.role,
                "verification_status": "verified",
                "last_location": (
                    {"latitude": location.latitude, "longitude": location.longitude}
                    if location else None
                ),
                "last_updated": location.last_updated if location else None,
                "status": "active" if user.alert_enabled else "alerts-disabled",
            }
            for user, location in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/admin/locations")
def admin_locations(
    limit: int = 100,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    limit = max(1, min(limit, 250))
    locations = db.scalars(select(Location).order_by(Location.last_updated.desc()).limit(limit)).all()
    return {"locations": [
        {"user_id": item.user_id, "latitude": item.latitude, "longitude": item.longitude, "last_updated": item.last_updated}
        for item in locations
    ]}


@app.get("/admin/alerts")
def admin_alerts(
    limit: int = 25,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    alerts = db.scalars(select(Alert).order_by(Alert.id.desc()).limit(limit)).all()
    return {"alerts": [
        {
            "id": item.id,
            "user_id": item.user_id,
            "risk_level": item.risk_level,
            "timestamp": item.timestamp,
            "status": item.delivered_status,
        }
        for item in alerts
    ]}


@app.get("/admin/events")
def admin_events(
    limit: int = 30,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    events = db.scalars(select(LocationEvent).order_by(LocationEvent.id.desc()).limit(limit)).all()
    return {"events": [
        {
            "id": item.id,
            "user_id": item.user_id,
            "timestamp_utc": item.timestamp_utc,
            "latitude": item.latitude,
            "longitude": item.longitude,
            "rainfall_mm": item.rainfall_mm,
            "final_risk": item.final_risk,
            "geofence_event": item.geofence_event,
            "active_zone_id": item.active_zone_id,
        }
        for item in events
    ]}


@app.post("/admin/affected-zones/preview")
def preview_affected_zone_recipients(
    req: AffectedZonePreviewRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Preview registered users inside an existing zone; never creates alerts."""
    risk_level, message, feature, total_registered_users, recipients = _affected_zone_recipients(req, db)
    start_time = datetime.now(timezone.utc)
    public_recipients = [_public_affected_zone_recipient(recipient) for recipient in recipients]
    sms_config = sms_configuration_status()
    result = {
        "preview_only": True,
        "source_type": "ADMIN_SIMULATION",
        "affected_zone": {
            "zone_id": str(feature["properties"].get("zone_id")),
            "name": str(feature["properties"].get("name", "Configured zone")),
            "geometry": feature["geometry"],
            "risk_level": risk_level,
            "message": message,
            "start_time": start_time.isoformat(),
            "expires_at": (start_time + timedelta(minutes=req.duration_minutes)).isoformat(),
            "duration_minutes": req.duration_minutes,
        },
        "total_registered_users": total_registered_users,
        "recipient_count": len(recipients),
        "recipients": public_recipients,
        "sms_eligible_count": sum(bool(item["sms_eligible"]) for item in recipients),
        "sms_max_recipients": _sms_max_recipients(),
        "sms_configuration": sms_config,
        "simulation_mode": bool(simulation_mode.read_state().get("enabled")),
    }
    try_record_audit_event(
        db,
        event_type="RECIPIENT_PREVIEW_OPENED",
        mode="REAL",
        zone_id=str(feature["properties"].get("zone_id") or req.zone_id),
        zone_name=str(feature["properties"].get("name") or req.zone_id),
        risk=risk_level,
        message="Authoritative Phase 5 recipient preview opened; no alert was activated.",
        metadata={
            "recipientCount": len(recipients),
            "smsEligibleRecipients": result["sms_eligible_count"],
            "totalRegisteredUsers": total_registered_users,
            "status": "PREVIEW_ONLY",
            "automaticAlert": False,
        },
    )
    return result


def _sms_max_recipients() -> int:
    try:
        configured = int(os.getenv("SMS_MAX_RECIPIENTS", "25"))
    except ValueError:
        configured = 25
    return max(1, min(configured, 500))


def _public_affected_zone_recipient(recipient: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in recipient.items() if not key.startswith("_")}


def _safe_citizen_id(user_id: str) -> str:
    digest = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:8].upper()
    return f"Citizen #{digest}"


def _public_population_member(member: dict[str, Any]) -> dict[str, Any]:
    return {
        "displayId": _safe_citizen_id(str(member["_user_id"])),
        "status": "INSIDE" if member["inside"] else "OUTSIDE",
        "inside": bool(member["inside"]),
        "recipientEligible": bool(member["inside"]),
        "smsEligible": bool(member["sms_eligible"]) if member["inside"] else False,
        "latitude": member["latitude"],
        "longitude": member["longitude"],
        "lastUpdated": member["last_updated"],
        "currentRisk": member["current_risk"],
    }


def _configured_zone_population(
    zone_id: str, db: Session
) -> tuple[dict[str, Any], int, list[dict[str, Any]]]:
    """Return server-calculated located users for one configured Phase 5 zone."""
    feature = _configured_zone(zone_id, load_zones(ZONE_PATH))
    if feature is None:
        raise HTTPException(status_code=404, detail="Configured affected zone not found")
    selected_geojson = {"type": "FeatureCollection", "features": [feature]}
    total_registered_users = int(db.scalar(select(func.count()).select_from(User)) or 0)
    rows = db.execute(select(User, Location).join(Location, Location.user_id == User.uid)).all()
    members: list[dict[str, Any]] = []
    for user, location in rows:
        inside = bool(find_zone_matches(location.latitude, location.longitude, selected_geojson))
        current_risk = None
        if inside:
            current_risk = db.scalar(
                select(LocationEvent.final_risk)
                .where(LocationEvent.user_id == user.uid)
                .order_by(LocationEvent.timestamp_utc.desc())
                .limit(1)
            )
        members.append({
            "_user_id": str(user.uid),
            "_phone_number": str(user.phone_number or ""),
            "_alert_enabled": bool(getattr(user, "alert_enabled", 0)),
            "inside": inside,
            "sms_eligible": bool(getattr(user, "alert_enabled", 0)) and bool(E164_PATTERN.match(str(user.phone_number or ""))),
            "latitude": location.latitude,
            "longitude": location.longitude,
            "last_updated": location.last_updated,
            "current_risk": current_risk,
        })
    return feature, total_registered_users, members


def _feature_population(feature: dict[str, Any], db: Session) -> tuple[int, list[dict[str, Any]]]:
    """Run the existing point-in-polygon geofence against a supplied server feature."""
    selected_geojson = {"type": "FeatureCollection", "features": [feature]}
    total_registered_users = int(db.scalar(select(func.count()).select_from(User)) or 0)
    rows = db.execute(select(User, Location).join(Location, Location.user_id == User.uid)).all()
    members: list[dict[str, Any]] = []
    for user, location in rows:
        inside = bool(find_zone_matches(location.latitude, location.longitude, selected_geojson))
        members.append({
            "_user_id": str(user.uid),
            "_phone_number": str(user.phone_number or ""),
            "_alert_enabled": bool(getattr(user, "alert_enabled", 0)),
            "inside": inside,
            "sms_eligible": inside and bool(getattr(user, "alert_enabled", 0)) and bool(E164_PATTERN.match(str(user.phone_number or ""))),
            "latitude": location.latitude,
            "longitude": location.longitude,
            "last_updated": location.last_updated,
            "current_risk": None,
        })
    return total_registered_users, members


def _httpsms_export_preview(zone_id: str, db: Session, recipient_ids: set[str] | None = None) -> dict[str, Any]:
    simulation_state = simulation_mode.read_state()
    if not simulation_state.get("enabled"):
        raise HTTPException(status_code=409, detail="Enable Simulation Mode before preparing an httpSMS export.")
    try:
        simulation_feature = simulation_state.get("synthetic_zone")
        if simulation_state.get("is_simulation") and simulation_feature and str((simulation_feature.get("properties") or {}).get("zone_id")) == zone_id:
            feature = simulation_feature
            _total, members = _feature_population(feature, db)
        else:
            feature, _total, members = _configured_zone_population(zone_id, db)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Unable to retrieve registered users. Please retry.") from exc
    except (ValueError, OSError, TypeError, KeyError, IndexError) as exc:
        raise HTTPException(status_code=422, detail="Danger-zone geometry is unavailable or invalid.") from exc
    props = feature.get("properties", {})
    risk = str(props.get("risk_level") or "").upper()
    location = str(props.get("name") or zone_id)
    geometry = feature.get("geometry") or {}
    rings = geometry.get("coordinates") or []
    try:
        valid_geometry = geometry.get("type") == "Polygon" and bool(rings) and all(
            len(ring) >= 4 and ring[0] == ring[-1] and all(
                len(point) >= 2 and math.isfinite(float(point[0])) and math.isfinite(float(point[1]))
                and -180 <= float(point[0]) <= 180 and -90 <= float(point[1]) <= 90
                for point in ring
            ) for ring in rings
        )
    except (TypeError, ValueError, IndexError):
        valid_geometry = False
    if not valid_geometry:
        raise HTTPException(status_code=422, detail="Danger-zone geometry is unavailable or invalid. A configured Polygon is required.")
    # The existing matcher tests the outer ring. Exclude any polygon holes for export.
    for member in members:
        if member["inside"] and any(point_in_polygon(member["latitude"], member["longitude"], hole) for hole in rings[1:]):
            member["inside"] = False
    # Eligibility never implies selection. Omitted selections export nobody.
    from services.httpsms_export import normalize_phone
    affected_count = sum(bool(member["inside"]) for member in members)
    public_recipients = [{"display_id": _safe_citizen_id(m["_user_id"]),
                          "phone_masked": _mask_phone(m["_phone_number"]),
                          "sms_eligible": bool(m["_alert_enabled"] and normalize_phone(m["_phone_number"]))}
                         for m in members if m["inside"]]
    selected_ids = recipient_ids or set()
    eligible_ids = {item["display_id"] for item in public_recipients if item["sms_eligible"]}
    if not selected_ids.issubset(eligible_ids):
        raise HTTPException(status_code=422, detail="Select only eligible users inside this danger zone.")
    selected_members = [m for m in members if m["inside"] and _safe_citizen_id(m["_user_id"]) in selected_ids]
    if simulation_state.get("is_simulation") and simulation_feature is feature:
        message = str((simulation_state.get("alert_preview") or {}).get("message") or "")
    else:
        try:
            message = generate_alert_message(risk, location)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = select_sms_recipients(selected_members)
    result.update(affected_count=affected_count, eligible_count=len(eligible_ids), selected_count=len(selected_ids))
    sender = os.getenv("HTTPSMS_FROM_NUMBER", "").strip()
    sender_error = None
    if not sender:
        sender_error = MISSING_SENDER
    elif not re.fullmatch(r"\+?[1-9][0-9]{7,14}", sender):
        sender_error = "HTTPSMS_FROM_NUMBER is invalid. Configure an international sender number."
    error = sender_error
    if not error and not result["sms_eligible_count"]:
        error = "No SMS-eligible users selected. Explicitly select recipients inside this danger zone."
    revision = hashlib.sha256(repr((result, sender, risk, location, geometry, sorted(selected_ids))).encode()).hexdigest()
    return {**result, "zone_id": zone_id, "location": location, "risk_level": risk,
            "revision": revision,
            "synthetic": True, "message": message, "sender_configured": not bool(sender_error),
            "download_enabled": not bool(error), "error": error, "_sender": sender,
            "recipients": public_recipients,
            "invalid_recipients": [_safe_citizen_id(uid) for uid in result["_invalid_user_ids"]],
            "filename": export_filename(risk, location)}


@app.get("/admin/affected-zones/{zone_id}/httpsms-preview")
def preview_httpsms_excel(zone_id: str, _: dict = Depends(require_admin), db: Session = Depends(get_db), recipient_ids: str | None = None):
    selected = set(filter(None, (recipient_ids or "").split(","))) if recipient_ids is not None else None
    result = _httpsms_export_preview(zone_id, db, selected)
    return {key: value for key, value in result.items() if not key.startswith("_")}


@app.get("/admin/affected-zones/{zone_id}/httpsms-excel")
def download_httpsms_excel(zone_id: str, _: dict = Depends(require_admin), db: Session = Depends(get_db), revision: str | None = None, recipient_ids: str | None = None):
    selected = set(filter(None, (recipient_ids or "").split(","))) if recipient_ids is not None else None
    result = _httpsms_export_preview(zone_id, db, selected)
    if not result["download_enabled"]:
        raise HTTPException(status_code=422, detail=result["error"])
    if revision is not None and revision != result["revision"]:
        raise HTTPException(status_code=409, detail="Recipients or zone information changed. Refresh recipients before downloading.")
    try:
        content = build_workbook(result["_sender"], result["_phones"], result["message"])
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to generate httpSMS Excel. Please retry.") from exc
    return Response(content=content,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"',
                             "Cache-Control": "no-store", "X-Recipient-Count": str(result["sms_eligible_count"])})


def _offline_demo_area(zone_id: str, db: Session) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve one configured red zone and return privacy-safe inside users."""
    feature, _total_registered_users, members = _configured_zone_population(zone_id.strip(), db)
    properties = feature.get("properties", {})
    risk = str(properties.get("risk_level") or "").upper()
    if risk not in {"HIGH", "CRITICAL"}:
        raise HTTPException(status_code=422, detail="Offline alert demonstrations require a configured HIGH or CRITICAL zone")

    recipients = []
    for member in members:
        if not member["inside"]:
            continue
        recipients.append({
            "displayId": _safe_citizen_id(str(member["_user_id"])),
            "status": "INSIDE ZONE",
            "userType": "REAL_REGISTERED_USER",
            "smsRegistered": bool(E164_PATTERN.match(str(member["_phone_number"] or ""))),
            "bluetoothDemoEligible": True,
        })
    return feature, recipients


def _incident_affected_feature(incident_id: str) -> dict[str, Any]:
    """Build polygonal GeoJSON from an existing catalog incident circle."""
    incident = next(
        (item for item in load_incident_catalog(INCIDENT_CATALOG_PATH) if str(item.get("id")) == incident_id),
        None,
    )
    if incident is None:
        raise HTTPException(status_code=404, detail="Configured incident demonstration not found")
    risk = str(incident.get("demo_risk") or "").upper()
    if risk not in {"HIGH", "CRITICAL"}:
        raise HTTPException(status_code=422, detail="Offline alert demonstrations require a HIGH or CRITICAL incident")
    latitude = float(incident["latitude"])
    longitude = float(incident["longitude"])
    radius_meters = float(incident.get("affected_radius_meters") or 0)
    if radius_meters <= 0:
        raise HTTPException(status_code=422, detail="Incident affected-radius geometry is unavailable")
    ring = []
    for index in range(49):
        angle = 2 * math.pi * index / 48
        north = math.cos(angle) * radius_meters
        east = math.sin(angle) * radius_meters
        ring.append([
            longitude + east / (111320 * math.cos(math.radians(latitude))),
            latitude + north / 111320,
        ])
    return {
        "type": "Feature",
        "properties": {
            "zone_id": f"incident:{incident_id}", "incident_id": incident_id,
            "name": str(incident.get("title") or "Incident affected area"),
            "risk_level": risk, "area_type": "INCIDENT_RADIUS",
        },
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def _offline_demo_incident_area(incident_id: str, db: Session) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Evaluate a catalog incident radius through the existing geofence helper."""
    feature = _incident_affected_feature(incident_id.strip())
    selected_geojson = {"type": "FeatureCollection", "features": [feature]}
    rows = db.execute(select(User, Location).join(Location, Location.user_id == User.uid)).all()
    members = []
    for user, location in rows:
        if not find_zone_matches(location.latitude, location.longitude, selected_geojson):
            continue
        members.append({
            "displayId": _safe_citizen_id(str(user.uid)),
            "status": "INSIDE AFFECTED RADIUS",
            "userType": "REAL_REGISTERED_USER",
            "smsRegistered": bool(E164_PATTERN.match(str(user.phone_number or ""))),
            "bluetoothDemoEligible": True,
        })
    return feature, members


def _resolve_offline_demo_area(req: OfflineDemoAreaRequest, db: Session) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if bool(req.zone_id) == bool(req.incident_id):
        raise HTTPException(status_code=422, detail="Select exactly one configured zone or incident affected area")
    if req.zone_id:
        return _offline_demo_area(req.zone_id, db)
    return _offline_demo_incident_area(str(req.incident_id), db)


def _offline_demo_preview_payload(feature: dict[str, Any], recipients: list[dict[str, Any]]) -> dict[str, Any]:
    properties = feature.get("properties", {})
    return {
        "simulation": True,
        "offline_delivery_simulation": True,
        "no_real_alert_sent": True,
        "area": {
            "areaType": str(properties.get("area_type") or "CONFIGURED_ZONE"),
            "zoneId": None if properties.get("incident_id") else str(properties.get("zone_id") or ""),
            "incidentId": str(properties.get("incident_id")) if properties.get("incident_id") else None,
            "name": str(properties.get("name") or "Configured zone"),
            "risk": str(properties.get("risk_level") or "HIGH").upper(),
            "geometryType": str(feature.get("geometry", {}).get("type") or "Polygon"),
        },
        "affectedRegisteredUsers": len(recipients),
        "simulatedParticipants": 0,
        "recipients": recipients,
        "selectionAuthority": "EXISTING PHASE 5 SERVER GEOFENCE",
    }


@app.post("/admin/offline-demo-alerts/preview")
def preview_offline_demo_alert(
    req: OfflineDemoAreaRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Calculate demo recipients only while the explicit safety mode is active."""
    if not bool(simulation_mode.read_state().get("enabled")):
        raise HTTPException(status_code=409, detail="Simulation Mode must be active for offline alert demonstrations")
    feature, recipients = _resolve_offline_demo_area(req, db)
    return _offline_demo_preview_payload(feature, recipients)


@app.post("/admin/offline-demo-alerts/send")
def send_offline_demo_alert(
    req: OfflineDemoSendRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Generate local demo records without Alert writes or external transports."""
    if not bool(simulation_mode.read_state().get("enabled")):
        raise HTTPException(status_code=409, detail="Simulation Mode must be active for offline alert demonstrations")
    if req.confirmed is not True:
        raise HTTPException(status_code=422, detail="Explicit confirmation is required")
    channels = list(dict.fromkeys(str(channel).strip().upper() for channel in req.channels))
    if not channels or any(channel not in {"SMS_DEMO", "BLUETOOTH_DEMO"} for channel in channels):
        raise HTTPException(status_code=422, detail="Only SMS_DEMO and BLUETOOTH_DEMO channels are supported")

    # Recalculate at send time.  The client cannot submit recipient IDs.
    feature, recipients = _resolve_offline_demo_area(req, db)
    properties = feature.get("properties", {})
    risk = str(properties.get("risk_level") or "HIGH").upper()
    area_name = str(properties.get("name") or "Configured zone")
    message = (
        f"LANDSLIDE EMERGENCY\n\nYou are currently inside a {risk} risk area.\n\n"
        "Move away from the affected zone and follow safer-route guidance.\n\n"
        "OFFLINE DEMO\nNo real message was sent."
    )
    deliveries = simulate_offline_deliveries(recipients, channels, message)
    sms_count = sum(item["channel"] == "SMS_DEMO" for item in deliveries)
    bluetooth_count = sum(item["channel"] == "BLUETOOTH_DEMO" for item in deliveries)
    audit_event = try_record_audit_event(
        db,
        event_type="OFFLINE_DEMO_ALERT_COMPLETED",
        mode="SIMULATION",
        zone_id=str(properties.get("zone_id") or req.zone_id or req.incident_id),
        zone_name=area_name,
        risk=risk,
        message="Offline delivery demonstration completed; no real alert was sent.",
        metadata={
            "channels": channels,
            "recipientCount": len(recipients),
            "smsDemoCount": sms_count,
            "bluetoothDemoCount": bluetooth_count,
            "realSmsCount": 0,
            "realBluetoothCount": 0,
            "realAlertCount": 0,
            "offlineDeliverySimulation": True,
            "externalNotificationsSuppressed": True,
        },
    )
    now = datetime.now(timezone.utc).isoformat()
    return {
        **_offline_demo_preview_payload(feature, recipients),
        "status": "DEMO_DELIVERED",
        "channels": channels,
        "deliveries": deliveries,
        "summary": {
            "smsDemo": sms_count,
            "bluetoothDemo": bluetooth_count,
            "realSms": 0,
            "realBluetooth": 0,
            "realAlerts": 0,
        },
        "generatedAt": now,
        "message": message,
        "demoAlert": {
            "id": f"offline-demo-{properties.get('zone_id')}-{now}",
            "simulation": True,
            "offline_demo": True,
            "title": "LANDSLIDE EMERGENCY",
            "location_name": area_name,
            "district": "Configured risk area",
            "date": now[:10],
            "demo_risk": risk,
            "short_description": f"You are inside a {risk} risk zone. Move away from the affected area.",
            "safety_guidance": "Follow safer-route guidance and official emergency instructions.",
            "notification_message": message,
            "launched_at": now,
            "delivery_channels": channels,
            "no_real_alert_sent": True,
        },
        "auditEvent": public_audit_event(audit_event) if audit_event is not None else None,
    }


def _affected_zone_recipients(
    req: AffectedZonePreviewRequest, db: Session
) -> tuple[str, str, dict[str, Any], int, list[dict[str, Any]]]:
    """Validate a configured zone and calculate recipients from Neon locations."""
    risk_level = req.risk_level.strip().upper()
    if risk_level not in RISK_SCORE:
        raise HTTPException(status_code=422, detail="risk_level must be LOW, MEDIUM, HIGH, or CRITICAL")

    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="message must not be blank")

    feature, total_registered_users, members = _configured_zone_population(req.zone_id.strip(), db)
    recipients: list[dict[str, Any]] = []
    for member in members:
        if not member["inside"]:
            continue
        recipients.append(
            {
                "user_id": member["_user_id"],
                "phone_masked": _mask_phone(member["_phone_number"]),
                "sms_eligible": member["sms_eligible"],
                "_sms_phone_number": member["_phone_number"],
                "latitude": member["latitude"],
                "longitude": member["longitude"],
                "last_updated": member["last_updated"],
                "current_risk": member["current_risk"],
            }
        )
    return risk_level, message, feature, total_registered_users, recipients


@app.post("/admin/affected-zones/activate")
def activate_affected_zone_alert(
    req: AffectedZonePreviewRequest,
    _admin_payload: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Persist in-app alerts, then optionally SMS newly targeted eligible users."""
    if bool(simulation_mode.read_state().get("enabled")):
        raise HTTPException(
            status_code=409,
            detail="Real configured-zone activation is disabled while Admin Simulation Mode is active",
        )
    try:
        risk_level, message, feature, _total_registered_users, recipients = _affected_zone_recipients(req, db)
    except HTTPException as exc:
        configured = _configured_zone(req.zone_id.strip(), load_zones(ZONE_PATH))
        properties = (configured or {}).get("properties", {})
        try_record_audit_event(
            db,
            event_type="ALERT_ACTIVATION_FAILED",
            mode="REAL",
            zone_id=str(properties.get("zone_id") or req.zone_id),
            zone_name=properties.get("name"),
            risk=req.risk_level,
            message="Configured-zone alert activation was rejected.",
            metadata={"reason": "Configured zone was not found" if exc.status_code == 404 else "Activation request was rejected by server validation", "status": "REJECTED"},
        )
        raise
    activated_at = datetime.now(timezone.utc)
    cutoff = (activated_at - timedelta(minutes=req.duration_minutes)).isoformat()
    recipient_ids = [str(recipient["user_id"]) for recipient in recipients]

    existing_user_ids: set[str] = set()
    if recipient_ids:
        # The existing alert schema has no zone column. This deliberately
        # conservative per-user dedupe suppresses the same in-app risk/message
        # within the requested active duration, avoiding duplicate activation.
        existing_user_ids = set(
            db.scalars(
                select(Alert.user_id).where(
                    Alert.user_id.in_(recipient_ids),
                    Alert.risk_level == risk_level,
                    Alert.message == message,
                    Alert.delivered_status == "in_app_pending",
                    Alert.timestamp >= cutoff,
                )
            ).all()
        )

    alerts_to_create = [
        Alert(
            user_id=user_id,
            risk_level=risk_level,
            message=message,
            timestamp=activated_at.isoformat(),
            delivered_status="in_app_pending",
        )
        for user_id in recipient_ids
        if user_id not in existing_user_ids
    ]
    try:
        if alerts_to_create:
            db.add_all(alerts_to_create)
            db.commit()
    except SQLAlchemyError:
        db.rollback()
        try_record_audit_event(
            db,
            event_type="ALERT_ACTIVATION_FAILED",
            mode="REAL",
            zone_id=str(feature["properties"].get("zone_id") or req.zone_id),
            zone_name=str(feature["properties"].get("name") or req.zone_id),
            risk=risk_level,
            message="Configured-zone alert activation failed before completion.",
            metadata={"reason": "Database activation transaction failed", "status": "FAILED"},
        )
        raise

    created_count = len(alerts_to_create)
    created_user_ids = {str(alert.user_id) for alert in alerts_to_create}
    sms_eligible_count = sum(bool(recipient["sms_eligible"]) for recipient in recipients)
    sms_candidates = [
        recipient for recipient in recipients
        if recipient["sms_eligible"] and str(recipient["user_id"]) in created_user_ids
    ]
    simulation_enabled = False
    sms_config = sms_configuration_status()
    sms_limit = _sms_max_recipients()
    sms_attempted = 0
    sms_sent = 0
    sms_failed = 0
    sms_suppressed = 0

    base_status = "in_app_pending" if created_count else ("deduplicated" if recipient_ids else "no_recipients")
    status = base_status
    if req.send_sms:
        # Eligible users already covered by an active deduplicated alert are
        # deliberately not sent the same SMS again.
        sms_suppressed = sms_eligible_count - len(sms_candidates)
        if simulation_enabled:
            sms_suppressed += len(sms_candidates)
            status = "simulation_sms_suppressed"
        elif len(sms_candidates) > sms_limit:
            sms_suppressed += len(sms_candidates)
            status = "sms_batch_limit_exceeded"
        elif not bool(sms_config.get("configured")):
            sms_suppressed += len(sms_candidates)
            status = "sms_provider_unavailable"
        elif not sms_candidates:
            status = "deduplicated" if existing_user_ids else "no_sms_eligible"
        else:
            sms_message = f"LANDSense — {risk_level} RISK\n{message}"
            for recipient in sms_candidates:
                sms_attempted += 1
                try:
                    result = send_sms_alert(
                        str(recipient["_sms_phone_number"]),
                        sms_message,
                        allow_simulated_fallback=False,
                    )
                except Exception:
                    sms_failed += 1
                    continue
                delivery_status = str(result.get("status", "failed")).lower()
                if delivery_status == "sent":
                    sms_sent += 1
                elif delivery_status in {"unavailable", "simulated_offline"}:
                    sms_suppressed += 1
                else:
                    sms_failed += 1

            if sms_sent and not sms_failed and sms_suppressed == 0:
                status = "sms_sent"
            elif sms_sent:
                status = "sms_partial"
            elif sms_failed:
                status = "sms_failed"
            else:
                status = "sms_suppressed"

    result = {
        "zone_id": str(feature["properties"].get("zone_id")),
        "risk_level": risk_level,
        "recipient_count": len(recipients),
        "in_app_created_count": created_count,
        "activated_at": activated_at.isoformat(),
        "status": status,
        "deduplicated_count": len(recipient_ids) - created_count,
        "sms_eligible_count": sms_eligible_count,
        "sms_attempted": sms_attempted,
        "sms_sent": sms_sent,
        "sms_failed": sms_failed,
        "sms_suppressed": sms_suppressed,
        "sms_requested": req.send_sms,
        "sms_provider": sms_config.get("provider", "twilio"),
        "sms_configured": bool(sms_config.get("configured")),
        "sms_max_recipients": sms_limit,
        "simulation_mode": simulation_enabled,
        "external_sms_sent": sms_sent > 0,
    }
    event_type = "ALERT_ACTIVATED" if created_count > 0 else "ALERT_ACTIVATION_FAILED"
    try_record_audit_event(
        db,
        event_type=event_type,
        mode="REAL",
        zone_id=result["zone_id"],
        zone_name=str(feature["properties"].get("name") or req.zone_id),
        risk=risk_level,
        message="Configured-zone alert activation completed." if created_count > 0 else "Configured-zone alert activation created no new alerts.",
        metadata={
            "recipientCount": len(recipients),
            "status": status,
            "smsRequested": req.send_sms,
            "smsSent": sms_sent,
            "smsFailed": sms_failed,
            "smsSuppressed": sms_suppressed,
            "externalNotificationsSuppressed": not bool(sms_sent),
        },
    )
    return result


@app.get("/admin/simulation/state")
def admin_simulation_state(
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    return simulation_mode.read_state()


@app.get("/admin/simulation/kodagu/locations")
def admin_kodagu_simulation_locations(_: dict = Depends(require_admin)) -> dict[str, Any]:
    return {
        "locations": list(KODAGU_LOCATIONS),
        "risk_levels": ["HIGH", "CRITICAL"],
        "source_note": "Location references derived from the uploaded Geological Survey of India report on landslide susceptibility mapping in parts of Coorg (Kodagu), Karnataka.",
        "classification_note": "Simulation risk levels HIGH and CRITICAL are LandSense demonstration states and are not direct classifications from the GSI report.",
    }


def _active_demo_state(scenario_revision: str | None = None) -> dict[str, Any]:
    state = simulation_mode.read_state()
    if not (state.get("enabled") and state.get("is_simulation")):
        raise HTTPException(status_code=409, detail="Enable Kodagu Simulation Mode to view the demonstration.")
    if scenario_revision is not None and state.get("enabled_at_utc") != scenario_revision:
        raise HTTPException(status_code=409, detail="Simulation changed. Refresh the demonstration before exporting.")
    return state


@app.get("/admin/simulation/demo")
@app.get("/admin/simulation")
@app.get("/frontend/admin/simulation")
@app.get("/frontend/admin/simulation/demo")
def simulation_demo_page() -> FileResponse:
    # Static shell has no simulation data; ProtectedRoute gates the UI and
    # every data/export endpoint independently requires Admin authorization.
    return _web_ui_asset("index.html", media_type="text/html")


@app.get("/admin/simulation/demo/state")
def admin_simulation_demo(_: dict = Depends(require_admin), db: Session = Depends(get_db)):
    state = simulation_mode.read_state()
    active = bool(state.get("enabled") and state.get("is_simulation"))
    preview = None
    if active and state.get("synthetic_zone"):
        result = _httpsms_export_preview(state["synthetic_zone"]["properties"]["zone_id"], db)
        _active_demo_state(state["enabled_at_utc"])
        preview = {key: value for key, value in result.items() if not key.startswith("_")}
    return {"active": active, "state": state if active else None, "preview": preview}


def _demo_export_preview(req: SimulationDemoExportRequest, db: Session) -> dict[str, Any]:
    state = _active_demo_state(req.scenario_revision)
    feature = state.get("synthetic_zone")
    if not feature:
        raise HTTPException(status_code=422, detail="Danger-zone geometry unavailable for this simulation location.")
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Enter a simulation message before generating Excel.")
    result = _httpsms_export_preview(feature["properties"]["zone_id"], db, set(req.recipient_ids))
    result["message"] = message
    result["revision"] = hashlib.sha256(repr((result["revision"], message, req.scenario_revision)).encode()).hexdigest()
    _active_demo_state(req.scenario_revision)
    return result


@app.post("/admin/simulation/demo/httpsms-preview")
def admin_demo_excel_preview(req: SimulationDemoExportRequest, _: dict = Depends(require_admin), db: Session = Depends(get_db)):
    result = _demo_export_preview(req, db)
    return {key: value for key, value in result.items() if not key.startswith("_")}


@app.post("/admin/simulation/demo/httpsms-excel")
def admin_demo_excel(req: SimulationDemoExportRequest, _: dict = Depends(require_admin), db: Session = Depends(get_db)):
    result = _demo_export_preview(req, db)
    if not result["download_enabled"]:
        raise HTTPException(status_code=422, detail=result["error"])
    if not req.revision or req.revision != result["revision"]:
        raise HTTPException(status_code=409, detail="Recipients or message changed. Refresh recipients before downloading.")
    try:
        content = build_workbook(result["_sender"], result["_phones"], result["message"])
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to generate httpSMS Excel. Please retry.") from exc
    _active_demo_state(req.scenario_revision)
    return Response(content=content,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"',
                             "Cache-Control": "no-store", "X-Recipient-Count": str(result["sms_eligible_count"])})


@app.post("/admin/simulation/kodagu/create")
def admin_create_kodagu_simulation(
    req: KodaguSimulationRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    zones_geo = load_zones(ZONE_PATH)
    # Geography may only be reused when an exact-name feature is explicitly
    # marked verified. No fuzzy location matching or coordinate invention.
    verified_feature = next((feature for feature in zones_geo.get("features", []) if
        str((feature.get("properties") or {}).get("name") or "").strip() == req.location.strip()
        and (feature.get("properties") or {}).get("verified") is True), None)
    try:
        state = simulation_mode.create_kodagu(location=req.location, risk=req.risk_level, verified_feature=verified_feature)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    feature = state.get("synthetic_zone")
    recipients: list[dict[str, Any]] = []
    sms_eligible = 0
    route = state.get("route")
    if feature:
        _total, members = _feature_population(feature, db)
        recipients = [{
            "display_id": _safe_citizen_id(member["_user_id"]),
            "phone_masked": _mask_phone(member["_phone_number"]),
            "sms_eligible": bool(member["sms_eligible"]),
        } for member in members if member["inside"]]
        sms_eligible = sum(bool(member["sms_eligible"]) for member in members if member["inside"])
        geometry = feature.get("geometry") or {}
        ring = (geometry.get("coordinates") or [[]])[0]
        center = None
        if ring:
            center = (sum(float(p[1]) for p in ring) / len(ring), sum(float(p[0]) for p in ring) / len(ring))
        safe_features = [item for item in zones_geo.get("features", []) if str((item.get("properties") or {}).get("risk_level") or "").upper() in {"SAFE", "LOW"}]
        if center and safe_features:
            guidance = safe_route_service.build_guidance(center[0], center[1], {"type": "FeatureCollection", "features": [feature, *safe_features]}, req.risk_level)
            if guidance and (guidance.get("route") or {}).get("status") == "ok":
                route = guidance
    state = simulation_mode.set_kodagu_results(recipients=recipients, sms_eligible_users=sms_eligible, route=route)
    return {"state": state, "generated": bool(feature), "message": "Generated synthetic zone for simulation." if feature else "Synthetic zone unavailable: no verified project geometry exists for this report-backed location."}


@app.post("/admin/simulation/kodagu/trigger")
def admin_trigger_kodagu_simulation(req: KodaguSimulationTriggerRequest, _: dict = Depends(require_admin)) -> dict[str, Any]:
    try:
        state = simulation_mode.trigger_kodagu(req.recipient_ids)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"state": state, "sent": False, "external_notifications_sent": 0, "message": "Demo alert confirmed. No SMS or live alert was sent."}


@app.post("/admin/simulation/kodagu/reset")
def admin_reset_kodagu_simulation(_: dict = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    previous = simulation_mode.read_state()
    state = simulation_mode.set_state(enabled=False, forced_risk="LOW", escalation_enabled=False, scenario_name="Normal", zones_geo=None)
    try_record_audit_event(db, event_type="SIMULATION_STOPPED", mode="SIMULATION", zone_id=previous.get("danger_zone_id"), zone_name=previous.get("location"), risk=previous.get("effective_risk"), message="Kodagu simulation reset; real data was not modified.", metadata={"isSimulation": True})
    return {"state": state, "real_data_modified": False}


@app.post("/admin/simulation/state")
def admin_simulation_toggle(
    req: SimulationToggleRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    previous = simulation_mode.read_state()
    zones_geo = load_zones(ZONE_PATH)
    state = simulation_mode.set_state(
        enabled=req.enabled,
        forced_risk=req.forced_risk,
        escalation_enabled=req.escalation_enabled,
        scenario_name=req.scenario_name,
        zones_geo=zones_geo,
    )
    if req.enabled != bool(previous.get("enabled")):
        try_record_audit_event(
            db,
            event_type="SIMULATION_STARTED" if req.enabled else "SIMULATION_STOPPED",
            mode="SIMULATION",
            zone_id=state.get("danger_zone_id") or previous.get("danger_zone_id"),
            zone_name=state.get("danger_zone_name") or previous.get("danger_zone_name"),
            risk=state.get("effective_risk") if req.enabled else previous.get("effective_risk"),
            message="Admin Simulation Mode started; real activation remains disabled." if req.enabled else "Admin Simulation Mode stopped and simulated state was cleared.",
            metadata={
                "scenarioName": req.scenario_name if req.enabled else previous.get("scenario_name"),
                "forcedRisk": req.forced_risk if req.enabled else previous.get("forced_risk"),
                "externalNotificationsSuppressed": True,
            },
        )
    return {"state": state}


@app.get("/admin/simulation/events")
def admin_simulation_events(
    limit: int = 100,
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    return {"events": simulation_mode.list_events(limit=limit)}


@app.post("/predict-risk")
def predict_risk(req: PredictRequest, _: dict = Depends(require_auth)) -> dict[str, Any]:
    weather = weather_service.fetch_weather_context(req.latitude, req.longitude)
    rain = weather_service.fetch_rainfall_mm(req.latitude, req.longitude)
    pred = predict(
        deformation_mm=req.deformation_mm,
        velocity_mm_yr=req.velocity_mm_yr,
        coherence=req.coherence,
        rainfall_mm=rain["rainfall_mm"],
        slope_deg=req.slope_deg,
        soil_moisture_pct=req.soil_moisture_pct,
        elevation_m=req.elevation_m,
        aspect_deg=180.0,
        ndvi=req.ndvi,
        model=req.model,
    )
    zones_geo = load_zones(ZONE_PATH)
    matches = find_zone_matches(req.latitude, req.longitude, zones_geo)
    zone_risk = highest_zone_risk(matches)
    final_risk = combine_risk(pred["risk_label"], zone_risk)
    evacuation = safe_route_service.build_guidance(req.latitude, req.longitude, zones_geo, final_risk, weather=weather)

    return {
        "prediction": pred,
        "rainfall": rain,
        "weather": weather,
        "zone_risk": zone_risk,
        "final_risk": final_risk,
        "zone_matches": [m.__dict__ for m in matches],
        "evacuation": evacuation,
    }


@app.post("/location-update")
def legacy_location_update(
    req: LocationUpdateRequest,
    background_tasks: BackgroundTasks,
    payload: dict = Depends(require_auth),
) -> dict[str, Any]:
    user_id = str(payload.get("sub", "")).strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid authenticated user")
    req.user_id = user_id
    if req.phone_number:
        req.phone_number = _validate_e164(req.phone_number)
    result = _evaluate_location(
        req,
        background_tasks=background_tasks,
        user_phone=None,
        alert_enabled=False,
    )
    store_location(user_id, req.latitude, req.longitude)
    return result


@app.post("/route-safe")
def route_safe(req: RouteRequest, _: dict = Depends(require_auth)) -> dict[str, Any]:
    zones_geo = load_zones(ZONE_PATH)
    route = plan_safe_route(
        start_lat=req.start_latitude,
        start_lon=req.start_longitude,
        end_lat=req.end_latitude,
        end_lon=req.end_longitude,
        zones_geojson=zones_geo,
    )
    if route["status"] != "ok":
        raise HTTPException(status_code=404, detail="No safe route found")
    return route


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend_api:app", host="0.0.0.0", port=8000, reload=True)
