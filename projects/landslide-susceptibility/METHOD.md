# Landslide Susceptibility — Method

> Status: **draft** — feasibility check done, M1 in progress (2026-10-08). Spec section: §6.
> Each statement is tagged **[verified]** (checked against a primary source or live service on 2026-10-08),
> **[planned]** (design, see [`PLAN.md`](PLAN.md)) or **[assumption]** (to be tested). Results will replace the
> planned items as milestones complete.

## Problem / decision
**Question (spec §6):** can we build a spatially transferable landslide susceptibility model and show where its
predictions are reliable?

**Who acts:** NCGS, Buncombe and Yancey planning offices, emergency management and NCDOT geotechnical staff.
**Decision:** which slope units to prioritise for site-specific geotechnical review before the next extreme-rainfall
event. [planned]

**Output wording:** relative susceptibility to *initiation* of rainfall-triggered shallow landslides, as a
percentile of hillslope area.
- It is not hazard and not risk.
- It is not a probability of a future landslide. Calibration is evaluated only as a diagnostic, and class-level
  frequencies are reported as "observed in Helene, in held-out watersheds". [planned]

## Study area and analytical unit
**AOI:** Buncombe + Yancey counties, NC (2,520 km²), plus a Watauga County temporal slice. [planned, pending owner
decision]

Reasons:
- the densest Helene initiation mapping: 1,815 and 1,156 natural High/Moderate-confidence source areas [verified]
- one mapping method inside the AOI [verified]
- pre-event lidar from 2017 [verified]

**Feasibility (2026-10-08) [verified]:**
- 32 HUC-12s in the AOI; positives are strongly clustered (top 10 HUC-12s hold 98 %).
- Rainfall strongly confounds positive density.
- Watauga 2024 labels come from a different mapping method.
- Consequences are in the decisions log and `PLAN.md` §0b.

**Unit of analysis:**
- a 5 m grid; the median natural source polygon is 84 m² [verified]
- **slope units**: hydrological half-basins on a 10 m DEM, at accumulation thresholds 0.05 / 0.1 / 0.2 km² [planned]

**Reporting unit:** the slope unit. [planned]

## Data and rationale
| Dataset | Why | Variable | Status |
|---|---|---|---|
| NCGS Landslide Inventory of NC | labels: initiation zones by phase, confidence, modifier, storm | positives / exclusions | fields and counts verified |
| USGS 3DEP 1 m (lidar 2017-02/04) | pre-event terrain | slope, curvature, relief, TPI, roughness, contributing area, aspect | metadata verified |
| NCGS Geologic Map of NC 1985 | weathering / residual soil | lithology group | service verified |
| SSURGO | colluvium thickness, infiltration | depth to restrictive layer, HSG, clay % | SDA reachable |
| NLCD 2021 land cover and tree canopy (MRLC WCS) | root reinforcement, disturbance | land-cover group, canopy % | planned |
| NOAA MRMS 72 h QPE | trigger: triggered domain + adjustment covariate | storm-total rainfall | archive verified |
| WBD HUC-12 / HUC-10 | spatial CV blocks | groups | reachable |
| NC footprints, NCDOT/TIGER roads | exposure only (after validation) | counts, km | licence open |

Excluded predictors [planned]:
- **elevation:** encodes Helene's rainfall footprint
- **distance to road:** encodes road failures and mapping access
- **PRISM normals:** weak gradient, collinear with elevation

Full provenance: [`DATA_SOURCES.md`](DATA_SOURCES.md).

## Harmonization
[planned]
- EPSG:26917 (native CRS of the DEM tiles [verified]), NAVD88 m.
- 5 m grid on the UTM lattice; AOI + 2 km buffer.
- DEM `average`; continuous layers `bilinear`; categorical layers `nearest` or cell-centre rasterization.
- Strict nodata in kernels; water excluded.
- All predictors pre-event. Post-event imagery and lidar are used only as NCGS's mapping basis and for display.

## Baseline
L2 logistic regression on a VIF-pruned predictor set, fitted inside spatial CV folds. [planned]

## Advanced method
HistGradientBoosting with native categoricals, tuned only inside training folds; pixel and slope-unit variants.
Out-of-fold ranks drive all validation views; a final all-data model gives the product map. [planned]

## Validation
[planned]
- **Primary:** leave-one-HUC-12-out inside the triggered domain (500 m buffer), rainfall-stratified metrics, per-watershed replicates; plus leave-one-county-out, HUC-10 grouping and distance decay.
- **Temporal:** Watauga 1940 → Helene 2024.
- **Strata and contrast:** rainfall-stratified evaluation; random split as a contrast only.
- **Metrics:** ROC/PR-AUC, Brier, reliability, confusion at top 5/10/20 %, capture curves, spatial error map.
- **Intervals:** block-bootstrap CIs for metrics and for Δ(advanced − baseline).
- **Comparison, not validation:** USGS slope-relief susceptibility and the NCGS channelized debris-flow model.

## Uncertainty and sensitivity
[planned]
- **Separate layers:** prediction uncertainty (bootstrap rank spread), training-data density, out-of-domain (area
  of applicability).
- **One-at-a-time sensitivity:** unit threshold, negative buffer and ratio, positive definition, label dilation,
  grid size, domain threshold, rainfall contrast model.

