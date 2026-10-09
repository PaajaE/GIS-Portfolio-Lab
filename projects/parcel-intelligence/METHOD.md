# Parcel Intelligence — Method

> Status: in progress — revised after the first `/quality-gate` review (2026-10-08); hand checks pending human review. Spec section: §5.
> Numbers below are from the run on 2026-10-08 (`make all`); the app reads them from `web/data/summary.json`.

## Problem / decision
**Question (spec §5):** given a parcel and stated planning assumptions, how much of it remains potentially
feasible, which constraints dominate, and how robust is that conclusion?

**Who acts:** a town planner, housing committee, land trust or site-selection analyst doing a first-pass
screen. **Decision:** which parcels deserve closer due diligence (survey, soils/septic tests, legal and
zoning review) and which are ruled out by mapped constraints regardless of reasonable assumptions.

**Output wording:** *potential feasibility under stated spatial screening assumptions* — not legal
development entitlement, not a buildability determination.

## Study area and analytical unit
**AOI:** Town of Amherst, Massachusetts (6,091 assessor parcels, 68.2 km²). Chosen because all inputs are
public domain and current (FY2026 parcels, 2026 3DEP lidar), and because the town combines the constraints
the method is about: Holyoke Range and eastern hills (slope), Fort River / Mill River floodplains (FEMA AE
with floodways), extensive mapped wetlands, a large share of protected land, and real development pressure.

