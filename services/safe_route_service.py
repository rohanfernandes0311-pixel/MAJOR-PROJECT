"""Safe route evacuation helpers.

This service enriches an already computed risk result with evacuation guidance
only when the risk level is HIGH or CRITICAL.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from route_planner import haversine_km, plan_safe_route


EVACUATION_RISKS = {"HIGH", "CRITICAL"}
SAFE_ZONE_RISKS = {"SAFE", "LOW"}


def _normalize_risk(level: str | None) -> str:
    return str(level or "").strip().upper()


def _zone_center(feature: dict[str, Any]) -> tuple[float, float] | None:
    coords = feature.get("geometry", {}).get("coordinates", [])
    if not coords:
        return None
    ring = coords[0] if coords and isinstance(coords[0], list) else coords
    if not ring:
        return None
    sum_lat = 0.0
    sum_lon = 0.0
    count = 0
    for pair in ring:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        sum_lon += float(pair[0])
        sum_lat += float(pair[1])
        count += 1
    if not count:
        return None
    return sum_lat / count, sum_lon / count


def _bearing_direction(start_lat: float, start_lon: float, end_lat: float, end_lon: float) -> str:
    lat1 = math.radians(start_lat)
    lat2 = math.radians(end_lat)
    diff_lon = math.radians(end_lon - start_lon)

    x = math.sin(diff_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(diff_lon)
    bearing = (math.degrees(math.atan2(x, y)) + 360.0) % 360.0

    directions = [
        ("north", 0.0),
        ("north-east", 45.0),
        ("east", 90.0),
        ("south-east", 135.0),
        ("south", 180.0),
        ("south-west", 225.0),
        ("west", 270.0),
        ("north-west", 315.0),
    ]
    nearest = min(directions, key=lambda item: min(abs(bearing - item[1]), 360.0 - abs(bearing - item[1])))
    return nearest[0]


def _pick_safe_zone(latitude: float, longitude: float, zones_geojson: dict[str, Any]) -> dict[str, Any] | None:
    zones = zones_geojson.get("features", [])
    candidates: list[dict[str, Any]] = []
    fallback_candidates: list[dict[str, Any]] = []

    for feature in zones:
        if not isinstance(feature, dict):
            continue
        center = _zone_center(feature)
        if not center:
            continue
        props = feature.get("properties", {}) or {}
        level = _normalize_risk(props.get("risk_level"))
        name = str(props.get("name") or props.get("zone_name") or props.get("id") or "Safer zone").strip()
        zone = {
            "name": name,
            "risk_level": level or "LOW",
            "latitude": center[0],
            "longitude": center[1],
            "zone_id": str(props.get("zone_id") or props.get("id") or name).strip(),
            "elevation_hint": str(props.get("elevation_hint") or props.get("elevation") or "higher ground"),
            "road_accessibility": str(props.get("road_accessibility") or "unknown"),
        }
        distance = haversine_km(latitude, longitude, zone["latitude"], zone["longitude"])
        zone["distance_km"] = round(distance, 3)

        if level in SAFE_ZONE_RISKS:
            candidates.append(zone)
        else:
            fallback_candidates.append(zone)

    pool = candidates or fallback_candidates
    if not pool:
        return None
    return sorted(pool, key=lambda item: item["distance_km"])[0]


@dataclass(slots=True)
class SafeRouteService:
    def build_guidance(
        self,
        latitude: float,
        longitude: float,
        zones_geojson: dict[str, Any],
        risk_level: str,
        weather: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        normalized_risk = _normalize_risk(risk_level)
        if normalized_risk not in EVACUATION_RISKS:
            return None

        safe_zone = _pick_safe_zone(latitude, longitude, zones_geojson)
        if not safe_zone:
            return {
                "enabled": True,
                "risk_level": normalized_risk,
                "route": {"path": [], "distance_km": None, "status": "no_safe_zone"},
                "safe_zone": None,
                "estimated_direction": "north",
                "temporary_shelter": "Nearest safer location",
                "safer_elevation_zone": "Higher ground",
                "road_accessibility_status": "Unknown",
                "summary": "Evacuate toward the nearest available higher ground.",
                "weather_context": weather or {},
            }

        route = plan_safe_route(
            start_lat=latitude,
            start_lon=longitude,
            end_lat=safe_zone["latitude"],
            end_lon=safe_zone["longitude"],
            zones_geojson=zones_geojson,
        )

        return {
            "enabled": True,
            "risk_level": normalized_risk,
            "route": route,
            "safe_zone": safe_zone,
            "estimated_direction": _bearing_direction(latitude, longitude, safe_zone["latitude"], safe_zone["longitude"]),
            "temporary_shelter": safe_zone["name"],
            "safer_elevation_zone": safe_zone["elevation_hint"],
            "road_accessibility_status": safe_zone["road_accessibility"],
            "summary": f"Move toward {safe_zone['name']} and follow the safest accessible route.",
            "weather_context": weather or {},
        }