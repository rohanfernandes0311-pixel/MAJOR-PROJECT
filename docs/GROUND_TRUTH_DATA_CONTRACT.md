# LandSense Ground-Truth Data Contract

This contract is for future independently labelled observations. It is
separate from the current nine-feature model input contract and does not alter
the production dataset, models, API, or database.

## Record requirements

Every row must have a stable `observation_id`. Repeated measurements from one
landslide must share an `event_id`; a row that cannot be associated with an
event must use an explicit null value and an explanation in the data-quality
log, not a fabricated identifier.

| Field | Required | Type / unit | Meaning and acceptance rule |
|---|---|---|---|
| `observation_id` | Yes | string | Stable unique identifier assigned by the ingest system |
| `event_id` | Conditional | string or null | External landslide event identifier; never generated from the label |
| `observation_timestamp_utc` | Yes | ISO-8601 UTC | Time the sensor observation represents |
| `event_timestamp_utc` | Conditional | ISO-8601 UTC or null | Independently recorded occurrence/onset time |
| `latitude` | Yes | decimal degrees | WGS84 latitude, inclusive range [-90, 90] |
| `longitude` | Yes | decimal degrees | WGS84 longitude, inclusive range [-180, 180] |
| `region` | Recommended | controlled string | Administrative or geographic unit and its lookup source |
| `landslide_occurrence` | Yes | boolean / null | Independently assessed occurrence; null means unresolved |
| `risk_label` | Yes for supervised training | `Low`, `Medium`, `High`, or `unknown` | Label assigned from external evidence, not model features |
| `label_source` | Yes | controlled string | Inventory, field survey, adjudicated imagery, or other approved source |
| `label_source_reference` | Yes | string | Inventory record, report, imagery ID, or immutable citation |
| `label_confidence` | Yes | `[0, 1]` | Confidence assigned by the labelling protocol |
| `verification_status` | Yes | controlled string | `unverified`, `reviewed`, or `adjudicated` |
| `rainfall_mm` | Recommended | millimetres plus interval | Accumulation and `rainfall_interval_hours` must both be recorded |
| `rainfall_interval_hours` | Recommended | positive number | Interval for rainfall accumulation |
| `deformation_mm` | If available | millimetres plus convention | Sensor product, reference frame, sign convention, and interval required |
| `velocity_mm_yr` | If available | millimetres/year | Product definition, sign convention, and observation window required |
| `coherence` | If available | unitless `[0, 1]` | Sensor/product definition and acquisition pair required |
| `slope_deg` | If available | degrees | DEM source and resolution required |
| `elevation_m` | If available | metres | DEM/source and vertical datum required |
| `soil_moisture_pct` | If available | percent or source-native unit | Measurement/product source and depth required |
| `aspect_deg` | If available | degrees `[0, 360)` | DEM/source and convention required |
| `ndvi` | If available | unitless, normally `[-1, 1]` | Product, acquisition date, and cloud-quality status required |
| `record_provenance` | Yes | `real`, `synthetic`, `simulated`, `unverified` | `real` requires an external source reference; synthetic values cannot be used as ground truth |

The nine production features remain exactly:

`deformation_mm`, `velocity_mm_yr`, `coherence`, `rainfall_mm`, `slope_deg`,
`soil_moisture_pct`, `elevation_m`, `aspect_deg`, `ndvi`.

Metadata in this contract must remain outside model inputs until a separately
versioned model explicitly validates a change.

## Genuine negative observations

A negative observation is not “whatever was not labelled High.” It is valid only
when all of the following are documented:

1. The sensor or field observation covers a defined location and time window.
2. An approved landslide inventory, field survey, or adjudicated imagery review
   found no landslide occurrence in the stated observation window.
3. The search coverage, resolution, reviewer, and source reference are recorded.
4. The observation is not merely missing, cloud-obscured, outside the sensor
   footprint, or unresolved.
5. If multiple observations belong to one event or location, the event/time
   grouping is retained for leakage-safe splitting.

If these conditions are not met, use `unknown` or exclude the record from
supervised evaluation; do not convert uncertainty into a Low label.

## Labeling and split policy

- Preserve raw source records and immutable source references.
- Keep synthetic, simulated, unverified, and real/adjudicated records distinct.
- Require at least two independent reviewers for high-impact labels where
  feasible, with disagreements adjudicated and recorded.
- Split by `event_id` first. If no event ID exists, use a documented geographic
  and temporal grouping proxy and mark the limitation.
- Reserve a final event/time-based test set before model tuning.
- Fit imputers, scalers, feature selection, and resampling only inside training
  folds.
- Do not use the final test set for early stopping, threshold selection,
  calibration, or candidate selection.
- Report per-class support, false negatives, balanced accuracy, macro F1, and
  confusion matrices. Suppress or qualify High-risk claims when support is too
  small for stable estimates.

## Intake rejection conditions

Reject or quarantine records with missing provenance, invalid coordinates,
non-finite model features, impossible units, duplicate `observation_id`, or a
label that is derived from the nine model features rather than external
evidence. Quarantine is preferable to silently imputing a missing label.

