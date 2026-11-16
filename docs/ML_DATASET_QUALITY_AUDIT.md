# LandSense ML Dataset Quality Audit

Audit date: 2026-10-09  
Dataset: `data/landslide_dataset.csv`  
Dataset SHA-256: `40bf746cf624a7d00e853d34b0cf46f1a99bb6dc49d94d13ef6f974c8ca68e7d`

## Preservation record

- Repository commit at audit start: `c7bad247991ceffe36e12ac8d1dfd60d31e0964c`
  (`c7bad24 feat: improve citizen high critical alert ux`)
- The worktree already contained unrelated modified and untracked files. They
  were preserved.
- Production artifact hashes at audit start:
  - `models/random_forest.pkl`: `33282F6C780ABFF0CED9C035A5BBC93B9F1D79A69A8513317252D203FF7ADC80`
  - `models/xgboost.pkl`: `5EF37A0F72924BE34BFC14F02BA09D9AC6F2BD878830F60205F2530D524400A5`
  - `models/scaler.pkl`: `8B4CA66B28A40DE701E30E697E40AD165C5ECC57734C8F0A28CC0EFADB6167A4`
  - `models/metrics.json`: `0422B7632BE82D6E8670A4CA0A9733710EC91B8B0E9BC9E8DC1929E3E94B6349`
- Production artifacts, APIs, thresholds, databases, alerts, routing, and
  frontend behavior were not changed.

## Dataset inventory

The file has 5,000 rows and these columns:

`region`, the nine model features, `day_of_year`, `latitude`, `longitude`,
`label`, and `risk_level`.

Class counts are:

| Numeric label | Name | Rows | Share |
|---:|---|---:|---:|
| 0 | Low | 4,927 | 98.54% |
| 1 | Medium | 70 | 1.40% |
| 2 | High | 3 | 0.06% |

There are 10 regions and 365 distinct `day_of_year` values. There is no
observation timestamp, event identifier, source reference, verification status,
or explicit synthetic/real provenance column.

## Provenance and label audit

`generate_dataset.py` uses a synthetic fallback when source CSVs are not
provided. Its fallback generates rainfall, soil moisture, deformation,
velocity, coherence, elevation, aspect, NDVI, region, coordinates, and
day-of-year values from random distributions.

The final label is computed from the same model features:

- deformation: weight `0.28`
- velocity: weight `0.18`
- rainfall: weight `0.18`
- slope: weight `0.14`
- soil moisture: weight `0.12`
- coherence: weight `-0.10`

The score is thresholded at `0.33` and `0.60` into Low, Medium, and High.
Recomputing this rule from the checked CSV reproduces every stored label:
**100% match**.

This is deterministic synthetic/rule-generated supervision, not independent
historical landslide ground truth. The current file must not be described as
verified landslide events or used to claim emergency-warning reliability.

The optional CSV ingestion path does not establish provenance by itself: it
selects columns by name, resizes values to the base row count, fills missing
feature values with medians, and still applies the same feature-derived label
rule. Future real-data ingestion must preserve source identifiers and external
labels instead of replacing them with this rule.

## Completeness, duplicates, and validity

- Missing values: 0 in every column.
- Non-finite numeric values: 0.
- Duplicate full rows: 0.
- Duplicate nine-feature rows: 0.
- Duplicate latitude/longitude pairs: 0.
- Invalid latitude/longitude bounds: 0.
- Multiple rows per exact coordinate: none were found.
- Event-level duplication cannot be assessed because no event ID exists.
- Temporal leakage cannot be assessed because `day_of_year` is not a date or
  ordered observation timestamp.
- Nearby-location or event leakage cannot be ruled out from exact-coordinate
  uniqueness alone. Region grouping is only a conservative proxy.

## Feature ranges

The names imply the following units, but the current CSV does not carry
measurement provenance or unit metadata:

| Feature | Min | Max | Mean | Audit finding |
|---|---:|---:|---:|---|
| `deformation_mm` | -23.1842 | 33.5830 | 4.2999 | Negative values require source review |
| `velocity_mm_yr` | -117.1559 | 219.3770 | 23.9052 | Negative values require source review |
| `coherence` | 0.1000 | 0.9900 | 0.8075 | Within nominal [0, 1] range |
| `rainfall_mm` | 0.0010 | 350.0000 | 30.1106 | Synthetic distribution; interval unspecified |
| `slope_deg` | 0.1419 | 52.7006 | 17.0042 | Plausible range, provenance absent |
| `soil_moisture_pct` | 6.4288 | 95.0000 | 32.3607 | Unit implied by name, source absent |
| `elevation_m` | 100.0000 | 2622.5451 | 1209.1236 | Plausible range, source absent |
| `aspect_deg` | 0.0170 | 359.9846 | 182.5930 | Circular feature, source absent |
| `ndvi` | -0.9224 | 0.9983 | 0.2057 | Within nominal [-1, 1] range |

Negative deformation and velocity may be meaningful signed line-of-sight
measurements in a real InSAR convention, but the current generator also permits
negative values through additive noise. They must not be corrected without
confirming the sensor convention and source metadata.

## Scientific conclusion

The current dataset is suitable for integration and pipeline testing only. It
does not support credible real-world class-wise model evaluation because:

1. labels are derived from the predictors;
2. only three rows are High;
3. no independent event/time/source provenance exists; and
4. feature units and observation intervals are not recorded.

No rows were fabricated, relabelled, clipped, or deleted during this audit.
The next safe step is collection and validation of independently labelled
observations under the contract in `GROUND_TRUTH_DATA_CONTRACT.md`.
