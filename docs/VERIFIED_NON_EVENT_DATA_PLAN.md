# LandSense Verified Non-Event Data Plan

Status: **SAMPLING PLAN READY — OBSERVATIONS NOT YET VERIFIED**

Research date: 2026-10-09. This plan does not alter production data, models,
preprocessing, inference APIs, thresholds, alerts, geofencing or databases.
It creates no negative records and does not train a classifier.

## Current decision

The acquired Kodagu and Kerala inventories are presence-only landslide
inventories. They contain zero independently verified non-event observations.
An absent point is therefore `unknown_or_unobserved`, not a Low-risk example.
The source and evidence inventory is
[`data/research/verified_non_event_source_inventory.json`](../data/research/verified_non_event_source_inventory.json).
The proposed record schema is
[`data/research/verified_non_event_review_schema.json`](../data/research/verified_non_event_review.schema.json).

The next concrete action is a bounded pilot in one selected Kodagu or Kerala
study frame. The pilot must obtain either a documented field survey or a
cloud-screened, quality-reviewed historical image series before admitting any
`verified_non_event_for_observed_period` record.

## What qualifies as a verified non-event

A verified non-event is a location and observation period for which an approved
search method had adequate spatial and temporal coverage and found no
landslide. It is not a permanent safety assertion. The record must include:

- WGS84 coordinates and a stable `observation_id`.
- The observation start and end timestamps, or an explicit unresolved value.
- The exact source reference, source checksum or immutable scene/report IDs.
- Search footprint, spatial resolution and coverage-quality assessment.
- The reviewer, review date, criteria, image quality and false-negative risk.
- Any nearby inventory records and the rule used to exclude or investigate
  them.
- A separate original source identifier and source row/feature index when the
  candidate came from an existing inventory or sampling frame.

The status values are intentionally distinct:

| Status | Meaning |
|---|---|
| `confirmed_landslide` | External evidence supports a landslide for the stated observation context. |
| `verified_non_event_for_observed_period` | Adequate documented search found no landslide only during the stated period and coverage. |
| `unknown_or_unobserved` | Coverage, timing, image quality or reporting completeness is insufficient. |
| `requires_review` | Evidence exists but reviewers have not resolved quality, overlap or disagreement. |

## Evidence methods

| Method | Strength | Weakness and false-negative risk | Current status |
|---|---|---|---|
| Documented field survey | Direct local observation; can inspect scarps, deposits and access context. | Limited footprint, observer and safety constraints; old or concealed failures can be missed. | Not conducted. |
| Historical imagery review | Retrospective, spatially explicit and repeatable using scene IDs and acquisition dates. | Clouds, vegetation, shadows, spatial resolution and revisit gaps can hide failures; image absence is not evidence. | Landsat, Sentinel and NASA discovery metadata reviewed as possible sources only. |
| Official incident records with coverage evidence | Useful when the agency documents reporting area, dates and reporting process. | Non-reporting is common unless completeness is demonstrated; records may be impact-focused. | NRSC/NDEM and Kerala SDMA sources reviewed for context; no negative label established. |
| Scientific stable-ground dataset | May provide a documented control class if sampling and verification are explicit. | Many susceptibility studies use pseudo-absences or low-susceptibility samples, which are not automatically verified negatives. | No suitable South Indian source confirmed. |
| Inventory absence | Simple to compute but has unknown reporting and search coverage. | High and unquantified false-negative risk. | Explicitly rejected. |

Terrain-based selection, model predictions, arbitrary distance buffers and
absence of a government report must not be used by themselves to create
negative labels. They can define candidate strata or exclusion checks, but
the final status remains unknown until independent evidence is reviewed.

## South Indian source assessment

The acquisition report confirms that the Kodagu repository and Kerala DANS
inventory were accessed and validated, but neither supports negative labels.
The NRSC/NDEM document and Bhuvan catalog are useful official context and
possible imagery/product routes, not complete stable-ground surveys. The
official Landsat, Copernicus Data Space and NASA Earthdata portals provide
time-stamped imagery or product discovery; access to a scene is not proof that
the scene is cloud-free or that no landslide occurred.

Source URLs, access states, reuse caveats and evidence limitations are recorded
in the machine-readable inventory. “Metadata page accessed” is deliberately
different from “candidate labels verified.” Licensing must be checked for each
downloaded scene, report or derived redistribution.

