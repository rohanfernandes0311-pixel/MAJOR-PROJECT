# Kodagu Satellite Imagery Feasibility

Status: **IMAGERY ACCESS BLOCKED — CATALOG OR AUTHENTICATION REQUIRED**

Research date: 2026-10-10. This is an imagery feasibility assessment only.
It did not train a model, create a label, alter production artifacts, or
change LandSense inference behavior.

## Pilot definition

The pilot envelope is the validated bounding box of the Kodagu polygon
inventory:

| Field | Value |
|---|---|
| CRS | EPSG:4326 |
| West | 75.461678 |
| South | 12.385906 |
| East | 75.832724 |
| North | 12.690308 |

This boundary is an exact source-derived envelope, not a guessed administrative
boundary. It is used because the polygon inventory has validated geographic
bounds and provides a bounded area for catalog queries. It does not imply that
the inventory is complete within the box or that every pixel was observed.

The source evidence supports an August 2018 Kodagu storm episode, but no
record-level occurrence date or event interval. The catalog search therefore
used 2018-07-01 through 2018-10-31 UTC as a broad imagery review window. The
window is not an assignment of dates to any landslide record. An imagery
acquisition timestamp is an observation date, not an onset date.

For the focused historical pass, July and August 2018 were queried separately
over the same envelope. The catalogs returned 55 observed item metadata results:
26 Sentinel-2 L2A, 10 Sentinel-1 GRD, 5 Sentinel-1 SLC (4 in July and 1
observed in a bounded August retry), and 14 Landsat Collection 2 Level-2
results. The initial August Sentinel-1 SLC request returned HTTP 429
(`WAF rate limit exceeded`); after a delay, a limit-1 retry retrieved one
August item. This is not a complete August count. The complete query counts,
retry method and error are retained in
[`data/research/kodagu_imagery_scene_register.json`](../data/research/kodagu_imagery_scene_register.json).

## Catalogs and actual results

### Copernicus Data Space — Sentinel-2

