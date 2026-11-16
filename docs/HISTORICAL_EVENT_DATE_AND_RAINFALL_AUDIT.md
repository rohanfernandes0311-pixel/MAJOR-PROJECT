# Historical Event Date and Rainfall Feasibility Audit

Status: **PARTIALLY RECOVERED — STORM-LEVEL TIMING ONLY**

Audit date: 2026-10-09. This is a research evidence audit. Production
datasets, models, preprocessing, APIs, thresholds, alerts, geofencing,
databases, and frontend behavior were not changed.

## Conclusion

The acquired Kodagu and Kerala shapefiles contain spatial identifiers and
coordinates but no per-record event date, date interval, event identifier, or
source-to-record timing crosswalk. Consequently:

- Exact event dates recovered: **0**
- Record-level bounded intervals recovered: **0**
- Kodagu point records with unknown event date: **267**
- Kodagu polygon records with unknown event date: **217**
- Kerala point records with unknown event date: **4,728**
- Inventory/storm-level timing episodes documented: **2**
- Record-level rainfall matching performed: **0**

The separate registry is
`data/research/south_india_environmental_features/event_date_registry.json`.
It intentionally contains inventory-level evidence with a null
`source_record_id`; it does not silently fill dates into the extracted
terrain tables.

## Sources investigated

### Kodagu

1. [The source repository](https://github.com/Arpithaachaiah6/Landslide-inventory-for-the-2018-storm-event-of-Kodagu-in-the-Western-Ghats)
   and its README identify a 2018 storm-event inventory of 267 landslides.
   The point attributes are `Name`, `X`, and `Y`; polygon attributes are
   `Name`, `area`, `X`, and `Y`. Neither contains a date field.
2. [Arpitha et al. (2024), DOI 10.1007/s12524-024-01953-8](https://doi.org/10.1007/s12524-024-01953-8)
   describes the inventory methodology using field investigation and
   pre-/post-event Google Earth and Sentinel-2A interpretation. Image
   acquisition or interpretation dates establish observation evidence, not
   necessarily the onset date of each slide.
3. [NRSC disaster map](https://ndem.nrsc.gov.in/documents/Disaster_Document/2018/KA/kalandslide50dsc07092018/kalandslide50dsc07092018_map.pdf)
   provides official August 2018 rainfall-triggered landslide context for
   Karnataka. It does not provide a record-level date crosswalk for the
   downloaded Kodagu identifiers.

Result: an August 2018 storm-month episode is documented with medium
confidence, but all 484 Kodagu point/polygon records remain unknown at
record level. The polygon `Name` values containing `2018` are identifiers,
not timestamps.

### Kerala

1. [DANS dataset DOI](https://doi.org/10.17026/DANS-X6C-Y7X2) identifies the
   2018 monsoon rainfall inventory and reports 4,728 mapped landslides.
   The downloaded shapefile attributes contain no event date.
2. [Hao et al. (2020), Earth System Science Data](https://doi.org/10.5194/essd-12-2899-2020)
   documents construction of the inventory from multiple existing sources
   and image interpretation. This supports event-inventory provenance, not
   per-record onset dates.
3. [Kerala SDMA/IMD extreme-rainfall report](https://sdma.kerala.gov.in/wp-content/uploads/2020/08/IMD-Monsoon-Extreme-Rainfall-2018.pdf)
   documents the statewide 2018 extreme-rainfall episode. The evidence
   supports a peak storm period of 8-17 August 2018, with broader August
   accumulation also discussed. This is storm-level evidence only.

Result: the 8-17 August 2018 peak storm period is documented with medium
confidence, but no date is assigned to any of the 4,728 Kerala records.

## Date types and what they mean

| Evidence type | Supports record-level onset? | Use in this project |
|---|---|---|
| Storm/rainfall episode | No | Context and possible event-level analysis only |
| Government disaster report | Usually no, unless it identifies a location and date | Requires location-specific crosswalk |
| Satellite acquisition date | No by itself | Establishes that a slide was visible or absent on an image date |
| Field survey date | Not necessarily | Survey/observation date, not automatic onset date |
| Inventory creation/publication date | No | Provenance only |
| Source record with event timestamp | Yes, if identifiers and location match | None found in the acquired files |

## Rainfall feasibility

| Product | Historical and technical facts | Feasibility here |
|---|---|---|
| NASA GPM IMERG V07 | Global precipitation; 0.1-degree grid; half-hourly and daily products; historical record begins in 2000. Official Earthdata product pages: [half-hourly](https://www.earthdata.nasa.gov/data/catalog/ges-disc-gpm-3imerghh-07) and [daily](https://www.earthdata.nasa.gov/data/catalog/ges-disc-gpm-3imergdf-07). | Technically suitable for 2018 storm windows, but not extractable per record without dates. |
| CHIRPS v3 | 1981 to near-present; 0.05-degree land grid; daily products are derived/disaggregated products, with date-label limitations documented by CHC. [Official documentation](https://www.chc.ucsb.edu/data/chirps3). | Technically suitable for storm-level or dated records; not currently temporally matched. |
| IMD gridded rainfall | India-focused daily gridded product is a potentially higher-relevance source. [IMD grid-data portal](https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html). | Access and exact file/version were not validated in this pass; source and license details require confirmation before extraction. |

Only rainfall windows tied to an exact date or defensible interval should be
computed. For a true dated record, candidate windows may include 1, 3, 7, and
14 days ending at or before the event date. For the current inventories, a
storm-level aggregate could be studied only after explicitly defining the
episode and retaining it as storm-level, not record-level, evidence. No such
aggregate was generated here.

## Remaining requirements

1. Obtain source spreadsheets, field logs, or supplementary tables with a
   stable inventory identifier and occurrence date or bounded date interval.
2. Obtain satellite acquisition metadata and pre/post image IDs linked to each
   source record; treat these as observation bounds unless onset is separately
   documented.
3. Request location-specific government incident reports where a record can be
   matched by coordinates, name, road, village, or administrative reference.
4. Confirm an IMD rainfall release and version, then cross-check it against
   IMERG and CHIRPS rather than treating one gridded product as ground truth.
5. Preserve uncertainty and reviewer decisions in the date registry.

The validation script is
`scripts/validate_event_date_registry.py`; it ensures every evidence entry
has a declared precision, source URL, and review status, and prevents
inventory-level evidence from being interpreted as record-level timing.
