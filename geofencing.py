"""
Geo-fencing engine for landslide-prone polygons.

Provides:
- Zone loading from GeoJSON
- Point-in-polygon checks
- Entry/exit event detection
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RISK_SCORE = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


@dataclass
class ZoneMatch:
    zone_id: str
    name: str
    risk_level: str


@dataclass
class FenceEvent:
    user_id: str
    event: str
    previous_zone: str | None
    current_zone: str | None


def load_zones(geojson_path: str | Path) -> dict[str, Any]:
    path = Path(geojson_path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("type") != "FeatureCollection":
        raise ValueError("GeoJSON must be a FeatureCollection")
    return data


def point_in_polygon(latitude: float, longitude: float, polygon: list[list[float]]) -> bool:
    """Ray-casting algorithm. Polygon points are [lon, lat]."""
    x = longitude
    y = latitude
    inside = False
    n = len(polygon)
    if n < 3:
        return False

    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]

        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def find_zone_matches(latitude: float, longitude: float, zones_geojson: dict[str, Any]) -> list[ZoneMatch]:
    matches: list[ZoneMatch] = []

    for feature in zones_geojson.get("features", []):
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "Polygon":
            continue

        rings = geometry.get("coordinates", [])
        if not rings:
            continue

        outer_ring = rings[0]
        if point_in_polygon(latitude, longitude, outer_ring):
            props = feature.get("properties", {})
            matches.append(
                ZoneMatch(
                    zone_id=str(props.get("zone_id", "UNKNOWN")),
                    name=str(props.get("name", "Unnamed Zone")),
                    risk_level=str(props.get("risk_level", "MEDIUM")).upper(),
                )
            )
    return matches


def highest_zone_risk(matches: list[ZoneMatch]) -> str:
    if not matches:
        return "LOW"
    return max((m.risk_level for m in matches), key=lambda x: RISK_SCORE.get(x, 0))


def primary_zone_id(matches: list[ZoneMatch]) -> str | None:
    return matches[0].zone_id if matches else None


def detect_fence_event(user_id: str, previous_zone: str | None, current_zone: str | None) -> FenceEvent | None:
    if previous_zone is None and current_zone is not None:
        return FenceEvent(user_id=user_id, event="ENTER", previous_zone=None, current_zone=current_zone)
    if previous_zone is not None and current_zone is None:
        return FenceEvent(user_id=user_id, event="EXIT", previous_zone=previous_zone, current_zone=None)
    if previous_zone != current_zone:
        return FenceEvent(
            user_id=user_id,
            event="ZONE_SWITCH",
            previous_zone=previous_zone,
            current_zone=current_zone,
        )
    return None