- Official catalog queried:
  [Copernicus STAC](https://stac.dataspace.copernicus.eu/v1/)
- Collection: `sentinel-2-l2a`
- Query used the pilot bbox and the July–October 2018 interval.
- Metadata was retrieved through an unauthenticated HTTPS STAC request.
- Observed examples:
  - `S2B_MSIL2A_20181024T051859_N0500_R062_T43PEQ_20230622T154852`,
    2018-10-24 05:18:59 UTC, 0.28% catalog cloud cover.
  - `S2B_MSIL2A_20181024T051859_N0500_R062_T43PEP_20230622T154852`,
    2018-10-24 05:18:59 UTC, 1.98% catalog cloud cover.
- The catalog footprint intersects the pilot envelope, and the nominal
  multispectral resolution includes 10 m bands.
- Product data were not downloaded. Scene-average cloud cover is not a
  pilot-level cloud/shadow mask.

### Copernicus Data Space — Sentinel-1

- Official catalog queried:
  [Copernicus STAC](https://stac.dataspace.copernicus.eu/v1/)
- Collection: `sentinel-1-grd`
- Metadata was retrieved through an unauthenticated HTTPS STAC request.
- Observed examples:
  - `S1B_IW_GRDH_1SDV_20181026T130645_20181026T130714_013324_018A2A_3A13_COG`,
    2018-10-26 13:06:45 UTC, IW, relative orbit 173, VV/VH.
  - `S1A_IW_GRDH_1SDV_20181025T004815_20181025T004840_024285_02A86F_45C1_COG`,
    2018-10-25 00:48:15 UTC, IW, relative orbit 63, VV/VH.
- The catalog footprint intersects the pilot envelope and the nominal GRD
  pixel spacing is approximately 10 m.
- GRD is not a deformation, coherence or stable-ground product. Processing
  would require appropriate pairs, terrain/geometric quality checks and
  scientific review. No SAR product was downloaded.

### USGS LandsatLook — Landsat

- Official catalog queried:
  [USGS LandsatLook STAC](https://landsatlook.usgs.gov/stac-server/)
- Collection: `landsat-c2l2-sr`
- Metadata was retrieved through an unauthenticated HTTPS STAC request.
- Observed examples:
  - `LC08_L2SP_145052_20181027_20200830_02_T1_SR`,
    2018-10-27 05:17:20 UTC, 1.42% catalog cloud cover.
  - `LE07_L2SP_145052_20181019_20200828_02_T1_SR`,
    2018-10-19 05:14:33 UTC, 55% catalog cloud cover.
- The footprints intersect the pilot envelope. Landsat surface reflectance
  nominally provides 30 m multispectral pixels.
- The October dates are later than the documented storm episode. The Landsat 7
  candidate has high scene-level cloud cover and requires pilot-level quality
  inspection. No product was downloaded.

The exact product IDs, catalog item URLs, footprints, retrieval method,
missing fields and validation statuses are in
[`data/research/kodagu_imagery_scene_register.json`](../data/research/kodagu_imagery_scene_register.json).

## July–August candidates and access screening

Seven additional July–August candidates were recorded in the scene register:

- Sentinel-2 L2A on 2018-08-25 for tiles T43PEQ and T43PEP. Catalog cloud
  percentages were 83.17% and 90.15%; these are metadata-only, high-cloud
  candidates.
- Sentinel-1 GRD on 2018-08-14 and 2018-08-15. These are storm-episode
  observation candidates, not event timestamps or labels.
- Sentinel-1 SLC on 2018-07-21 and 2018-07-22. These are possible pre-episode
  SAR references; the official item metadata was observed, but the product
  requires an authenticated/permitted download route and paired scientific
  processing.
- Landsat 8 on 2018-08-08, path 145 row 051, with 17.71% catalog cloud cover.
  This was the strongest optical metadata candidate observed, but an asset
  request returned EROS Registration System login HTML rather than image
  bytes. No response bytes were retained.

No full July–August imagery product was successfully downloaded. One small
catalog-linked Sentinel-1 GRD thumbnail was successfully retrieved and
validated as a 251 x 200 PNG (90,788 bytes; SHA-256
`3FA1071E59111C69A41F041DC19BEB2CF80C2B875FF32167583F201A54B628FC`).
It is a browse quicklook, not the scientific GRD raster, and was not used for
pixel-level pilot quality assessment. The dedicated
[`kodagu_imagery_download_manifest.json`](../data/research/kodagu_imagery_download_manifest.json)
contains that one browse asset and records the failed USGS attempts and the
authenticated Copernicus product blocker. No full scientific product has been
retained.

## Feasibility conclusion

The pilot is **catalog-ready but not human-review-ready**. Official catalogs
returned six October candidates plus 55 observed July–August metadata results.
One browse quicklook was retrieved, but it does not establish that any
candidate location was cloud-free,
visible, stable or adequately covered.

The July–August candidates remain metadata-only because product access was
blocked or rate-limited. The strongest optical candidate still requires pixel
quality inspection, and the SAR candidates require paired processing. No
candidate non-event observation has been independently verified.

## Independent review protocol

The machine-readable protocol is
[`data/research/kodagu_imagery_review_protocol.json`](../data/research/kodagu_imagery_review_protocol.json).
It requires:

1. Stable local keys that preserve the original source ID, source file and
   source row/feature index. Repeated Kodagu `Name` identifiers are not
   collapsed.
2. A documented pre-period and post-period scene pair, with acquisition times,
   footprints, pixel-level cloud/shadow quality and checksums.
3. Independent assessment of disturbance versus roads, agriculture, forestry,
   fire, seasonal vegetation, cloud/shadow and registration artifacts.
4. Review of point/polygon overlap and uncertain source identity. Proximity is
   not event identity.
5. A second qualified reviewer for proposed negatives or ambiguous cases,
   with adjudication notes.
6. `verified_non_event_for_observed_period` only when coverage is adequate and
   the reviewed period is explicitly bounded. Otherwise use
   `unknown_or_unobserved` or `requires_review`.

Satellite imagery alone cannot prove permanent stability or a negative outside
the observed location and period. Future imagery cannot establish that a site
was stable during an earlier unobserved interval. Model scores, terrain
measurements and inventory absence are prohibited as negative-label evidence.

## Access, licensing and limitations

Catalog metadata access succeeded without authentication during this audit.
The Copernicus OData product endpoint returned HTTP 405 without an
authenticated/permitted download session, while its separate catalog-linked
thumbnail endpoint permitted one quicklook download. The USGS Landsat
thumbnail requests returned EROS Registration System HTML rather than image
bytes. The exact attempts are recorded in the download manifest. A qualified
operator must complete the applicable Copernicus account/token flow or USGS
registration/institutional access flow to obtain full products. The local
authentication preflight found no CDSE credentials, bearer token, or OAuth
client configuration, so no full-product request was attempted in this pass.
After authorization, retain the source license, product version, item ID and
checksum before using or redistributing any product.

Important interpretation limitations include:

- Scene-average cloud percentages do not replace pixel-level masks.
- Vegetation, cloud, terrain shadow, layover, speckle and spatial resolution
  can hide small or covered landslides.
- Sentinel-1 GRD is not a ready-made deformation measurement.
- Landsat 30 m and Sentinel-2 10 m observations may not resolve small failures.
- Catalog footprints establish intersection, not adequate observation at every
  candidate coordinate.

## Current status and next action

- October scene candidates retained: **6**
- July–August catalog items observed: **55** (one August SLC item from a
  bounded limit-1 retry; not a complete August SLC count)
- July–August scene candidates recorded: **8**
- Full imagery products downloaded: **No**
- Browse assets downloaded: **1** (Copernicus Sentinel-1 thumbnail)
- Quality-screened from pixels: **0**
- Human review completed: **No**
- Independently verified non-event observations: **0**
- Labels created: **No**

**Next action:** complete the official Copernicus authentication/permitted
download flow or USGS EROS registration/institutional access route; provide
the authorized token only through a local environment variable or ignored
credentials file; retrieve one full optical or SAR product; create a
checksummed pilot subset; and have two qualified reviewers assess a bounded
candidate set using the protocol. Keep all obscured or temporally unsupported
locations unknown.

Final status: **FULL PRODUCT ACCESS BLOCKED — LOCAL AUTHORIZATION REQUIRED**