## Decision metric
Held-out capture of mapped Helene initiation sites in the top *k* % of hillslope area (*k* = 5/10/20 % scenarios),
with uncertainty and out-of-domain flags per unit. [planned]

*Do not use it as* a hazard or runout map, a site-specific stability assessment, or a probability of future
failure.

## Rust component
[planned]
- **Kernels:** multi-scale square-window statistics (summed-area tables; van Herk/Gil-Werman min/max) and a 3×3
  multi-output terrain pass (Zevenbergen–Thorne curvature, Riley TRI).
- **Oracle:** a NumPy/SciPy reference on analytic surfaces.
- **Tolerance:** exact, or rtol 1e-9.
- **Semantics:** strict nodata and edges.
- **Benchmark:** §12 fields at several sizes. A small speed-up is reported as such.

## Limitations and omitted processes
Known before analysis:
- **One trigger event:** transfer to other storms is tested only in Watauga, with small n. [verified as a data limit]
- **Not modelled:** runout, deep-seated landslides, road-cut failures. Road-related source areas are > 50 % of
  Helene source areas and are excluded from the primary target. [verified]
- **Detection bias:** small, shallow and under-canopy failures are likely under-mapped. [assumption]
- **Mapped absence is not true absence**; county-wide inspection is assumed. [assumption]
- **Terrain after 2017** (new cuts and grading) is not represented.

## Decisions log
| Date | Decision | Alternatives considered | Reason |
|---|---|---|---|
| 2026-10-08 | Inventory = NCGS Landslide Inventory of NC (Helene source areas) | USGS US inventory v3; WA DNR; DOGAMI SLIDO | only candidate with pre-event lidar (2017), phase-separated polygons, confidence and modifier fields; WA/OR inventories are mapped on the predictor lidar |
| 2026-10-08 | AOI proposal: Buncombe + Yancey + Watauga temporal slice | +McDowell/Henderson; Yancey only | densest natural initiation mapping, uniform method; Watauga is the only area with two dated events on the same terrain |
| 2026-10-08 | Primary target = natural source areas (`None Apparent`), road-related as contrast | all source areas | road failures are a different process; including them makes road proximity a dominant artefact |
| 2026-10-08 | 5 m grid, slope units as reporting unit | 1–2 m; 10 m | median source polygon 84 m²; volume and micro-relief at 1–2 m; misregistration tolerance |
| 2026-10-08 | Elevation and distance-to-road excluded as predictors | include | trigger-footprint and mapping-access proxies |
| 2026-10-08 | No probabilities in the app; ranks + event-specific observed frequencies | calibrated probability map | single event, mapped-only labels; a probability would overstate the evidence |
| 2026-10-08 | Out-of-fold ranks for all validation views and slider metrics | final-model ranks everywhere | honest hit/miss display |
| 2026-10-08 | High-ranked units without mapped initiation are not called false positives | standard confusion terms in UI | mapped absence ≠ true absence; Helene did not test all slopes |
| 2026-10-08 | Slope units by half-basins with pysheds | GRASS r.slopeunits | no GRASS install; half-basins are the classical basis |
| 2026-10-08 | Before/after imagery only at curated sites | full-AOI swipe; hotlinked services | hundreds of GB; D10 self-contained cartography |
| 2026-10-08 | Owner: AOI Buncombe + Yancey; Watauga separate temporal test | +McDowell/Henderson | owner decision |
| 2026-10-08 | Triggered domain: MRMS 72 h ≥ 250 mm (200/300 sensitivity) | whole AOI | feasibility: < 250 mm covers 717 km² with 0.7 % of positives; absence there reflects no trigger |
| 2026-10-08 | Rainfall as adjustment covariate; product predicted at fixed reference rainfall; rainfall-stratified primary metrics | rainfall only for stratification (rev. 2) | positive density rises ~100× from < 250 to > 400 mm (ρ = 0.56 across HUC-12) |
| 2026-10-08 | Leave-one-HUC-12-out + per-watershed replicates (10 HUC-12 with ≥ 50 positives) | 5 balanced HUC-12 folds | top 2 HUC-12 hold 46 % of positives, 16 of 32 have none |
| 2026-10-08 | Watauga test indicative only: outlines natural/unassessed > 30 m from roads, smoothed predictors, recurrence baseline | primary temporal holdout | Watauga 2024 mapped on Nearmap imagery (different method), only 26 confirmed natural; 2017 terrain post-dates 1940 by 77 years |
| 2026-10-08 | NLCD 2021 land cover + canopy 2021 via MRLC WCS | Annual NLCD 2023 | 2023 not offered per year in WCS; consistent pre-event vintage |
| 2026-10-09 | DEM mosaic priority NC Phase 5 (2017) > NC Phase 4 (2016–17) > TN (2016) | alphabetical / first found | the AOI and Watauga use the same collection wherever it exists; cross-project overlaps have no vertical offset (|median| ≤ 0.09 m) |
| 2026-10-09 | Building footprints harvested for the buffered AOI only, local use | whole harvest bbox (430 k) | exposure is computed for the AOI only; licence unresolved |
| 2026-10-09 | NCGS channelized debris-flow model not treated as a pre-event reference | use as reference comparison | published 2025-04-28 (post-Helene), query disabled |
