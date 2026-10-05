from __future__ import annotations

import json
import threading
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RISK_SCORE = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
ALLOWED_FORCED_RISKS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
KODAGU_SIMULATION_RISKS = {"HIGH", "CRITICAL"}
KODAGU_LOCATIONS = (
    "Madikeri", "Virajpet", "Chittalli", "Perumbadi", "Makutta",
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _centroid_from_ring(ring: list[list[float]]) -> tuple[float, float] | None:
    if not ring:
        return None
    valid = [p for p in ring if isinstance(p, (list, tuple)) and len(p) >= 2]
    if not valid:
        return None
    lon = sum(float(p[0]) for p in valid) / len(valid)
    lat = sum(float(p[1]) for p in valid) / len(valid)
    return (lat, lon)


@dataclass(slots=True)
class SimulationState:
    enabled: bool = False
    forced_risk: str = "LOW"
    escalation_enabled: bool = False
    scenario_name: str = "Normal"
    enabled_at_utc: str | None = None
    danger_zone_id: str | None = None
    danger_zone_name: str | None = None
    danger_latitude: float | None = None
    danger_longitude: float | None = None
    is_simulation: bool = False
    location: str | None = None
    synthetic_zone: dict[str, Any] | None = None
    geometry_status: str = "not_created"
    alert_preview: dict[str, Any] | None = None
    recipients: list[dict[str, Any]] | None = None
    selected_recipient_ids: list[str] | None = None
    affected_registered_users: int = 0
    sms_eligible_users: int = 0
    route: dict[str, Any] | None = None
    triggered: bool = False


class SimulationModeService:
    """Isolated emergency simulation state and override policy."""

    def __init__(self, base_dir: Path) -> None:
        self._lock = threading.Lock()
        self._state = SimulationState()
        self._event_log = base_dir / "alerts" / "simulation_events.jsonl"
        self._event_log.parent.mkdir(parents=True, exist_ok=True)

    def read_state(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def set_state(
        self,
        *,
        enabled: bool,
        forced_risk: str,
        escalation_enabled: bool,
        scenario_name: str,
        zones_geo: dict[str, Any] | None,
    ) -> dict[str, Any]:
        forced = str(forced_risk or "LOW").upper()
        if forced not in ALLOWED_FORCED_RISKS:
            forced = "LOW"

        with self._lock:
            if enabled:
                zone = self._pick_danger_zone(zones_geo)
                self._state.enabled = True
                self._state.forced_risk = forced
                self._state.escalation_enabled = bool(escalation_enabled)
                self._state.scenario_name = (scenario_name or "Normal").strip() or "Normal"
                self._state.enabled_at_utc = _utc_iso()
                self._state.danger_zone_id = zone.get("zone_id")
                self._state.danger_zone_name = zone.get("zone_name")
                self._state.danger_latitude = zone.get("latitude")
                self._state.danger_longitude = zone.get("longitude")
            else:
                self._state = SimulationState()
            snapshot = self._snapshot_locked()

        self.record_event(
            "simulation_mode_toggled",
            {
                "enabled": bool(enabled),
                "forced_risk": forced,
                "escalation_enabled": bool(escalation_enabled),
                "scenario_name": scenario_name,
            },
        )
        return snapshot

    def apply_location_override(self, latitude: float, longitude: float) -> dict[str, Any]:
        state = self.read_state()
        if not state["enabled"] or state.get("is_simulation"):
            return {
                "enabled": False,
                "latitude": latitude,
                "longitude": longitude,
            }

        return {
            "enabled": True,
            "latitude": state.get("danger_latitude") or latitude,
            "longitude": state.get("danger_longitude") or longitude,
            "zone_id": state.get("danger_zone_id"),
            "zone_name": state.get("danger_zone_name"),
            "scenario_name": state.get("scenario_name"),
        }

    def create_kodagu(self, *, location: str, risk: str, verified_feature: dict[str, Any] | None = None) -> dict[str, Any]:
        """Create isolated admin demo state without manufacturing geography.

        Geometry is copied only from an existing exact-name configured feature. When
        none exists the simulation remains usable as an alert preview and reports
        geometry/route/recipient calculation as unavailable.
        """
        clean_location = str(location or "").strip()
        clean_risk = str(risk or "").strip().upper()
        if clean_location not in KODAGU_LOCATIONS:
            raise ValueError("Unsupported Kodagu simulation location.")
        if clean_risk not in KODAGU_SIMULATION_RISKS:
            raise ValueError("Simulation Risk Level must be HIGH or CRITICAL.")

        geometry = None
        if verified_feature and str((verified_feature.get("properties") or {}).get("name") or "").strip() == clean_location:
            candidate = verified_feature.get("geometry") or {}
            if candidate.get("type") == "Polygon" and candidate.get("coordinates"):
                geometry = candidate
        zone = None
        if geometry:
            zone = {
                "type": "Feature",
                "properties": {
                    "zone_id": f"KODAGU-SIM-{KODAGU_LOCATIONS.index(clean_location) + 1:02d}",
                    "name": clean_location,
                    "risk_level": clean_risk,
                    "risk_label": "LandSense Simulation Risk Level",
                    "is_simulation": True,
                    "synthetic": True,
                    "source_geometry": "existing_project_verified_geometry",
                },
                "geometry": geometry,
            }
        message = self._kodagu_message(clean_risk, clean_location)
        with self._lock:
            self._state = SimulationState(
                enabled=True,
                forced_risk=clean_risk,
                scenario_name=f"Kodagu / {clean_location}",
                enabled_at_utc=_utc_iso(),
                danger_zone_id=(zone or {}).get("properties", {}).get("zone_id"),
                danger_zone_name=clean_location,
                is_simulation=True,
                location=clean_location,
                synthetic_zone=zone,
                geometry_status="synthetic_from_verified_project_geometry" if zone else "unavailable_no_verified_geometry",
                alert_preview={"risk": clean_risk, "location": clean_location, "message": message, "recipients": 0},
                recipients=[],
                route={"status": "unavailable", "message": "Demo route unavailable: verified geometry and a safe destination are required."},
            )
            snapshot = self._snapshot_locked()
        self.record_event("kodagu_simulation_created", {"location": clean_location, "risk": clean_risk, "is_simulation": True, "geometry_status": snapshot["geometry_status"]})
        return snapshot

    def set_kodagu_results(self, *, recipients: list[dict[str, Any]], sms_eligible_users: int, route: dict[str, Any] | None) -> dict[str, Any]:
        with self._lock:
            self._state.recipients = recipients
            self._state.affected_registered_users = len(recipients)
            self._state.sms_eligible_users = int(sms_eligible_users)
            if self._state.alert_preview is not None:
                self._state.alert_preview["recipients"] = len(recipients)
            if route is not None:
                self._state.route = route
            return self._snapshot_locked()

    @staticmethod
    def admin_actor(location: str, risk: str, position: list[float] | None, feature: dict[str, Any]) -> dict[str, Any]:
        """Validate an existing simulation position without deriving or persisting GPS."""
        from geofencing import point_in_polygon
        unavailable = {"status": "unavailable", "is_simulation": True,
                       "message": "Admin simulation actor unavailable: no existing position verified inside this simulation zone."}
        if location not in KODAGU_LOCATIONS or risk not in KODAGU_SIMULATION_RISKS:
            return unavailable
        geometry = feature.get("geometry") or {}
        rings = geometry.get("coordinates") or []
        try:
            if geometry.get("type") != "Polygon" or not rings or not position or len(position) != 2:
                return unavailable
            latitude, longitude = position
            if not all(math.isfinite(value) for value in position) or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                return unavailable
            if not point_in_polygon(latitude, longitude, rings[0]) or any(point_in_polygon(latitude, longitude, hole) for hole in rings[1:]):
                return unavailable
        except (TypeError, ValueError, IndexError):
            return unavailable
        return {"status": "available", "label": "ADMIN SIMULATION ACTOR", "is_simulation": True,
                "location": location, "risk": risk, "latitude": latitude, "longitude": longitude,
                "source": "existing_simulation_location_center", "recipientEligible": False}

    def trigger_kodagu(self, recipient_ids: list[str] | None = None) -> dict[str, Any]:
        with self._lock:
            if not self._state.enabled or not self._state.is_simulation:
                raise ValueError("Create a Kodagu simulation before triggering the preview.")
            allowed = {str(item.get("display_id")) for item in (self._state.recipients or []) if item.get("sms_eligible")}
            selected = list(dict.fromkeys(str(value) for value in (recipient_ids or []) if str(value) in allowed))
            self._state.selected_recipient_ids = selected
            if self._state.alert_preview is not None:
                self._state.alert_preview["recipients"] = len(selected)
            self._state.triggered = True
            snapshot = self._snapshot_locked()
        self.record_event("kodagu_simulation_preview_confirmed", {"location": snapshot["location"], "risk": snapshot["effective_risk"], "external_notifications_sent": 0})
        return snapshot

    @staticmethod
    def _kodagu_message(risk: str, location: str) -> str:
        if risk == "HIGH":
            guidance = "Please stay alert, avoid unstable slopes, and follow the recommended safer route."
        else:
            guidance = "Move away from unstable slopes and follow the recommended safer route."
        return f"LANDsense SIMULATION ALERT: {risk.title()} landslide risk simulated in {location}. {guidance}"

    def effective_forced_risk(self) -> str:
        with self._lock:
            return self._effective_forced_risk_locked()

    def should_suppress_external_notifications(self) -> bool:
        with self._lock:
            return self._should_suppress_external_notifications_locked()

    def record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        item = {
            "timestamp_utc": _utc_iso(),
            "event_type": event_type,
            "payload": payload,
        }
        try:
            with self._event_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except Exception:
            # Simulation logging must never interfere with primary workflows.
            return

    def list_events(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self._event_log.exists():
            return []
        try:
            lines = self._event_log.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []

        recent: list[dict[str, Any]] = []
        for line in lines[-max(1, limit) :]:
            try:
                recent.append(json.loads(line))
            except Exception:
                continue
        return list(reversed(recent))

    def _snapshot_locked(self) -> dict[str, Any]:
        effective_risk = self._effective_forced_risk_locked() if self._state.enabled else "LOW"
        return {
            "enabled": self._state.enabled,
            "forced_risk": self._state.forced_risk,
            "effective_risk": effective_risk,
            "escalation_enabled": self._state.escalation_enabled,
            "scenario_name": self._state.scenario_name,
            "enabled_at_utc": self._state.enabled_at_utc,
            "danger_zone_id": self._state.danger_zone_id,
            "danger_zone_name": self._state.danger_zone_name,
            "danger_latitude": self._state.danger_latitude,
            "danger_longitude": self._state.danger_longitude,
            "external_notifications_suppressed": self._should_suppress_external_notifications_locked(),
            "is_simulation": self._state.is_simulation,
            "location": self._state.location,
            "synthetic_zone": self._state.synthetic_zone,
            "geometry_status": self._state.geometry_status,
            "alert_preview": self._state.alert_preview,
            "recipients": list(self._state.recipients or []),
            "selected_recipient_ids": list(self._state.selected_recipient_ids or []),
            "affected_registered_users": self._state.affected_registered_users,
            "sms_eligible_users": self._state.sms_eligible_users,
            "route": self._state.route,
            "triggered": self._state.triggered,
        }

    def _effective_forced_risk_locked(self) -> str:
        if not self._state.enabled:
            return "LOW"

        base = self._state.forced_risk
        if not self._state.escalation_enabled:
            return base

        enabled_at_raw = self._state.enabled_at_utc
        if not enabled_at_raw:
            return base

        try:
            enabled_at = datetime.fromisoformat(enabled_at_raw)
        except ValueError:
            return base

        elapsed_seconds = (datetime.now(timezone.utc) - enabled_at).total_seconds()
        if elapsed_seconds >= 90:
            return "CRITICAL"
        return base

    def _should_suppress_external_notifications_locked(self) -> bool:
        # Simulation is always display-only; it must never activate live alerts.
        return bool(self._state.enabled)

    def _pick_danger_zone(self, zones_geo: dict[str, Any] | None) -> dict[str, Any]:
        features = list((zones_geo or {}).get("features") or [])
        ranked: list[tuple[int, dict[str, Any]]] = []

        for feature in features:
            props = dict(feature.get("properties") or {})
            geometry = dict(feature.get("geometry") or {})
            risk = str(props.get("risk_level", "MEDIUM")).upper()
            score = RISK_SCORE.get(risk, 0)
            coords = geometry.get("coordinates") or []
            ring = []
            if geometry.get("type") == "Polygon" and coords:
                ring = coords[0] if isinstance(coords[0], list) else []
            elif geometry.get("type") == "MultiPolygon" and coords and isinstance(coords[0], list):
                first_poly = coords[0]
                if first_poly and isinstance(first_poly[0], list):
                    ring = first_poly[0]

            centroid = _centroid_from_ring(ring)
            if not centroid:
                continue

            ranked.append(
                (
                    score,
                    {
                        "zone_id": props.get("zone_id"),
                        "zone_name": props.get("name"),
                        "latitude": centroid[0],
                        "longitude": centroid[1],
                    },
                )
            )

        if not ranked:
            return {}

        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked[0][1]
