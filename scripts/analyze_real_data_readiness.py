"""Summarize research-data readiness without fitting a classifier."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from statistics import mean, median


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "research" / "south_india_environmental_features"
OUTPUT = BASE / "real_data_readiness_summary.json"
TERRAIN_FIELDS = ("elevation_m", "slope_deg", "aspect_deg")
MODEL_FEATURES = (
    "deformation_mm",
    "velocity_mm_yr",
    "coherence",
    "rainfall_mm",
    "slope_deg",
    "soil_moisture_pct",
    "elevation_m",
    "aspect_deg",
    "ndvi",
)


def number(value: str) -> float | None:
    if value in ("", "None", "null"):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def summarize(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    source_ids = [row["source_record_id"] for row in rows]
    coordinates = [
        (float(row["longitude"]), float(row["latitude"]))
        for row in rows
        if row["longitude"] and row["latitude"]
    ]
    fields: dict[str, object] = {}
    for field in MODEL_FEATURES + ("event_date",):
        if field not in rows[0]:
            fields[field] = {
                "missing": len(rows),
                "observed": 0,
                "available_column": False,
            }
            continue
        values = [number(row[field]) for row in rows] if field != "event_date" else [
            row[field] for row in rows
        ]
        if field == "event_date":
            missing = sum(value == "" for value in values)
            fields[field] = {"missing": missing, "observed": len(values) - missing}
            continue
        numeric = [value for value in values if value is not None]
        fields[field] = {
            "available_column": True,
            "missing": len(rows) - len(numeric),
            "observed": len(numeric),
            "min": min(numeric) if numeric else None,
            "max": max(numeric) if numeric else None,
            "mean": mean(numeric) if numeric else None,
            "median": median(numeric) if numeric else None,
        }
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "records": len(rows),
        "unique_source_record_ids": len(set(source_ids)),
        "duplicate_source_record_ids": len(source_ids) - len(set(source_ids)),
        "coordinate_count": len(coordinates),
        "coordinate_bounds": {
            "longitude_min": min(point[0] for point in coordinates),
            "longitude_max": max(point[0] for point in coordinates),
            "latitude_min": min(point[1] for point in coordinates),
            "latitude_max": max(point[1] for point in coordinates),
        },
        "measurement_status_counts": {
            status: sum(row["measurement_status"] == status for row in rows)
            for status in sorted({row["measurement_status"] for row in rows})
        },
        "fields": fields,
    }


def main() -> None:
    terrain_manifest = json.loads(
        (BASE / "terrain_manifest.json").read_text(encoding="utf-8")
    )
    date_registry = json.loads(
        (BASE / "event_date_registry.json").read_text(encoding="utf-8")
    )
    inventories = [
        summarize(BASE / "kodagu_points_terrain.csv"),
        summarize(BASE / "kodagu_polygons_terrain.csv"),
        summarize(BASE / "kerala_points_terrain.csv"),
    ]
    total_records = sum(int(item["records"]) for item in inventories)
    summary = {
        "analysis": {
            "name": "LandSense real-data evaluation readiness",
            "purpose": "Exploratory provenance and coverage analysis only",
            "classifier_trained": False,
            "production_models_used": False,
            "records_analyzed": total_records,
            "decision": "BLOCKED BY LABEL OR DATA LIMITATIONS",
        },
        "inventories": inventories,
        "source_relationships": {
            "kodagu_points_and_polygons_are_independent_events": False,
            "reason": "The source does not provide a one-to-one point/polygon event crosswalk; retain both separately.",
            "cross_inventory_merge_performed": False,
            "deduplication_performed": False,
        },
        "provenance": {
            "terrain_manifest": terrain_manifest,
            "event_date_registry": date_registry,
        },
        "feature_coverage": {
            field: {
                "status": (
                    "extracted_and_validated"
                    if field in TERRAIN_FIELDS
                    else "unavailable_or_not_temporally_matchable"
                ),
                "observed_in_research_outputs": field in TERRAIN_FIELDS,
                "valid_supervised_input": False,
                "reason": (
                    "Spatial SRTM-derived terrain measurement with method and source metadata."
                    if field in TERRAIN_FIELDS
                    else "No defensible record-level event date or source measurement was available."
                ),
            }
            for field in MODEL_FEATURES
        },
        "label_readiness": {
            "confirmed_landslide_records": total_records,
            "verified_non_event_records": 0,
            "unknown_or_unobserved_locations": "Not represented by these event inventories",
            "supervised_learning_justified": False,
            "reason": "Event inventories establish recorded presence only and do not provide verified Low-risk observations or independent labels.",
        },
        "validation_requirements": [
            "Acquire independently verified non-event observations with defined spatial and temporal coverage.",
            "Obtain event IDs and dates or bounded intervals before temporal feature extraction.",
            "Split by event, geography, and time where those identifiers exist.",
            "Keep Kodagu points and polygons separate unless a source crosswalk verifies their relationship.",
            "Fit all preprocessing inside training folds and reserve an untouched final evaluation set.",
        ],
    }
    OUTPUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
