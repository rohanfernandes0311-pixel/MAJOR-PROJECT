"""Evacuation route suggestion using Dijkstra over a small geo-grid."""

from __future__ import annotations

import heapq
import math
from typing import Any

from geofencing import point_in_polygon


RISK_COST = {"LOW": 1.0, "MEDIUM": 8.0, "HIGH": 1000.0, "CRITICAL": 10000.0}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def zone_risk_at(latitude: float, longitude: float, zones_geojson: dict[str, Any]) -> str:
    found = "LOW"
    for feature in zones_geojson.get("features", []):
        geom = feature.get("geometry", {})
        if geom.get("type") != "Polygon":
            continue
        rings = geom.get("coordinates", [])
        if not rings:
            continue
        if point_in_polygon(latitude, longitude, rings[0]):
            level = str(feature.get("properties", {}).get("risk_level", "MEDIUM")).upper()
            if RISK_COST.get(level, 1.0) > RISK_COST.get(found, 1.0):
                found = level
    return found


def _index_to_coord(i: int, j: int, lat0: float, lon0: float, step: float) -> tuple[float, float]:
    return lat0 + i * step, lon0 + j * step


def _coord_to_index(lat: float, lon: float, lat0: float, lon0: float, step: float, n: int) -> tuple[int, int]:
    i = round((lat - lat0) / step)
    j = round((lon - lon0) / step)
    return max(0, min(n - 1, i)), max(0, min(n - 1, j))


def plan_safe_route(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    zones_geojson: dict[str, Any],
    grid_size: int = 35,
    step_deg: float = 0.003,
) -> dict:
    """
    Compute a safe route using Dijkstra, penalizing medium/high-risk grid cells.
    """
    center_lat = (start_lat + end_lat) / 2.0
    center_lon = (start_lon + end_lon) / 2.0
    lat0 = center_lat - (grid_size // 2) * step_deg
    lon0 = center_lon - (grid_size // 2) * step_deg

    start = _coord_to_index(start_lat, start_lon, lat0, lon0, step_deg, grid_size)
    goal = _coord_to_index(end_lat, end_lon, lat0, lon0, step_deg, grid_size)

    dist: dict[tuple[int, int], float] = {start: 0.0}
    prev: dict[tuple[int, int], tuple[int, int]] = {}
    pq: list[tuple[float, tuple[int, int]]] = [(0.0, start)]
    visited: set[tuple[int, int]] = set()

    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    while pq:
        cur_cost, node = heapq.heappop(pq)
        if node in visited:
            continue
        visited.add(node)

        if node == goal:
            break

        ni, nj = node
        lat_a, lon_a = _index_to_coord(ni, nj, lat0, lon0, step_deg)

        for di, dj in offsets:
            vi, vj = ni + di, nj + dj
            if vi < 0 or vj < 0 or vi >= grid_size or vj >= grid_size:
                continue

            lat_b, lon_b = _index_to_coord(vi, vj, lat0, lon0, step_deg)
            edge_len = haversine_km(lat_a, lon_a, lat_b, lon_b)
            risk = zone_risk_at(lat_b, lon_b, zones_geojson)
            weight = edge_len * RISK_COST.get(risk, 1.0)

            next_cost = cur_cost + weight
            neighbor = (vi, vj)
            if next_cost < dist.get(neighbor, float("inf")):
                dist[neighbor] = next_cost
                prev[neighbor] = node
                heapq.heappush(pq, (next_cost, neighbor))

    if goal not in dist:
        return {"path": [], "distance_km": None, "status": "no_path"}

    # Reconstruct route
    path_idx: list[tuple[int, int]] = []
    cur = goal
    while cur != start:
        path_idx.append(cur)
        cur = prev[cur]
    path_idx.append(start)
    path_idx.reverse()

    path_coords: list[dict[str, float]] = []
    geo_distance = 0.0
    for idx, (i, j) in enumerate(path_idx):
        lat, lon = _index_to_coord(i, j, lat0, lon0, step_deg)
        path_coords.append({"latitude": lat, "longitude": lon})
        if idx > 0:
            p = path_coords[idx - 1]
            geo_distance += haversine_km(p["latitude"], p["longitude"], lat, lon)

    return {
        "path": path_coords,
        "distance_km": round(geo_distance, 3),
        "status": "ok",
    }
