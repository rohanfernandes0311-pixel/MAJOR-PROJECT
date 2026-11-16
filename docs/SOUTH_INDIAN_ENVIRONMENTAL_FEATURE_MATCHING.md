# South Indian Environmental Feature Matching

Status: **PARTIALLY MATCHED — FEATURES OR DATES MISSING**

Research-only work performed on 2026-10-09. Production models, the
production dataset, inference preprocessing, thresholds, APIs, alerts,
geofencing, databases, and frontend behavior were not changed.

## Metadata-first decision

The acquired inventories contain valid spatial coordinates, but neither
contains a defensible per-record event date or event identifier:

- Kodagu points have `Name`, `X`, and `Y`; the source README describes the
  inventory as a 2018 storm-event inventory, but provides no per-record date.
- Kodagu polygons have `Name`, `area`, `X`, and `Y`; some `Name` values contain
  `2018`, but this is an inventory/source identifier, not a verified occurrence
  timestamp.
- Kerala has `No`, `District`, source flags, landslide attributes, and point
  coordinates. The source dataset describes the 2018 monsoon event at dataset
  level; there is no per-record occurrence date.

Therefore no rainfall, soil-moisture, NDVI, or other time-dependent value was
extracted. A dataset-level event year is not substituted for an observation
date.

## Spatial terrain extraction

Terrain was extracted for the independent Kodagu point inventory, Kodagu
polygon representative points, and Kerala point inventory. Polygon values use
the source `X`/`Y` representative-point attributes, not recomputed centroids.
This distinction is recorded in every output row.

Source:

- NASA SRTM v3, 1 arc-second HGT tiles, approximately 30 m
- Public AWS Open Data `elevation-tiles-prod`, `skadi` path
- Geographic CRS: WGS 84 (`EPSG:4326`)
- Elevation units: metres
- NoData value: `-32768`
- Elevation: nearest DEM cell
- Slope and aspect: centered 3x3 finite differences using neighboring cells
- Aspect convention: degrees clockwise from north, `[0, 360)`

Kodagu points were transformed from WGS 84 / UTM zone 43N (`EPSG:32643`) to
WGS 84 before extraction. Kodagu polygons were already geographic coordinates
with a vertical CRS component; their source representative coordinates were
used as geographic longitude/latitude. Kerala points were read from the
source WGS 84 shapefile.

Outputs:

| Output | Records | Terrain fields |
|---|---:|---|
| `data/research/south_india_environmental_features/kodagu_points_terrain.csv` | 267 | elevation, slope, aspect |
| `data/research/south_india_environmental_features/kodagu_polygons_terrain.csv` | 217 | elevation, slope, aspect |
| `data/research/south_india_environmental_features/kerala_points_terrain.csv` | 4,728 | elevation, slope, aspect |

Every row contains the original inventory name and source record identifier,
coordinates, coordinate method/CRS, empty event-date fields with provenance,
terrain source and units, extraction timestamp, extraction method, and a
measurement status. No synthetic labels or measurements were added.

All 267 Kodagu point rows and 217 Kodagu polygon rows have complete terrain
measurements. Kerala has complete terrain measurements for 4,712 rows; 16
rows retain missing slope/aspect values because the centered neighborhood
intersects unavailable DEM cells. Their status is `blocked`; they were not
imputed.

Tile URLs, tile checksums, output checksums, and extraction metadata are in
`data/research/south_india_environmental_features/terrain_manifest.json`.
The reproducible extractor is
`scripts/extract_south_india_terrain.py`.

## Feature coverage matrix

| LandSense feature | Status | Evidence and blocker |
|---|---|---|
| `deformation_mm` | `requires_scientific_review` | Sentinel-1 interferometric processing is required; raw GRD is not a deformation measurement |
| `velocity_mm_yr` | `requires_scientific_review` | Requires a documented InSAR time series, reference frame, sign convention, and observation interval |
| `coherence` | `requires_scientific_review` | Requires acquisition-pair processing and quality thresholds |
| `rainfall_mm` | `not_available_for_record` | No defensible per-record event dates |
| `slope_deg` | `extracted_and_validated` | SRTM v3 terrain extraction |
| `soil_moisture_pct` | `source_identified_not_downloaded` | SMAP or another product requires temporal matching and source-native unit handling |
| `elevation_m` | `extracted_and_validated` | SRTM v3 elevation in metres |
| `aspect_deg` | `extracted_and_validated` | SRTM v3-derived aspect; circular convention recorded |
| `ndvi` | `source_identified_not_downloaded` | Dated, quality-masked optical product requires temporal matching |

## Scientific limitations

These outputs are spatially matched research measurements, not a
model-training table. The inventories are presence-only event inventories and
do not establish genuine Low-risk or non-event observations. The 2018 event
description cannot be used to calculate record-level antecedent rainfall
windows. No records were merged based on proximity, duplicated for balance, or
labelled using LandSense's synthetic formula.

To continue safely, obtain authoritative event onset dates or date intervals
for each source record, then match rainfall using only measurements available
at or before the event. Acquire independent non-event observations with
documented spatial coverage and observation windows. InSAR, soil moisture,
NDVI, and rainfall processing should each retain product version, acquisition
time, spatial support, quality masks, units, and missing-data reasons.

Original source data remains under `data/external/` and is unchanged.
