# LandSense Real Landslide Data Source Discovery

Research date: 2026-10-09  
Scope: discovery and integration planning; subsequent acquisition is documented
in [SOUTH_INDIAN_DATA_ACQUISITION_REPORT.md](./SOUTH_INDIAN_DATA_ACQUISITION_REPORT.md)

The later South Indian acquisition pass downloaded the Kodagu and Kerala
research inventories into `data/external/`. No production dataset, model,
scaler, inference API, threshold, database, alert, geofencing, or frontend
behavior was changed.

## Current project context

The current dataset is [landslide_dataset.csv](../data/landslide_dataset.csv),
with SHA-256
`40BF746CF624A7D00E853D34B0CF46F1A99BB6DC49D94D13EF6F974C8CA68E7D`.
It contains 5,000 synthetic/rule-generated records and only three High labels.
The production model inputs remain the nine features documented in
[ML_DATASET_QUALITY_AUDIT.md](./ML_DATASET_QUALITY_AUDIT.md).

The current loaders and paths are:

- [generate_dataset.py](../generate_dataset.py): optional CSV ingestion plus
  synthetic fallback; writes the current dataset.
- [train_models.py](../train_models.py): reads the current dataset and trains
  the models.
- [predict.py](../predict.py): loads `models/random_forest.pkl` and
  `models/xgboost.pkl` and constructs the unchanged nine-feature vector.
- [app.py](../app.py) and [backend_api.py](../backend_api.py): consume the
  existing prediction workflow.

## Evidence status terminology

- **Landing page tested** means the official URL opened and its metadata or
  description was read.
- **Metadata endpoint tested** means an official machine-readable endpoint
  responded.
- **File downloaded** is claimed only where a file was actually downloaded and
  checksum-recorded. The acquisition report and
  `data/external/source_manifest.json` contain the later file-level evidence.
- A source being open or discoverable does not imply that redistribution,
  bulk access, or commercial use is permitted.

## Priority event inventories

