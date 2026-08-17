from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RISK_SCORE = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
ALLOWED_FORCED_RISKS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


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
        if not state["enabled"]:
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
