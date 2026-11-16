# South Indian Landslide Data Acquisition Report

Status: **BOTH DATASETS ACQUIRED AND VALIDATED**

Research-only acquisition performed on 2026-10-09. No production dataset,
model artifact, scaler, inference code, API contract, threshold, database,
alerting workflow, geofencing behavior, or frontend behavior was changed.

## Sources and provenance

### Kodagu, Karnataka (2018 storm event)

- Official source: [GitHub repository](https://github.com/Arpithaachaiah6/Landslide-inventory-for-the-2018-storm-event-of-Kodagu-in-the-Western-Ghats)
- Source commit: `9a49788babe1aa92e3d0919ae41fcc34044fff91`
- License file: CC BY-SA 4.0
- README describes a field-verified and image-interpreted inventory of 267
  landslides, including 89 field-investigated and 178 image-interpreted
  records. This description is source metadata, not an independently
  reverified claim about completeness.
- Downloaded raw components are preserved under
  `data/external/kodagu_2018/raw/`, including the point and polygon
  shapefile sidecars, README, and license.

Validated record counts:

| Dataset | Records | Geometry | Fields | CRS/bounds |
|---|---:|---|---|---|
| Kodagu points | 267 | POINTZ | `Name`, `X`, `Y` | WGS 84 / UTM 43N; 545770.785, 1371518.001 to 590458.391, 1403005.542 |
| Kodagu polygons | 217 | POLYGONZ | `Name`, `area`, `X`, `Y` | WGS 84 geographic with EGM96 vertical component; 75.461678, 12.385906 to 75.832724, 12.690308 |

The point and polygon files are not one-to-one: 217 polygons accompany 267
points. After converting the points to WGS 84 geographic coordinates, 60
points were covered by a polygon. This relationship is retained as an
observation, not used to discard or merge records.

Six polygon geometries are invalid according to Shapely. They remain
unchanged in the raw data and are marked `geometry_valid: false` in the
normalized copy. No automated repair was applied.

### Kerala (2018 monsoon rainfall event)

- Official source: [DANS DOI landing page](https://doi.org/10.17026/DANS-X6C-Y7X2)
- Dataset publisher metadata identifies C.J. van Westen, version 2.0, and
  reports 4,728 mapped landslides.
- License shown on the landing page: CC BY 4.0.
- The official Dataverse dataset API archive was downloaded to
  `data/external/kerala_2018/raw/kerala_2018_original.zip` and was not
  modified. Its contents were extracted for inspection under
  `data/external/kerala_2018/raw/archive_contents/`.

Validated record count is 4,728 POINTZ records. The shapefile fields are:
`No`, `District`, `NRSC`, `GSI`, `New`, `Type_of_sl`, `Length`, `Width`,
`Area`, `Building_I`, `Road_impac`, `Impact_Agr`, `LU_2010`, `LU_2018`,
`Specific_r`, `Remarks`, `POINT_X`, `POINT_Y`, `Reclass_Sl`, and
`RASTERVALU`. The CRS is WGS 84 geographic, with bounds 75.015414,
8.474453 to 77.396262, 12.654953.

Optional fields are incomplete: `Specific_r` is missing for 3,864 records and
`Remarks` for 3,698 records. The remaining listed fields have no empty values
in the DBF inspection. The archive also contains the source metadata XML,
manifest, PDF metadata, and shapefile sidecars. The source spells the
filename `Kerela landslide`; that spelling is preserved.

## Normalized research copies

The following GeoJSON files are derived copies, not replacements for raw data:

- `data/external/kodagu_2018/processed/kodagu_points.geojson`
- `data/external/kodagu_2018/processed/kodagu_polygons.geojson`
- `data/external/kerala_2018/processed/kerala_points.geojson`

Each feature retains the original attributes and includes `source_dataset`,
`source_file`, `source_record_id`, `local_id`, `source_crs`, and
`geometry_valid`. The Kodagu points were transformed from UTM zone 43N to
WGS 84 for spatial comparison only. The raw CRS and coordinates remain
unchanged.

There were no exact coordinate matches between the normalized Kodagu and
Kerala point inventories. The closest cross-source point distance was
approximately 7.657 km. This is not evidence that records are duplicates:
the inventories describe different events and require source/event context
before any future merge.

No records were merged, relabelled, deduplicated, or converted into negative
observations. These are event inventories and do not establish verified
non-landslide observations.

## Feature compatibility for LandSense

| Existing feature | Present in inventories | Required future matching |
|---|---|---|
| `deformation_mm` | No | Independently processed InSAR time series, event-relative window, sensor and processing provenance |
| `velocity_mm_yr` | No | Independently processed InSAR velocity product and observation interval |
| `coherence` | No | Sentinel-1 acquisition-pair metadata and validated extraction |
| `rainfall_mm` | No | IMD, IMERG, or CHIRPS rainfall matched to coordinates and pre-event windows |
| `slope_deg` | No | Versioned DEM-derived slope at a documented resolution |
| `soil_moisture_pct` | No | SMAP or equivalent product matched to event date and spatial support |
| `elevation_m` | No | Versioned DEM and extraction method |
| `aspect_deg` | No | Same DEM/version and circular-angle handling |
| `ndvi` | No | Dated satellite product and cloud/quality-mask rules |

The existing nine-feature inference contract must remain unchanged. Neither
inventory is ready to train that model because the required covariates are
absent and the event inventories do not supply verified negative examples.

## Limitations and next steps

The inventories provide landslide presence records, not a balanced supervised
classification dataset. A future experiment needs independently documented
non-event observations, a defensible event or spatial split, and environmental
measurements matched without using post-event information improperly. Event
dates are not sufficiently represented in the inspected shapefile attributes
to claim precise temporal matching for every record. Licensing attribution must
be retained in any redistribution or publication.

The machine-readable file manifest, retrieval metadata, byte sizes, and
SHA-256 checksums are in
`data/external/source_manifest.json`. Production artifact hashes were checked
before acquisition and remain unchanged.