## Reproducible sampling protocol

### 1. Freeze a sampling frame

Select one bounded pilot frame, such as a documented catchment or a grid
covering a named Kodagu or Kerala study area. Record the boundary CRS, file
checksum, administrative/geographic rationale and inclusion date. Do not
sample from the whole state merely to increase row counts.

The frame must include the search footprint, not just points around known
landslides. Candidate generation may be stratified by terrain, land cover,
catchment or accessibility, but these are sampling strata rather than labels.

### 2. Define the observation period

Choose the period before reviewing outcomes. For historical imagery, retain at
least one suitable pre-period and one suitable post-period scene, with scene
IDs, acquisition times, cloud/quality masks and the reason the pair brackets
the review period. For field work, record the survey timestamp and any
defensible retrospective period separately.

The 2018 storm-level periods in the timing audit are not per-record event
dates. They may define a pilot review window, but cannot be copied into
individual event timestamps.

### 3. Exclude and investigate known events

Retain all source records and use local composite keys such as
`inventory:source-file:source-row` because Kodagu point `Name` and Kerala `No`
repeat. Preserve `source_record_id` separately. Do not infer event identity
from proximity.

Use an exclusion or review zone only after documenting its spatial reference,
geometry semantics and scientific rationale. A buffer is a candidate-review
rule, not a universal truth: it must account for inventory positional error,
polygon extent, image resolution and the possibility of nearby independent
events. Candidates intersecting a known inventory geometry or uncertain
overlap should be `requires_review`, not automatically negative.

Kodagu points and polygons remain separate until a source-backed crosswalk is
obtained. Repeated Kerala and Kodagu identifiers are not deduplicated.

### 4. Review independently

Two reviewers should independently inspect each candidate where feasible.
They record the same source IDs, coverage and uncertainty, then adjudicate
disagreements. A reviewer may accept a negative only when coverage is
`adequate`, the search criteria were met and the imagery/field observation was
interpretable. Cloud-obscured, inaccessible, out-of-footprint or ambiguous
locations remain `unknown_or_unobserved` or `requires_review`.

The JSON schema requires evidence, provenance and review fields. No populated
candidate file is included in this change.

### 5. Keep uncertainty and grouping

Use `event_id` only when supplied by a source or established by documented
independent evidence. Repeated measurements from one event must share its
event grouping. A negative applies only to its observed period. Store image
quality, reviewer disagreement, positional uncertainty and false-negative risk
in notes or a versioned extension.

## Evaluation gate

Supervised evaluation may begin only after all of the following are satisfied:

1. Positive and negative labels are independently supported, with a documented
   search footprint and observation period for every negative.
2. Every row has immutable provenance, a stable local key and preserved source
   identifier/row mapping.
3. Event grouping is available or a documented geographic/temporal proxy is
   accepted as a limitation.
4. Environmental features have units, source/version metadata and timestamps
   no later than the prediction context.
5. Candidate train/validation/test splits are event-separated, and geography
   or time separation is used when required by the deployment question.
6. The number of independent landslide events and independent negative
   observation periods is sufficient for the intended uncertainty estimates.
   There is no universal sample-count threshold: adequacy depends on event
   clustering, prevalence, label error, spatial support, target metric and
   the precision required for High-risk recall and false-negative estimates.
7. A final test set is frozen before model selection, calibration or threshold
   tuning.

Until that gate is met, the correct output is exploratory quality assessment,
not real-world accuracy or emergency-warning validation.

## Remaining limitations and next action

- No South Indian source reviewed here provides verified negatives ready for
  import.
- Historical imagery can support a negative only after scene-level review; it
  does not supply labels automatically.
- Official incident-record absence has unknown reporting completeness.
- The acquired inventories lack record-level dates and stable event
  crosswalks, limiting temporal matching.
- Repeated source identifiers require row-level provenance and must not be
  collapsed.

**Next action:** commission or select a bounded pilot frame, freeze its
boundary and review window, obtain scene metadata and imagery, and run the
two-reviewer protocol against the proposed schema. Keep every unresolved
candidate out of the negative class.

Final status: **SAMPLING PLAN READY — OBSERVATIONS NOT YET VERIFIED**
