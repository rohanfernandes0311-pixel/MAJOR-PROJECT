# Real-Data Evaluation Readiness

Decision: **BLOCKED BY LABEL OR DATA LIMITATIONS**

Analysis date: 2026-10-09. This is a research-only exploratory analysis.
Production datasets, models, preprocessing, thresholds, APIs, alerts,
geofencing, databases, and frontend behavior were not changed. No classifier
was trained.

## Scope and provenance

The analysis loads the acquired, provenance-preserving terrain outputs:

- Kodagu point inventory: 267 records
- Kodagu polygon inventory: 217 records
- Kerala point inventory: 4,728 records
- Total source rows analyzed: 5,212

The reproducible script is
[`scripts/analyze_real_data_readiness.py`](../scripts/analyze_real_data_readiness.py).
Its machine-readable output is
[`data/research/south_india_environmental_features/real_data_readiness_summary.json`](../data/research/south_india_environmental_features/real_data_readiness_summary.json).

Every analyzed row retains an inventory name and source record identifier.
Source terrain metadata and extraction status are retained. Output files were
not merged or silently deduplicated.

The source identifiers are not unique in every inventory: the 267 Kodagu point
rows contain 178 unique `Name` values (89 repeated identifier occurrences),
and the 4,728 Kerala point rows contain 2,501 unique `No` values (2,227
repeated identifier occurrences). The 217 Kodagu polygon identifiers are
unique. These repetitions are reported, not removed; future ingestion needs a
stable source crosswalk or a composite identifier that preserves the original
row identity.

## Coverage and missingness

All 267 Kodagu point records and all 217 Kodagu polygon records have
elevation, slope, and aspect measurements. Kerala has those measurements for
4,712 of 4,728 point records; 16 rows retain blocked slope/aspect values
because the centered SRTM neighborhood intersects unavailable DEM cells.
Those values remain missing.

The nine-feature LandSense coverage is:

| Feature | Research status | Interpretation |
|---|---|---|
| `elevation_m` | Extracted for all complete terrain rows | SRTM v3 spatial measurement |
| `slope_deg` | Extracted except 16 Kerala rows | SRTM-derived spatial measurement |
| `aspect_deg` | Extracted except 16 Kerala rows | SRTM-derived circular spatial measurement |
| `rainfall_mm` | Unavailable | No defensible record-level event date |
| `deformation_mm` | Unavailable | No processed InSAR product |
| `velocity_mm_yr` | Unavailable | No processed InSAR time series |
| `coherence` | Unavailable | No acquisition-pair processing |
| `soil_moisture_pct` | Unavailable | No time-matched source measurement |
| `ndvi` | Unavailable | No dated, quality-masked optical extraction |

The detailed field-level ranges, coordinate bounds, missingness, status counts,
and source checksums are in the JSON summary.

## Geometry and source relationships

The source-specific acquisition validation found valid coordinates and no
duplicate geometries in the original point/polygon checks. Identifier
repetition is a separate issue from geometric duplication. Six Kodagu polygon
geometries were invalid and remain flagged in the normalized source copy.
Kodagu points and polygons are not treated as independent landslide events:
the source does not provide a one-to-one crosswalk, and the prior validation
found only 60 point/polygon coverage relationships. No relationship-based
deduplication was performed.

The Kerala inventory is a point event inventory with source attributes and
documented missingness in optional fields. It does not contain verified
non-event locations.

## Why supervised learning is not justified

These inventories record mapped landslide presence. They do not establish
that locations absent from the files were observed and found safe. Therefore
there are **zero verified non-event examples** in this research dataset.
Assigning Low labels to unlisted locations, or applying LandSense's synthetic
feature-derived formula, would create unsupported labels and leakage.

Terrain distributions at recorded landslide locations can support descriptive
exploration, quality control, and hypothesis generation. They are not
predictive accuracy, susceptibility validation, or evidence that terrain
caused the observed events. The source inventories also have event-level
reporting and geographic coverage biases.

## Evaluation design required later

Before supervised evaluation:

1. Obtain independently verified non-event observations with defined search
   coverage, observation window, reviewer/source reference, and coordinates.
2. Obtain stable event IDs and occurrence dates or defensible intervals.
3. Match rainfall, soil moisture, NDVI, and InSAR products only to dates
   available at or before each event.
4. Keep the Kodagu point and polygon sources separate unless a source-backed
   event crosswalk is obtained.
5. Split by event first, then geography and time where appropriate. Reserve an
   untouched final test set before tuning or calibration.
6. Fit imputation, scaling, selection, and resampling inside training folds.

## Validation performed

- The analysis script was executed successfully and generated the JSON summary.
- Provenance, row-count, coordinate, and missingness assertions passed.
- The event-date registry validation passed.
- Python syntax validation passed for the new script.
- `git diff --check` passed, with existing Windows line-ending warnings only.
- No model training or production inference was run.

Production hashes remain unchanged:

| Artifact | SHA-256 |
|---|---|
| `data/landslide_dataset.csv` | `40BF746CF624A7D00E853D34B0CF46F1A99BB6DC49D94D13EF6F974C8CA68E7D` |
| `models/random_forest.pkl` | `33282F6C780ABFF0CED9C035A5BBC93B9F1D79A69A8513317252D203FF7ADC80` |
| `models/xgboost.pkl` | `5EF37A0F72924BE34BFC14F02BA09D9AC6F2BD878830F60205F2530D524400A5` |
| `models/scaler.pkl` | `8B4CA66B28A40DE701E30E697E40AD165C5ECC57734C8F0A28CC0EFADB6167A4` |
| `models/metrics.json` | `0422B7632BE82D6E8670A4CA0A9733710EC91B8B0E9BC9E8DC1929E3E94B6349` |
