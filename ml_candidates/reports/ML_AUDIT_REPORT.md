# LandSense ML Audit and Candidate Validation

## Decision

**Retain the existing production models. Do not promote either candidate.**
The available data has only three rule-generated High labels, and the grouped
holdout is used for XGBoost early stopping rather than as an untouched final test.
Neither candidate has evidence of real-world warning reliability.

## Verified data findings

- Rows: 5000; class counts: `{'0': 4927, '1': 70, '2': 3}`.
- Features: `deformation_mm, velocity_mm_yr, coherence, rainfall_mm, slope_deg, soil_moisture_pct, elevation_m, aspect_deg, ndvi`.
- Dataset SHA-256: `40bf746cf624a7d00e853d34b0cf46f1a99bb6dc49d94d13ef6f974c8ca68e7d`.
- No event ID, timestamp, or independently labelled landslide inventory was present.
- Labels are generated from the same feature table by deterministic score thresholds; the rule reproduces the stored labels at 100%.
- No source column distinguishes synthetic from real observations in this file; the generator and label provenance identify it as synthetic/rule-generated evidence.
- Region and spatial grouping are proxies only; they cannot prove event independence.

## Validation findings

- Production baselines and candidates were evaluated on the same grouped holdout for comparability.
- Candidate preprocessing is fitted inside each training fold; validation data is transformed only after fitting.
- Grouped cross-validation uses `StratifiedGroupKFold(n_splits=3)` over the training portion.
- XGBoost early stopping uses a validation set and therefore requires a new untouched test set before deployment.
- Calibration and threshold claims are withheld because three High observations cannot support reliable estimates.
- Training metrics for every grouped-CV fold are stored alongside validation metrics in `candidate_metrics.json`.

## Results

| Model | Holdout accuracy | Holdout balanced accuracy | Holdout macro F1 | High recall | High false negatives |
|---|---:|---:|---:|---:|---:|
| production_random_forest_baseline | 0.9940 | 0.5751 | 0.5751 | 0.0000 | 1 |
| production_xgboost_baseline | 0.9960 | 0.5758 | 0.5995 | 0.0000 | 1 |
| candidate_random_forest | 0.9900 | 0.9966 | 0.8941 | 1.0000 | 0 |
| candidate_xgboost | 0.9970 | 0.6061 | 0.6187 | 0.0000 | 1 |

Full per-class metrics, fold variability, supports, and confusion matrices are in `candidate_metrics.json`.

## Tests executed

- Focused ML regression tests: 7 passed.
- Existing citizen/environment regression tests: 30 passed.
- Python syntax and diagnostics: no errors in modified Python files.
- Production model hashes were unchanged after candidate training.

## Limitations and next steps

Obtain an independently labelled landslide inventory with event IDs, observation dates,
and location provenance. Reserve events and time periods for a final test set, then
re-run candidate selection without using that test set for early stopping or tuning.
Until then, the models are suitable only for pipeline/integration testing, not emergency warnings.
