"""
FastAPI backend for LandSense:
- Public API for risk prediction and geofencing
- Geo-fencing entry/exit detection
- Real-time ML risk prediction
- SQLite-backed users/locations/alerts
- Twilio SMS alert queue with cooldown protection
"""

from __future__ import annotations

import re
import sqlite3
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from backend.auth.router import router as auth_router
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
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
from backend.auth.middleware import JWTAuthMiddleware
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
from geofencing import (
    detect_fence_event,
    find_zone_matches,
    highest_zone_risk,
    load_zones,
    primary_zone_id,
)
from predict import predict
from route_planner import plan_safe_route
from sms_service import send_sms_alert
from services.extension_loader import ExtensionLoader
from services.safe_route_service import SafeRouteService
from services.simulation_mode_service import SimulationModeService


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "location_events.db"
ZONE_PATH = BASE_DIR / "config" / "risk_zones.geojson"
WEB_UI_DIR = BASE_DIR / "web-ui"
WEB_UI_DIST_DIR = WEB_UI_DIR / "dist"
WEB_UI_ASSETS_DIR = WEB_UI_DIST_DIR / "assets"

ALERT_TEXT = "Landslide warning: You are in a high-risk zone. Move to a safer location immediately."
RISK_SCORE = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
ALERT_COOLDOWN_SECONDS = 600
SIMULATION_AUTH_HEADER = "X-Simulation-Admin-Key"
SIMULATION_SESSION_HEADER = "X-Simulation-Session"
 


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
    forced_risk: str = "HIGH"
    escalation_enabled: bool = True
    scenario_name: str = "Demo Danger Mode"


class SimulationSessionRequest(BaseModel):
    admin_key: str = Field(..., min_length=1)


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
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS location_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            timestamp_utc TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            rainfall_mm REAL NOT NULL,
            ml_risk TEXT NOT NULL,
            zone_risk TEXT NOT NULL,
            final_risk TEXT NOT NULL,
            geofence_event TEXT,
            active_zone_id TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def save_event(payload: dict[str, Any]) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO location_events (
            user_id, timestamp_utc, latitude, longitude, rainfall_mm,
            ml_risk, zone_risk, final_risk, geofence_event, active_zone_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["user_id"],
            payload["timestamp_utc"],
            payload["latitude"],
            payload["longitude"],
            payload["rainfall_mm"],
            payload["ml_risk"],
            payload["zone_risk"],
            payload["final_risk"],
            payload.get("geofence_event"),
            payload.get("active_zone_id"),
        ),
    )
    conn.commit()
    conn.close()


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


def _require_simulation_admin(
    x_simulation_admin_key: str | None,
    x_simulation_session: str | None,
) -> None:
    if not simulation_mode.is_configured():
        raise HTTPException(status_code=503, detail="Simulation mode admin key is not configured")
    if simulation_mode.validate_admin_session(x_simulation_session):
        return
    if simulation_mode.authorize(x_simulation_admin_key):
        return
    raise HTTPException(status_code=403, detail="Forbidden: invalid simulation session or admin key")


def _create_simulation_session(admin_key: str) -> dict[str, str]:
    if not simulation_mode.is_configured():
        raise HTTPException(status_code=503, detail="Simulation mode admin key is not configured")
    if not simulation_mode.authorize(admin_key):
        raise HTTPException(status_code=403, detail="Forbidden: invalid simulation admin key")
    return simulation_mode.create_admin_session()


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
        send_threshold = "HIGH"
        if simulation_mode.should_suppress_external_notifications():
            send_threshold = "CRITICAL"
        alert = process_reading(reading, send_only_above=send_threshold)
        alert_summary = {
            "alert_id": alert.alert_id,
            "risk_level": alert.risk_level,
            "message": ALERT_TEXT,
            "simulated": simulation_enabled,
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


@app.get("/events")
def recent_events(limit: int = 30) -> dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM location_events ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"events": rows}


@app.get("/admin/simulation/state")
def admin_simulation_state(
    x_simulation_admin_key: str | None = Header(default=None, alias=SIMULATION_AUTH_HEADER),
    x_simulation_session: str | None = Header(default=None, alias=SIMULATION_SESSION_HEADER),
) -> dict[str, Any]:
    _require_simulation_admin(x_simulation_admin_key, x_simulation_session)
    return simulation_mode.read_state()


@app.post("/admin/simulation/state")
def admin_simulation_toggle(
    req: SimulationToggleRequest,
    x_simulation_admin_key: str | None = Header(default=None, alias=SIMULATION_AUTH_HEADER),
    x_simulation_session: str | None = Header(default=None, alias=SIMULATION_SESSION_HEADER),
) -> dict[str, Any]:
    _require_simulation_admin(x_simulation_admin_key, x_simulation_session)
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
    x_simulation_admin_key: str | None = Header(default=None, alias=SIMULATION_AUTH_HEADER),
    x_simulation_session: str | None = Header(default=None, alias=SIMULATION_SESSION_HEADER),
) -> dict[str, Any]:
    _require_simulation_admin(x_simulation_admin_key, x_simulation_session)
    return {"events": simulation_mode.list_events(limit=limit)}


@app.post("/admin/simulation/session")
def admin_simulation_session(req: SimulationSessionRequest) -> dict[str, Any]:
    session = _create_simulation_session(req.admin_key)
    return {
        "session": session,
        "ttl_minutes": int(os.getenv("SIMULATION_SESSION_TTL_MIN", "30")),
    }


@app.delete("/admin/simulation/session")
def admin_simulation_revoke_session(
    x_simulation_session: str | None = Header(default=None, alias=SIMULATION_SESSION_HEADER),
) -> dict[str, Any]:
    revoked = simulation_mode.revoke_admin_session(x_simulation_session)
    return {"revoked": revoked}


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