**Reporting unit:** the parcel (`LOC_ID`). **Unit of analysis:** 2 m grid cells, so that the *shape* of the
feasible area inside a parcel is kept (spec: "parcel is the reporting unit, but feasibility is calculated
spatially"). A parcel average would hide exactly the fragmentation this screen is meant to detect.

## Data and rationale
| Dataset | Why | Variable supplied |
|---|---|---|
| MassGIS L3 parcels (FY2026) | reporting unit; land-use eligibility | geometry, use code, zoning code, year built |
| USGS 3DEP 1 m DEM | slope is a hard physical/engineering constraint | slope (%) |
| FEMA NFHL (via MassGIS, 2023-07-02) | regulatory flood hazard | floodway / 1% / 0.2% zones |
| MassDEP wetlands + 1:25k hydrography | Wetlands Protection Act resource areas and buffers | wetland, water, stream setbacks |
| Protected and Recreational Open Space | land legally protected from development | protection level P / T / L |
| NHESP Priority Habitat | regulatory review trigger (conservative only) | habitat polygons |
| MassDOT roads, building footprints | existing development; access | road surface, buildings, frontage, distance |
| MassDEP sewer service areas | servicing context (soft factor) | share in sewer area |

Full provenance: [`DATA_SOURCES.md`](DATA_SOURCES.md).

## Harmonization
- **CRS:** NAD83 / Massachusetts Mainland (EPSG:26986), metres, for every distance, buffer and area.
  Vector services are requested in EPSG:4326 and reprojected locally (PROJ 9.8.1); the DEM is warped from
  EPSG:26918. No computation is done in degrees.
- **Resolution: 2 m.** The source DEM is 1 m; slope from 1 m lidar is dominated by micro-relief (stone
  walls, ditches, root plates), which is not what a site screen means by "steep". Mean-aggregating to 2 m
  (GDAL `average`) suppresses that noise while resolving a 10 m building envelope by 5 × 5 cells. Area
  error from boundary rasterization is measured (see Validation), not assumed.
- **Resampling:** DEM `average` (continuous); slope classes for display `nearest`.
- **Vector → raster:** cell-centre rule (`all_touched=False`) for every layer, so a cell belongs to a
  constraint iff its centre lies inside. Buffers are computed on vectors with GEOS before rasterization.
- **Nodata:** slope is nodata where any cell of the 3×3 Horn window is nodata or at the grid edge; nodata
  is its own constraint bit and never treated as flat. Inside the parcels the nodata share is 0 (verified).
- **Geometry:** all layers checked with `is_valid`; one open-space polygon repaired with `make_valid`.
  Parcels: 0 overlapping pairs > 1 m² after collapsing condo stacks (total overlap 0.2 m²).
- **Time:** all constraints describe the present regulatory/physical state; FEMA vintage 2023-07-02 is
  older than the other layers (documented). There is no event/outcome variable, so no leakage question.

## Baseline
Two transparent baselines, both reported per parcel and scenario:
1. **Naive parcel screen:** the whole parcel counts if its mean slope is below the threshold and its
   representative point lies outside flood, wetland/water setback and protected land. This is the
   "parcel-wide average" the spec warns against.
2. **Net unconstrained area:** parcel area minus the union of all hard constraints (cell count × 4 m²),
   with no contiguity or minimum-size requirement — the common "net developable area" overlay.

## Advanced method
1. **Hard-constraint mask** per scenario (bit per category, so the breakdown is exact):
   flood, wetland/water/stream setback, protected open space, priority habitat (conservative), slope ≥
   threshold, uniform setback from lot lines (GEOS inner buffer), existing buildings and road surface,
   nodata. Hard exclusions only; sewer service and frontage are reported, never mixed in.
2. **Morphological opening** with a 5 × 5-cell (10 m × 10 m) square, *within each parcel*: a cell survives
   only if some 10 m square of feasible cells of the same parcel contains it. Removes slivers that a
   house footprint cannot use.
3. **Connected components** (4-connectivity, never across parcel lines) → largest contiguous patch,
   number of patches ≥ 500 m², feasible area after cleanup.
4. **Qualifying patch** = an eligible parcel's largest patch is ≥ 500 m² (MIN_PATCH_M2): one contiguous
   area outside all mapped hard constraints into which a 10 m square fits. (Called "usable" in the first
   version; renamed because it is a screening threshold, not usability.)
5. **Robustness class** from the three scenarios (they are nested — every constraint and the opening are
   monotone — and nesting is asserted for every parcel): *robust* (qualifies in all), *assumption-dependent*
   (moderate + aggressive), *only aggressive*, *constrained* (none), *not screened* (tax-exempt).
6. **Vacant vs built.** A parcel has a *structure* if at least half of some mapped building footprint
   lies inside it (so a neighbour's footprint spilling over an assessor line does not count) or the
   assessor records a year built (catches houses newer than the mostly-2011 footprints). *Vacant* = no
   structure (906 parcels, 565 of them screened in the moderate scenario); everything else is *built*.
   The assessor vacant-land class (13x/39x/44x) is reported but does not override a structure; the 45
   parcels where it conflicts (23 agricultural parcels, code 393, plus 22 vacant residential/commercial codes) are counted
   as built and flagged (`vacancy_conflict`, list in `validation/vacancy_conflicts.csv`); the report does
   not call their patch a yard. On a
   built parcel the patch is almost always the yard beside the building — land outside mapped
   constraints, not a separate building site. Every town-level result is reported for both groups, and
   the vacant figures lead.
7. **Leave-one-out relief:** for each constraint, recompute the largest patch without it. The *binding
   constraint* is chosen among **site constraints only** (flood, wetland/water, protected land, priority
   habitat, slope). Excluded from the choice: the uniform lot-line setback (removing a ring always adds
   area) and existing development (removing it means demolition; in the first version it was "binding" on
   3,521 of 5,540 eligible parcels, i.e. "remove the house"). Both reliefs are still reported per parcel.

**Why better than the baselines:** it answers "is there one qualifying piece, and where" rather than "how
much area in total", and it exposes which single assumption controls the answer.
**Assumptions:** hard constraints are binary; a 10 m square and 500 m² are a minimal building envelope;
mapped resource areas approximate regulated areas.

### Land-use eligibility
Tax-exempt parcels (state use class 9xx: municipal, state, university, religious, charitable, or any
assessor record on the parcel exempt) are **not screened** in any scenario: 551 parcels. Chapter 61/61A/61B
parcels (classes 6xx–8xx) are excluded only in the conservative scenario (right of first refusal, use
assessment). Assessor zoning codes are reported but not used: the permitted-use and dimensional tables of
the Amherst bylaw were not encoded (see Limitations).

## Scenarios
| Assumption | Conservative | Moderate | Aggressive | Reason |
|---|---|---|---|---|
| Slope excluded at ≥ | 15 % | 25 % | 35 % | 15 % and 25 % are thresholds commonly used in steep-slope provisions and site-planning guidance (not verified against the Amherst bylaw); 35 % is a permissive bound. The spec's example (20/25/30°, i.e. 36/47/58 %) is much steeper than typical residential practice, so it was not adopted |
| Wetland / water-body buffer | 50 m | 30 m | 15 m | spec example setbacks; 30 m ≈ the 100 ft Wetlands Protection Act buffer zone (310 CMR 10.02); 15 m ≈ the 50 ft no-disturb zones found in many local wetland bylaws (not verified for Amherst) |
| Perennial stream buffer | 61 m | 30 m | 15 m | 61 m = 200 ft Rivers Protection Act riverfront area |
| Intermittent stream / ditch buffer | 30 m | 15 m | 8 m | intermittent streams have no riverfront area; smaller buffers |
| Flood | 1 % + 0.2 % | 1 % (SFHA) | floodway only | SFHA development is permitted under conditions; floodway encroachment additionally requires a no-rise demonstration, so the aggressive case keeps only the floodway |
| Protected open space | P + T + L | P | P | only perpetual protection is certain |
| Priority habitat | excluded | — | — | review trigger, not a prohibition |
| Uniform lot-line setback | 10 m | 6 m | 3 m | stands in for front/side/rear yards (not district-specific) |
| Chapter 61 land | excluded | screened | screened | |
| Opening / min patch | 10 m square, 500 m² in all scenarios | | | varied in sensitivity |

## Validation
There is no ground truth for "developable". Validation therefore checks structural correctness, and
compares with independent information that measures a *related* construct (reported as comparison).

| Check | Result | Status |
|---|---|---|
| Rust kernel == SciPy reference, full town (moderate) | identical integers for every parcel (6,091; one 14 m² parcel has no cell centre) | verified |
| Rust kernel == reference, 72 random fixtures (3 opening sizes × 2 connectivities × 12 seeds) + hand-computed cases (borders, ties, empty input, parcel narrower than the opening, neighbour must not help) | all pass | verified |
| Slope kernel on an analytic plane, flat surface, nodata propagation | exact | verified |
| Raster vs exact GEOS overlay, per parcel | wetland/water: 1,837.58 vs 1,837.60 ha; 95th pct abs error 0.71 % of parcel area (flood 0.46 %, protected 0.27 %); median 6.6 m² | verified |
| Parcel raster vs vector area, total | ratio 1.0000015; 1 parcel (14 m²) has no cell centre | verified |
| Patch polygons vs raster patch area | equal (rtol 1e-9) | verified (test) |
| Scenario nesting con ⊆ mod ⊆ agg | holds for every parcel | verified (assert + test) |
| Assessor vacant-land classes: AUC of separating "developable or potentially developable" (176, of which 7 "potentially": codes 131, 441) from "undevelopable" (264) | largest patch 0.763, net 0.762, naive 0.675, parcel area only 0.641 (moderate); Δ(largest − naive) 95 % CI [0.046, 0.131]; Δ(largest − net) [−0.009, 0.011] | comparison |
| Qualifying share among assessor classes (moderate) | 84 % of "developable or potentially developable", 33 % of "undevelopable" | comparison |
| Footprints of 446 houses built ≥ 2000: share in constraints (moderate) | flood 0 %, wetland/water setback 4.2 %, slope ≥ 25 % 3.6 % (biased low: post-construction lidar), protected 2.7 % | comparison |
| Hand checks of 14 parcels: one vacant + one built per screened class, the 2 screened parcels with the largest naive overstatement, plus documented cases ([`validation/HAND_CHECKS.md`](validation/HAND_CHECKS.md)) | AI-assisted notes only | **pending human review** |

**Reading of the assessor comparison.** The assessor's developable/undevelopable class reflects legal
frontage, lot size, zoning and local knowledge — a different construct. The contiguous-patch metric agrees
with it clearly better than the naive parcel screen, **but not detectably better than the net-area
overlay**. Contiguity is not shown to improve ranking; its value is in the per-parcel answer (is there one
qualifying piece, where, and what blocks it) and in not counting fragmented area: under moderate
assumptions, the net overlay totals 1,653 ha on eligible parcels vs 1,286 ha in largest patches (−22 %).

**Hand checks — status: AI-assisted only, pending human review.** The coding assistant inspected the
rendered figures (hillshade + the model's own constraint layers), so the checks test plausibility and
implementation, not independent truth. Notes per parcel, the sampling rule and empty columns for a human
reviewer are in [`validation/HAND_CHECKS.md`](validation/HAND_CHECKS.md). No parcel has been reviewed by a
person yet. Defects these checks found and that were fixed: mixed assessor records on multi-record parcels
(pid 1795, UMass, was "robust"), and private-way pavement counted as feasible (pid 3424). Open issues they
raised: vacant-coded parcels with mapped buildings (pid 209), cul-de-sac bulbs (pid 3424).

## Uncertainty and sensitivity
One-at-a-time, from moderate. Moderate reference: **300 of 565 screened vacant parcels** qualify (373 ha in
their largest patches); 3,024 of 5,540 screened parcels overall, 2,724 of them built.

| Assumption varied (stricter / looser) | Vacant parcels qualifying | All parcels qualifying |
|---|---|---|
| Chapter 61 land excluded | 250 (−50) | 2,963 (−61) |
| uniform lot-line setback 10 m / 3 m | 252 / 337 (−48 / +37) | 1,970 / 3,888 (−1,054 / +864) |
| slope 15 % / 35 % | 267 / 304 (−33 / +4) | 2,581 / 3,145 (−443 / +121) |
| priority habitat excluded | 269 (−31) | 2,955 (−69) |
| wetland & stream setbacks | 275 / 319 (−25 / +19) | 2,785 / 3,170 (−239 / +146) |
| minimum patch width 14 m / 6 m | 284 / 310 (−16 / +10) | 2,640 / 3,444 (−384 / +420) |
| flood definition | 298 / 303 (−2 / +3) | 3,011 / 3,034 (−13 / +10) |
| protected-land levels P+T+L | 300 (0) | 3,024 (0: the T/L parcels are tax-exempt anyway) |

**Conclusion.** Counted over all parcels, the result is dominated by the lot-line setback and the minimum
patch width — i.e. by how much yard is left on built lots, which is not the decision question. Over
**vacant** parcels the picture is more balanced and more relevant: the stricter values of the setback, Chapter 61
status, the slope threshold, priority habitat and wetland setbacks each remove 25–50 parcels (8–17 %), while the
flood definition barely matters (floodplain parcels are mostly constrained by wetlands too). This is why
the app shows robustness classes and leads with vacant parcels. Not quantified: positional error of parcel
lines and wetland mapping (no independent reference data); resolution sensitivity (1 m vs 2 m slope).

## Decision metric
Per parcel: **largest contiguous potentially feasible patch (m²) under each scenario**, whether it is a
**qualifying patch**, the **robustness class**, **vacant or built**, the **constraint breakdown**, and the
**binding site constraint** with the area it would release.
Town level: qualifying vacant and built parcels and patch area per scenario, plus the sensitivity table.

*Use it to* prioritize vacant parcels for closer review and to see which assumption a conclusion hinges on.
*Do not use it as* a buildability, zoning-compliance or wetland determination; on built parcels the patch
is yard space, not a building site; distances are straight-line (not access), frontage is a geometric
proxy (not legal frontage), and sewer share is servicing context.

## Rust component
- **Kernel:** per-parcel morphological opening + 4/8-connected component labelling + per-parcel
  aggregation in one raster pass (`rust/src/lib.rs`, exposed via PyO3 as `parcel_kernels.screen_patches`).
  Erosion/dilation are separable run-length passes conditioned on parcel id; components by union-find with
  the smaller index as root (deterministic tie-break = first cell in row-major order).
- **Why Rust:** the operation is not available in GDAL/SciPy with per-parcel semantics; the reference must
  loop over 6,000 parcel crops in Python. It runs 24× per pipeline (3 scenarios + 7 leave-one-out + 14
  sensitivity rows; the count is derived from the outputs in `bench.py`).
- **Reference:** `parcel_intel.patches.screen_patches_reference` (SciPy per parcel bounding box). Tolerance:
  exact (integer outputs). Edge semantics: raster edge and other parcels count as infeasible.
- **Benchmark** (`make bench`, Apple M4, 16 GB, single-threaded, `timeit` medians, real moderate mask):

  | Cells | Parcels | Reference (s) | Rust (s) | Speed-up |
  |---|---|---|---|---|
  | 3.4 M | 286 | 0.061 | 0.022 | 2.8× |
  | 6.8 M | 1,347 | 0.183 | 0.053 | 3.5× |
  | 13.6 M | 3,350 | 0.388 | 0.108 | 3.6× |
  | 27.2 M | 6,090 | 0.770 | 0.229 | 3.4× |

  **Honest reading:** ~3.4× — 18.5 s vs 5.5 s per full pipeline (24 calls). Useful, not decisive at town scale; SciPy is
  already C. The Rust kernel's main value here is the explicit single-pass formulation with exact tests.
  Larger AOIs and denser parameter sweeps were not benchmarked. No parallelism yet (not needed).

## Limitations and omitted processes
- Not modelled: zoning dimensional and use rules, lot-area/frontage minimums, septic suitability (Title 5),
  soils and depth to ledge/groundwater, easements, title, wetland field delineation, stormwater rules.
- Uniform lot-line setback per scenario, not district-specific yards.
- FEMA flood data as of 2023-07-02 (FEMA servers unreachable from the build machine).
- Road surface by assumed half-width per road class; cul-de-sac bulbs and unmapped driveways missing.
- Vacancy from 2011-based footprints and assessor use codes; both can be outdated (e.g. pid 209).
- Hand checks are AI-assisted and not yet reviewed by a person.
- Building footprints mostly from 2011 imagery; some newer buildings missing.
- Bare-earth lidar is post-construction; graded areas look flatter than the original terrain.
- Parcel lines are assessor compilations, not surveys; boundary cells misassigned by up to one 2 m cell.
- One AOI; results are not transferable to other towns without rerunning (thresholds are regional practice).

## Decisions log
| Date | Decision | Alternatives considered | Reason |
|---|---|---|---|
| 2026-10-08 | AOI = Amherst, MA | Allegheny County PA; other MA towns | MassGIS data are public domain (Allegheny parcels had no stated licence); Amherst has slopes, floodplains, wetlands, protected land and 96 % zoning-code fill |
| 2026-10-08 | FEMA NFHL via MassGIS mirror | FEMA NFHL REST / MSC download | FEMA hosts refused connections from the build machine; vintage documented |
| 2026-10-08 | 2 m analysis grid, DEM mean-aggregated | 1 m; 5 m | 1 m slope dominated by micro-relief; 5 m too coarse for small lots; error measured |
| 2026-10-08 | Slope thresholds 15/25/35 % instead of spec example 20/25/30° | spec example | the example is far steeper than residential practice; thresholds presented as scenarios |
| 2026-10-08 | Collapse condo stacks by LOC_ID; one representative assessor record | mode per field | mode per field mixed records (found in hand check, pid 1795) |
| 2026-10-08 | Road surface added to existing development | buildings only | hand check pid 3424: private way counted as feasible |
| 2026-10-08 | Binding constraint excludes the uniform setback | include all | the setback always "binds" by construction (4,038 parcels) |
| 2026-10-08 | Python ↔ Rust via PyO3/maturin as a uv path dependency | CLI binary exchanging files | zero-copy NumPy, one `uv sync`, testable from pytest |
| 2026-10-08 | Tax-exempt parcels not screened | screen all | public/institutional land is not on the development market; still shown |
| 2026-10-08 | Split results vacant / built; lead with vacant (quality gate) | single totals | 2,724 of 3,024 qualifying parcels (moderate) are built — their patch is a yard |
| 2026-10-08 | Vacancy = no structure (own footprint ≥ 50 % inside, or assessor year built); use code does not override (final review) | footprint cell anywhere OR vacant-land code | 44 vacant-coded parcels had their own mapped building, 11 "vacant" parcels had an assessed building (half built 2017–2025), 28 parcels were "built" only through a neighbour's footprint spillover |
| 2026-10-08 | Hand-check sample frozen in `validation/hand_check_sample.json` | re-draw each run | a human review sheet must not change under the reviewer |
| 2026-10-08 | Existing development excluded from the binding-constraint choice (quality gate) | include | "binding = existing building" on 64 % of eligible parcels meant "demolish the house" |
| 2026-10-08 | "Usable" renamed "qualifying patch" (quality gate) | keep | the threshold screens area outside mapped constraints; it does not establish usability |
| 2026-10-08 | Hand-check sample: one vacant + one built per class, naive-overstatement picks from screened parcels only (quality gate) | 2 random per class, all parcels | first sample's overstatement picks were tax-exempt parcels |
