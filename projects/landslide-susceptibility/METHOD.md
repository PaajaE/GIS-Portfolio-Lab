# Landslide Susceptibility — Method

> Status: **draft** — M1 (harvest + QA) and M2 (terrain kernels) done (2026-10-09); no model yet. Spec section: §6.
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
**Status: implemented and benchmarked (M2, 2026-10-09).**

**Kernels** (`rust/src/lib.rs`, PyO3 module `terrain_kernels`):
- `terrain3x3`: a single 3×3 pass giving slope (Horn 1981), northness/eastness of the downslope direction,
  profile and plan curvature (second derivatives from the Zevenbergen & Thorne 1987 coefficients; profile > 0
  concave, plan > 0 convergent) and TRI (Riley et al. 1999).
- `window_stats`: square (2r+1)² windows giving mean and sd (sliding sums in f64 on mean-centred values) and
  min/max (van Herk / Gil-Werman, O(1) per cell).

**Why Rust:**
- One nodata-aware pass produces all outputs; SciPy needs separate filters plus a nodata-count filter.
- The predictors are recomputed for two regions (290 M cells) and for the sensitivity runs.
- I/O, mosaicking and reprojection stay in GDAL/rasterio.

**Reference (oracle):** `landslide.terrain_ref`: vectorised NumPy for the 3×3 pass, explicit loops and SciPy C
filters for the windows. The oracle is itself tested on analytic surfaces (plane, paraboloid, cone).

**Semantics:** strict. Nodata, NaN or a window crossing the grid edge gives nodata. A gradient ≤ 1e-9 is flat,
so aspect and curvature are 0 there.

**Tolerances** (outputs are float32, computed in f64, rounded once):
- min, max, relief: exact
- mean / TPI: rtol 1e-6
- sd: atol 1e-4
- 3×3 outputs: rtol 1e-6, atol 1e-6
- These replace the planned "rtol 1e-9", which float32 storage cannot meet.

**Bug found by the benchmark and fixed:**
- The first version used summed-area tables. On 4096²–8192² grids its sd drifted by up to 3.7e-3 m, because
  rounding grows with grid totals.
- An exact check on sampled windows showed SciPy within 1e-7 and Rust off.
- The window sums are now sliding sums, and a regression test checks sd to 1e-5 against an exact two-pass
  computation on a 3000² grid.

**Benchmark** (`make bench`, `benchmarks/terrain_kernels.json`):
- Hardware: Apple M4, 16.0 GB, single-threaded (both implementations); rustc 1.99.0 (b940084d7 2026-09-28); NumPy 2.5.3, SciPy 1.18.1.
- Input: centre crops of the real 5 m DEM.
- Harness: `timeit.repeat`, median.

| Kernel | Cells | Window | Agree | Reference median (s) | Rust median (s) | Speed-up |
|---|---|---|---|---|---|---|
| terrain3x3 | 1024² | 3x3 | yes | 0.035 | 0.0125 | 2.8× |
| window_stats | 1024² | 3x3 | yes | 0.0492 | 0.0201 | 2.45× |
| window_stats | 1024² | 11x11 | yes | 0.0532 | 0.0198 | 2.69× |
| window_stats | 1024² | 21x21 | yes | 0.0514 | 0.0189 | 2.72× |
| window_stats | 1024² | 101x101 | yes | 0.0524 | 0.0177 | 2.96× |
| terrain3x3 | 4096² | 3x3 | yes | 0.5828 | 0.5449 | 1.07× |
| window_stats | 4096² | 3x3 | yes | 1.1584 | 0.4443 | 2.61× |
| window_stats | 4096² | 11x11 | yes | 1.1407 | 0.451 | 2.53× |
| window_stats | 4096² | 21x21 | yes | 1.1453 | 0.4469 | 2.56× |
| window_stats | 4096² | 101x101 | yes | 1.1583 | 0.4646 | 2.49× |
| terrain3x3 | 8192² | 3x3 | yes | 2.4408 | 0.8445 | 2.89× |
| window_stats | 8192² | 3x3 | yes | 5.4824 | 1.7218 | 3.18× |
| window_stats | 8192² | 11x11 | yes | 5.9472 | 1.8538 | 3.21× |
| window_stats | 8192² | 21x21 | yes | 6.3929 | 1.8003 | 3.55× |
| window_stats | 8192² | 101x101 | yes | 6.2342 | 2.0351 | 3.06× |

**Production run:**
- 132 kernel calls (derived in `terrain.run_region`) take 42 s of kernel time within 403 s of
  wall time for both regions. The rest is compressed GeoTIFF I/O.
- Peak RSS is 3.8 GB with 4096² tiles and a 54-cell halo.

**Honest reading:**
- Rust is 2.5–3.5× faster than SciPy's C filters for window statistics and ~1.1–2.9× for the 3×3 pass.
- Kernel time is ~10 % of a full predictor run, so the whole-run saving is about a minute.
- The value of the Rust kernels is the single strict-nodata pass with explicit, tested semantics rather than
  raw speed.
- No parallelism yet (not needed).

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
| 2026-10-09 | Window sums by sliding sums, not summed-area tables | summed-area tables | SAT sd drifted 3.7e-3 m on 8192² grids (found by benchmark agreement check); sliding sums accurate to 1e-5 |
| 2026-10-09 | Tolerances set for float32 outputs (exact / rtol 1e-6 / atol 1e-4) | rtol 1e-9 (plan) | float32 storage cannot meet 1e-9; both sides compute in f64 and round once |
| 2026-10-09 | Benchmark reference for the 3×3 pass runs in 1024-row bands | unchunked NumPy | unchunked needs ~16 GB at 8192² and swaps (12× slower), which would fake a speed-up |
