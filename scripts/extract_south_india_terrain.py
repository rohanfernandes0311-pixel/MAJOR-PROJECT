"""Extract spatial terrain features from cached SRTM HGT tiles.

This script deliberately extracts only spatial features. The acquired
inventories do not provide defensible per-record event dates, so rainfall and
other time-dependent products are not inferred here.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import struct
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import pyproj
import shapefile
from shapely.geometry import shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "research" / "south_india_environmental_features"
TILES = OUTPUT / "sources" / "srtm_v3"
NROWS = 3601
NCOLS = 3601
CELL_DEGREES = 1 / 3600
FEATURES = ("elevation_m", "slope_deg", "aspect_deg")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def tile_name(latitude: float, longitude: float) -> str:
    lat = math.floor(latitude)
    lon = math.floor(longitude)
    return f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}"


@lru_cache(maxsize=None)
def load_tile(name: str) -> tuple[tuple[int, ...], ...]:
    path = TILES / f"{name}.hgt.gz"
    if not path.exists():
        raise FileNotFoundError(f"Missing cached SRTM tile: {path}")
    with gzip.open(path, "rb") as handle:
        values = struct.unpack(f">{NROWS * NCOLS}h", handle.read())
    return tuple(
        tuple(values[row * NCOLS : (row + 1) * NCOLS]) for row in range(NROWS)
    )


def value(tile: list[list[int]], row: int, col: int) -> float | None:
    raw = tile[row][col]
    return None if raw == -32768 else float(raw)


def terrain(latitude: float, longitude: float) -> tuple[float | None, float | None, float | None]:
    name = tile_name(latitude, longitude)
    tile = load_tile(name)
    south = math.floor(latitude)
    west = math.floor(longitude)
    row = min(NROWS - 1, max(0, round((south + 1 - latitude) / CELL_DEGREES)))
    col = min(NCOLS - 1, max(0, round((longitude - west) / CELL_DEGREES)))
    elevation = value(tile, row, col)
    if elevation is None or row in (0, NROWS - 1) or col in (0, NCOLS - 1):
        return elevation, None, None
    north = value(tile, row - 1, col)
    south_value = value(tile, row + 1, col)
    east = value(tile, row, col + 1)
    west_value = value(tile, row, col - 1)
    if None in (north, south_value, east, west_value):
        return elevation, None, None
    metres_per_degree_lat = 111_320.0
    metres_per_degree_lon = metres_per_degree_lat * math.cos(math.radians(latitude))
    dz_d_north = (north - south_value) / (2 * CELL_DEGREES * metres_per_degree_lat)
    dz_d_east = (east - west_value) / (2 * CELL_DEGREES * metres_per_degree_lon)
    slope = math.degrees(math.atan(math.hypot(dz_d_north, dz_d_east)))
    aspect = (math.degrees(math.atan2(dz_d_east, dz_d_north)) + 360) % 360
    return elevation, slope, aspect


def records_for_inventory(name: str) -> Iterable[dict[str, object]]:
    if name == "kodagu_points":
        path = ROOT / "data" / "external" / "kodagu_2018" / "raw" / "Landslide_Points.shp"
        reader = shapefile.Reader(str(path))
        source_crs = "EPSG:32643"
        to_wgs84 = pyproj.Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True).transform
        for index, (record, geometry) in enumerate(zip(reader.records(), reader.shapes()), 1):
            point = transform(to_wgs84, shape(geometry.__geo_interface__))
            yield {
                "inventory": "kodagu_2018_points",
                "source_record_id": str(record[0]),
                "source_geometry_method": "shapefile point transformed from EPSG:32643",
                "latitude": point.y,
                "longitude": point.x,
                "event_date": "",
                "event_date_provenance": "not available in source attributes",
                "record_index": index,
            }
    elif name == "kodagu_polygons":
        path = ROOT / "data" / "external" / "kodagu_2018" / "raw" / "Landslide_polygons.shp"
        reader = shapefile.Reader(str(path))
        for index, record in enumerate(reader.records(), 1):
            yield {
                "inventory": "kodagu_2018_polygons",
                "source_record_id": str(record[0] or f"record-{index}"),
                "source_geometry_method": "source X/Y representative point attributes; not recomputed centroid",
                "latitude": float(record[3]),
                "longitude": float(record[2]),
                "event_date": "",
                "event_date_provenance": "not available in source attributes",
                "record_index": index,
            }
    elif name == "kerala_points":
        path = ROOT / "data" / "external" / "kerala_2018" / "raw" / "archive_contents" / "Kerela landslide.shp"
        reader = shapefile.Reader(str(path))
        for index, record in enumerate(reader.records(), 1):
            yield {
                "inventory": "kerala_2018_points",
                "source_record_id": str(record[0]),
                "source_geometry_method": "shapefile POINTZ in EPSG:4326",
                "latitude": float(record[17]),
                "longitude": float(record[16]),
                "event_date": "",
                "event_date_provenance": "2018 event described at dataset level; no per-record date",
                "record_index": index,
            }
    else:
        raise ValueError(f"Unknown inventory: {name}")


def extract_inventory(name: str) -> list[dict[str, object]]:
    rows = []
    for row in records_for_inventory(name):
        elevation, slope, aspect = terrain(float(row["latitude"]), float(row["longitude"]))
        terrain_status = (
            "extracted_and_validated"
            if all(value is not None for value in (elevation, slope, aspect))
            else "blocked"
        )
        row.update(
            elevation_m=elevation,
            slope_deg=slope,
            aspect_deg=aspect,
            terrain_source="NASA SRTM v3 1 arc-second HGT tiles from AWS Open Data terrain-tiles",
            terrain_source_resolution="1 arc-second (~30 m)",
            terrain_source_crs="EPSG:4326",
            extraction_method="nearest DEM cell; slope/aspect from centered 3x3 finite differences",
            extraction_timestamp_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            measurement_status=terrain_status,
        )
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    inventories = ("kodagu_points", "kodagu_polygons", "kerala_points")
    outputs = {}
    for inventory in inventories:
        rows = extract_inventory(inventory)
        path = OUTPUT / f"{inventory}_terrain.csv"
        write_csv(path, rows)
        outputs[inventory] = {
            "path": path.relative_to(ROOT).as_posix(),
            "records": len(rows),
            "complete_terrain_records": sum(
                all(row[key] not in ("", None) for key in FEATURES) for row in rows
            ),
            "sha256": sha256(path),
        }
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "purpose": "Spatial terrain matching only; no time-dependent features or labels generated.",
        "dem": {
            "product": "NASA SRTM v3 1 arc-second HGT tiles",
            "distribution": "AWS Open Data terrain-tiles, skadi path",
            "url_template": "https://s3.amazonaws.com/elevation-tiles-prod/skadi/{lat_band}/{tile}.hgt.gz",
            "resolution": "1 arc-second (~30 m)",
            "vertical_units": "metres",
            "nodata": -32768,
            "tile_checksums": {
                path.name: sha256(path) for path in sorted(TILES.glob("*.hgt.gz"))
            },
        },
        "outputs": outputs,
        "unavailable_features": {
            "rainfall_mm": "not_available_for_record: no defensible per-record event date",
            "soil_moisture_pct": "source_identified_not_downloaded: temporal matching blocked",
            "ndvi": "source_identified_not_downloaded: temporal matching blocked",
            "deformation_mm": "requires_scientific_review: Sentinel-1 processing not performed",
            "velocity_mm_yr": "requires_scientific_review: Sentinel-1 processing not performed",
            "coherence": "requires_scientific_review: acquisition-pair processing not performed",
        },
    }
    (OUTPUT / "terrain_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