| Source | Publisher and official URL | Coverage and relevance | Records and metadata | Negative observations | Access, license, and recommendation |
|---|---|---|---|---|---|
| **Landslide Atlas of India** | NRSC/ISRO: [official Atlas page](https://www.isro.gov.in/ISRO_EN/Landslide_Atlas_India.html); [NRSC/Bhuvan disaster portal](https://bhuvan-app1.nrsc.gov.in/disaster/disaster.php?id=landslide) | India-wide; published descriptions report roughly 80,000 mapped landslides for 1998–2022 across 17 states and 2 Union Territories, including Western Ghats regions. | Seasonal, event-based, and route-wise inventory views are described. Exact downloadable field names, stable event IDs, geometry format, and date precision were not verified. | No documented true-negative layer. Absence from a mapped inventory is not a verified negative. | Official landing pages tested. No shapefile/GeoJSON download was successfully tested. Confirm current schema, CRS, stable IDs, terms, and attribution with NRSC/Bhuvan before use. **Priority 1 official India source.** |
| **GSI landslide information/inventory** | Geological Survey of India: [Landslide Hazard](https://gsi.gov.in/landslide-hazard/) | National geological authority; potentially relevant to Western Ghats, Karnataka, Kerala, and ongoing incident records. | Public metadata exposed during this pass was insufficient to verify exact fields, format, event IDs, date coverage, or update frequency. | No documented true-negative layer. | Official page tested, but no inventory file/API was downloaded. Request the authoritative release and reuse terms from GSI. **Priority 2 official source.** |
| **Landslide inventory of the 2018 monsoon rainfall in Kerala, India** | Hao et al.; [University of Twente dataset page](https://research.utwente.nl/en/datasets/landslide-inventory-of-the-2018-monsoon-rainfall-in-kerala-india/); [ESSD paper](https://essd.copernicus.org/articles/12/2899/2020/); [DOI](https://doi.org/10.17026/dans-x6c-y7x2) | Kerala, including the Wayanad region; the 2018 extreme monsoon event. It is not evidence for Kodagu coverage. | 4,728 mapped landslides. The landing page lists district, data source, landslide type, landslide area, land use in 2010/2018, and related attributes; the acquired shapefile and metadata are inspected in the acquisition report. | Event inventory only; it does not provide verified non-event/background observations. | Landing page and official Dataverse archive tested; archive and checksums are recorded in `data/external/source_manifest.json`. Reported CC BY 4.0; cite Hao et al. (2020), ESSD, and the dataset DOI. **Priority 1 seed dataset for Kerala/Wayanad.** |
| **NASA Global Landslide Catalog (GLC)** | NASA GSFC: [NASA Open Data export](https://data.nasa.gov/dataset/global-landslide-catalog-export) | Global event-reporting catalog; the public export is a one-time export current to 2016-03-07, so it is not a current complete catalog. | Reported events from media, reports, scientific sources, and other records; records use a GLC ID tag and generally include event location/date/source metadata. Exact current schema was not retrieved here. | No true negatives. Unreported areas cannot be interpreted as safe. | NASA page tested; linked live ArcGIS service was not fetched in this environment and no file was downloaded. Follow NASA terms and cite Kirschbaum et al. **Priority 3 supplementary event source, not a complete reference inventory.** |
| **USGS Landslide Inventories across the United States, v3.0** | USGS: [official data page](https://www.usgs.gov/data/landslide-inventories-across-united-states-ver-30-february-2025) | United States, not India. Useful for pipeline benchmarking and transfer experiments, not for India labels. | Versioned inventory with USGS-defined fields; exact schema/license should be recorded from the download page before use. | Inventory presence does not establish verified negatives outside mapped events. | Official page is the authoritative access route; not accessed/downloaded in this pass. Use only with explicit geography separation. |

## Supporting environmental products

These products provide covariates aligned to event dates and locations. They
must never be used as replacement labels.

| Product | Official URL | Relevant fields/use | Coverage/update | Access tested and constraints |
|---|---|---|---|---|
| **NASA LHASA exposure/hazard service** | [NASA Earthdata MapServer](https://gis.earthdata.nasa.gov/portal/rest/services/Landslides/LHASA_Exposure/MapServer) | Near-real-time hazard/exposure assessment combining GPM rainfall and SMAP antecedent soil moisture; service supports JSON, GeoJSON, and PBF queries and EPSG:4326. | Global, daily hazard/exposure assessment. It is a model output, not an event inventory and has no event IDs or verified negatives. | REST metadata endpoint tested successfully. NASA GSFC copyright is exposed. Use as a deployment covariate or descriptive comparison only. |
| **Copernicus Sentinel-1 GRD** | [Google Earth Engine catalog](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD); [Copernicus Data Space access](https://dataspace.copernicus.eu/) | VV/VH or HH/HV SAR, incidence angle, acquisition/product IDs, orbit metadata; derive deformation/change features only with a documented processing pipeline. | Global mission-era coverage; GEE collection updated daily and new assets normally ingested within two days. Resolutions 10/25/40 m. | Official catalog metadata tested. No scene downloaded. GEE/Data Space account, processing choices, orbit, acquisition pair, and attribution must be recorded. |
| **NASA GPM IMERG V07** | [GEE catalog](https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07); [NASA IMERG documentation](https://gpm.nasa.gov/data/imerg) | Time-stamped precipitation estimates; extract 1/3/7/15/30-day accumulations before an event. | Global GPM/TRMM-era precipitation; three-hourly products are available. Provisional products can be replaced; record product status/version and access date. | Official catalog metadata tested. No raster export performed. Cite NASA GPM/IMERG and preserve the exact collection/version. |
| **CHIRPS Daily** | [Climate Hazards Center / GEE catalog](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY) | Daily land precipitation, useful as an independent rainfall covariate or comparison with IMERG. | Approximately 1981 to near-present, about 0.05-degree daily grid. | Catalog metadata tested. No export performed. Cite Funk et al. (2015), DOI 10.1038/sdata.2015.66, and CHC/UCSB terms. |
| **SRTMGL1 elevation** | [NASA/USGS GEE catalog](https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003); [Farr et al. DOI](https://doi.org/10.1029/2005RG000183) | Elevation from which slope, aspect, curvature, relief, and drainage derivatives can be computed. | Near-global coverage between approximately 60N and 56S; acquisition in February 2000; approximately 30 m. | Catalog metadata tested. No export performed. Record DEM version, CRS, vertical datum, resolution, and derivative method. |
| **IMD gridded rainfall** | [IMD Pune 0.25-degree rainfall page](https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html); [Mausam](https://mausam.imd.gov.in) | India-focused daily rainfall grid, potentially valuable for monsoon/event calibration. | Portal descriptions indicate 0.25-degree daily rainfall from 1901 to present; exact current product/version requires confirmation. | Direct page access encountered transport/DNS/TLS failure in this environment. No download attempted or claimed. Confirm access, terms, format, version, and attribution with IMD before planning a pipeline. |

## What is and is not currently verified

Verified in this pass:

- Official landing/metadata pages for the Kerala inventory, ISRO Atlas page,
  GSI page, NASA LHASA service, Sentinel-1 catalog, IMERG catalog, SRTM
  catalog, and CHIRPS catalog were reachable or their status was observed.
- The Kerala landing page explicitly states 4,728 landslides and lists the main
  attributes.
- LHASA metadata identifies a global daily service, GPM/SMAP inputs, EPSG:4326,
  JSON/GeoJSON/PBF query support, and NASA GSFC copyright.
- Sentinel-1 catalog metadata identifies daily updates, product IDs/acquisition
  metadata, polarization options, and 10/25/40 m resolutions.
- IMERG catalog metadata identifies three-hourly GPM precipitation estimates
  and provisional/permanent status behavior.

Not verified:

- Successful download of any external event inventory or raster.
- A stable NRSC/ISRO or GSI downloadable schema, event ID policy, or reuse
  license.
- Current GSI/NRSC update frequency or complete Kodagu coverage.
- Direct IMD download access from this environment.
- Any genuine negative observation set.
- That the Kerala inventory contains every field or event date needed for the
  LandSense contract; inspect the actual shapefile metadata after an approved
  download.

## Recommended acquisition and integration sequence

### Stage 1: Kerala/Wayanad seed

1. Obtain the Hao et al. dataset from the DOI repository.
2. Record download time, URL/DOI, checksum, CRS, file format, license, and
   complete source schema.
3. Preserve its event/source attributes and map them to
   `event_id`, `event_timestamp_utc`, `label_source`, and
   `label_source_reference` only when the source supports those mappings.
4. Do not generate negatives from points outside its polygons.

### Stage 2: Official Indian inventory coverage

1. Request current NRSC/ISRO Atlas and GSI data through their official access
   channels.
2. Confirm terms, CRS, geometry type, date precision, stable IDs, source
   methodology, and whether records are duplicates of the Kerala inventory.
3. Maintain a source crosswalk with
   `source`, `source_event_id`, `event_date`, `date_precision`, `geometry`,
   `mapping_method`, `confidence`, and `license`.
4. Search specifically for Karnataka/Kodagu coverage; do not infer it from
   Kerala or Western Ghats-wide claims.

### Stage 3: Environmental joins

For each verified event, extract covariates using the event geometry and a
documented time window:

- Sentinel-1 acquisition pairs and preprocessing metadata.
- IMERG and/or CHIRPS rainfall accumulations at 1, 3, 7, 15, and 30 days.
- IMD rainfall only after access and terms are confirmed.
- SRTM-derived terrain features with DEM version and resolution.
- Optional LHASA hazard/exposure values as a separate deployment covariate.

Never use LHASA or an environmental threshold to create the ground-truth label.

### Stage 4: Negatives and validation

Create a separate `unknown_or_unmapped` population first. Promote an observation
to a genuine negative only when the [ground-truth contract](./GROUND_TRUTH_DATA_CONTRACT.md)
requirements for coverage, review, source reference, and time window are met.
Split by event ID, then by geography/time when event IDs are unavailable. Keep
an untouched final event/time test set out of tuning, early stopping, threshold
selection, and calibration.

## Recommendation

Start with the 2018 Kerala inventory as a documented presence-only seed, then
obtain NRSC/ISRO and GSI layers under confirmed access terms. Add Sentinel-1,
rainfall, SRTM, and optionally LHASA as provenance-preserving covariates. Do
not retrain LandSense or claim real-world accuracy until the resulting records
have independent labels, event/time provenance, defensible negatives, and a
held-out event/time test set.
