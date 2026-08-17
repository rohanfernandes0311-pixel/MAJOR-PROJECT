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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from backend.auth.router import router as auth_router
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
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
from database.models import Alert, LandslideInventory, Location, LocationEvent, User
from geofencing import (
    detect_fence_event,
    find_zone_matches,
    highest_zone_risk,
    load_zones,
    primary_zone_id,
)
from predict import predict
from route_planner import plan_safe_route
from sms_service import send_sms_alert, sms_configuration_status
from services.extension_loader import ExtensionLoader
from services.safe_route_service import SafeRouteService
from services.simulation_mode_service import SimulationModeService


BASE_DIR = Path(__file__).parent
ZONE_PATH = BASE_DIR / "config" / "risk_zones.geojson"
WEB_UI_DIR = BASE_DIR / "web-ui"
WEB_UI_DIST_DIR = WEB_UI_DIR / "dist"
WEB_UI_ASSETS_DIR = WEB_UI_DIST_DIR / "assets"

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
    start_latitude: float
    start_longitude: float
    end_latitude: float
    end_longitude: float


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


class AffectedZonePreviewRequest(BaseModel):
    """Admin-only, non-persistent recipient preview for a configured zone."""

    zone_id: str = Field(..., min_length=1, max_length=100)
    risk_level: str = Field(..., min_length=1, max_length=16)
    message: str = Field(..., min_length=1, max_length=1000)
    duration_minutes: int = Field(..., ge=5, le=10080)
    send_sms: bool = False

    class Config:
        extra = "forbid"


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
    simulation_enabled = bool(simulation_state["enabled"])
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
    return {
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


def _sms_max_recipients() -> int:
    try:
        configured = int(os.getenv("SMS_MAX_RECIPIENTS", "25"))
    except ValueError:
        configured = 25
    return max(1, min(configured, 500))


def _public_affected_zone_recipient(recipient: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in recipient.items() if not key.startswith("_")}


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

    zones_geo = load_zones(ZONE_PATH)
    feature = _configured_zone(req.zone_id.strip(), zones_geo)
    if feature is None:
        raise HTTPException(status_code=404, detail="Configured affected zone not found")

    # Reuse the existing geofence implementation instead of duplicating
    # point-in-polygon logic. The client never supplies geometry.
    selected_geojson = {"type": "FeatureCollection", "features": [feature]}
    total_registered_users = int(db.scalar(select(func.count()).select_from(User)) or 0)
    rows = db.execute(select(User, Location).join(Location, Location.user_id == User.uid)).all()
    recipients: list[dict[str, Any]] = []
    for user, location in rows:
        if not find_zone_matches(location.latitude, location.longitude, selected_geojson):
            continue
        current_risk = db.scalar(
            select(LocationEvent.final_risk)
            .where(LocationEvent.user_id == user.uid)
            .order_by(LocationEvent.timestamp_utc.desc())
            .limit(1)
        )
        recipients.append(
            {
                "user_id": user.uid,
                "phone_masked": _mask_phone(user.phone_number),
                "sms_eligible": bool(getattr(user, "alert_enabled", 0)) and bool(E164_PATTERN.match(str(user.phone_number or ""))),
                "_sms_phone_number": str(user.phone_number or ""),
                "latitude": location.latitude,
                "longitude": location.longitude,
                "last_updated": location.last_updated,
                "current_risk": current_risk,
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
    risk_level, message, feature, _total_registered_users, recipients = _affected_zone_recipients(req, db)
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
        raise

    created_count = len(alerts_to_create)
    created_user_ids = {str(alert.user_id) for alert in alerts_to_create}
    sms_eligible_count = sum(bool(recipient["sms_eligible"]) for recipient in recipients)
    sms_candidates = [
        recipient for recipient in recipients
        if recipient["sms_eligible"] and str(recipient["user_id"]) in created_user_ids
    ]
    simulation_enabled = bool(simulation_mode.read_state().get("enabled"))
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

    return {
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


@app.get("/admin/simulation/state")
def admin_simulation_state(
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    return simulation_mode.read_state()


@app.post("/admin/simulation/state")
def admin_simulation_toggle(
    req: SimulationToggleRequest,
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    zones_geo = load_zones(ZONE_PATH)
    state = simulation_mode.set_state(
        enabled=req.enabled,
        forced_risk=req.forced_risk,
        escalation_enabled=req.escalation_enabled,
        scenario_name=req.scenario_name,
        zones_geo=zones_geo,
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
