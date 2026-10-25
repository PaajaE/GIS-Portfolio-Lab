# FirePath — M1a results (mathematical specification and analytic fixtures)

> Date: 2026-10-09. Scope: decisions D1–D3 from `CRITICAL_REVIEW.md`, analytic fixtures only, no data.
> Everything here comes from the pure-Python/NumPy reference implementations on the cloud container
> (Linux x86_64, 4 vCPU). Times are **not** Rust estimates. Evidence labels as in CRITICAL_REVIEW:
> [verified] by computation or test here, [sourced] from documents (here mostly search-engine excerpts,
> because the primary PDFs were blocked from this session), [hypothesis].

## Summary

| Decision | Outcome |
|---|---|
| **D1 propagation scheme (owner decision 2026-10-24)** | **Decided by the owner: hybrid (HY) at 30 m**, with the pre-registered code-verification criterion relaxed **for the LB 8 cases only**. The LB 8 / 45° tail (p95 16.1 %) is a documented, accepted limitation, not a verification pass; all other criteria stay as registered. Before M1b: a short pre-registered confirmation run of HY at 30 m (see "D1 decision" at the end). *Status after M1a-3:* Still undecided: no scheme meets the pre-registered V&V criteria at 30 m (see "M1a-3").** The level set is the only convergent scheme and passes all exact cases at 15 m; the hybrid has the best 30 m record. The decision goes back to the owner. *Earlier status (M1a bake-off):* Not decided: no candidate passed all pre-declared criteria.** Under the rule fixed in CRITICAL_REVIEW, the decision returns to the owner and M1b does not start. The WENO5 level set came closest (it passes criteria 1 and 3, misses criterion 2 at LB 8 by 0.5 pp, and fails the barrier fixtures). Radius-8 label-setting fails criteria 1–3 and passes the barriers. |
| **D2 LB relation** | **Decided:** FARSITE form (Finney 1998: Anderson 1983 − 0.397, *effective midflame* wind in **m/s**, cap 8) as the default; BehavePlus 1 + 0.25 U_E (mi/h) as a sensitivity. Units are verified algebraically. The source wording was read in excerpts of the primary document, not in the full text |
| **D3 wind multiplier** | **Adopted provisionally:** `a_u` on the 20 ft wind speed (systematic correction), plus a separate scenario factor λ for input uncertainty. The model cannot distinguish them (tested), so they are kept apart by design |
| M0 on the Mac | **Not run.** This session cannot reach the Mac (`M0_RESULTS.md`). M1b stays NO-GO |

## D1: propagation-scheme bake-off

**Setup** (`firepath.bakeoff`; raw results `validation/m1a_bakeoff_*.json`, combined
`validation/m1a_bakeoff_summary.json`):
- Grid and source: 121 × 121 cells of 30 m, uniform R_head = 1 m/min, source at (90, 30).
- Wind angles 0–45° in 2.5° steps; LB 2, 3, 4, 8.
- Error measured on forward cells ≥ 25 cells from the source.
- Exact references:
  - label-setting: point ellipse;
  - level set (2-cell ignition disc): disc ⊕ ellipse, computed from support functions; Steiner formula
    for the area at t = 1500 min;
  - wind change: Minkowski sum for a 90° turn at 600 min.

All four runs ran concurrently on 4 vCPU, so the times include contention.

**Candidates.**
- *A:* time-dependent label-setting with stencil radius 8 (`reference.propagate`).
- *B:* Eulerian level set for φ_t + H(∇φ) = 0, where H is the support function of the focus-anchored
  ellipse (the front-normal speed of the Huygens envelope, which also resolves CRITICAL_REVIEW P1-11),
  with local Lax–Friedrichs dissipation (`levelset.propagate_levelset`), in two variants:
  - B2: ENO2 + Heun;
  - B5: WENO5 + TVD-RK3.
- *Context:* radius-2 label-setting (the v1 default).

**Implementation changes made during the bake-off, reported as such:**
1. **B5 was added after B2's results were seen.** The criteria did not change.
2. Level-set dissipation was tightened twice before the sweep: direction-specific Lax–Friedrichs bounds,
   then local (gradient-box) bounds. These are standard LLF choices; the first version was 2–44 % late.
3. **Level-set barriers:** with frozen barrier values the front **could not pass a one-cell gap at all**.
   Zero-flux barrier faces, with a first-order fallback where the high-order stencil touches a barrier,
   fixed the blockage.

**Results against the pre-declared criteria** [verified]:

| Criterion (limit) | A: radius-8 graph | B2: level set ENO2 | **B5: level set WENO5** | radius-2 graph (v1) |
|---|---|---|---|---|
| 1. worst forward arrival error, LB ≤ 4 (≤ 5 %) | 6.1 % ✗ | 5.5 % ✗ | **0.7 %** ✓ | 86 % ✗ |
| 1. … at LB 8 (≤ 10 %) | 24.3 % ✗ | 13.2 % ✗ | **1.5 %** ✓ | never reached the ring ✗ |
| 2. burned-area spread across wind angles (≤ 3 %): LB 2 / 3 / 4 / 8 | 1.4 / 2.3 / 4.0 / 17.0 % ✗ | 1.6 / 4.1 / 6.0 / 10.2 % ✗ | **0.8 / 1.3 / 1.8 / 3.5 %** ✗ (only LB 8) | 5.6 / 18 / 33 / 95 % ✗ |
| 3. wind turns 90° (≤ 5 %): LB 2 / 4 | 3.4 / 13.7 % ✗ | 6.4 / 18.0 % ✗ | **1.1 / 3.2 %** ✓ | 31 / 106 % ✗ |
| 4. barrier and initial-perimeter fixtures | ✓ no leaks; ≤ geodesic × 1.0276 + 0.1 cell | ✗ as B5 | ✗ no leaks through one-cell straight or diagonal walls, but **up to 3.2 cells late behind a one-cell gap** (fixture allows 2), 10–23 % late vs the geodesic, and 11 % late around a lake at the initial boundary (16.1 vs 14.5 cells) | ✓ |
| 5. cost (Python/NumPy, this container) | median 4.7 s per run, scaling with *burned* cells × 176 edges | 4.7 s | 10.6 s, scaling with *all* cells × steps (no narrow band yet) | 0.1 s |

The radius-8 graph's criterion-1 values match the exact geometric prediction to 0.1 pp (6.07 vs 6.1 %,
24.26 vs 24.3 %). The graph's wind-change error (13.7 %) is larger than its static error at the same LB,
because graph paths bend only at nodes.

**Exact asymptotic values for larger graph stencils** (`firepath.stencil_table`, not a propagation run):

| Radius → directions | c1 LB ≤ 4 | c1 LB 8 | c2 LB 4 / 8 |
|---|---|---|---|
| 8 → 176 | 6.1 % | 24.3 % | 3.4 / 17.3 % |
| 12 → 368 | 2.7 % | 11.0 % | 1.2 / 7.6 % |
| 16 → 640 | 1.5 % | 6.2 % | 0.5 / 3.9 % |

So radius 16 passes criterion 1 but misses criterion 2 at LB 8. Its criterion 3 was not measured. Its
cost is about 7× radius 8 per cell (directions × traversal length): roughly 12 ms per cell in this
Python reference [estimate].

**Diagnostic outside the pre-declared criteria: fuel-speed contrast** [verified;
`test_fuel_contrast_delay_is_first_order`]. 1-D, fast (1 m/min) → slow (0.25 m/min) at 135 m; exact
arrival at 300 m is 735 min (level set, 2-cell disc):

| Cell size | B2 | B5 | label-setting |
|---|---|---|---|
| 30 m | +13 % (831) | +11.6 % (820) | exact on the cell-face-aligned case |
| 15 m | +3.9 % | +3.2 % | — |
| 7.5 m | +1.4 % | — | — |

The level set loses about 0.7–0.8 cell of slow-fuel travel time at each fast→slow interface. This is the
usual first-order behaviour of shock-capturing schemes at speed discontinuities. At 30 m and slow
timber-litter speeds that is on the order of an hour per interface, and real 30 m fuel maps have many
interfaces. **This was not a pre-declared criterion and decides nothing by itself. It is relevant to D1.**

**Other level-set limitations found** [verified]: ignitions smaller than about one cell vanish under
ENO2 numerical viscosity (`test_sub_cell_ignition_is_erased_by_numerical_viscosity`); WENO5 keeps them
but starts late by about 0.7 cell.

**Verdict under the pre-declared rule:** no scheme passes criteria 1–4, so the cheapest passing scheme does
not exist, D1 returns to the owner, and **M1b does not start.** Neither scheme is adopted silently. Options:

| Option | Strengths (measured) | Weaknesses (measured) | Smallest next experiment |
|---|---|---|---|
| **B5 level set** | best shape and wind-change accuracy (≤ 1.5 % / 3.2 %); grid-orientation-free | barriers (one-cell gaps, obstacle corners) and fuel contrasts give O(Δx) delays; misses c2 at LB 8 by 0.5 pp; whole-grid cost until a narrow band exists | heterogeneous-mosaic comparison against a refined-grid reference; a sub-cell barrier treatment (e.g. a cut-cell or immersed-boundary face flux), re-run c4 |
| **Radius-16 graph** | exact barriers and contrasts on its paths; passes c1 | c2 3.9 % at LB 8; c3 not measured (bends only at nodes); ~7× the cost of radius 8 | c3 at radius 16; the same mosaic comparison; cost per cell |
| **Hybrid** (level set in open fuel, graph near barriers) | could combine the strengths | unproven; coupling is a design project | only if both single schemes fail the experiments above |

**Recommendation:** run the two experiments in the right column (the mosaic reference and radius-16 c3,
plus one barrier treatment for B5) before choosing. Do not change the criteria. The mosaic test should
get its own pass threshold, declared before it runs (proposal: median |error| ≤ 5 % and 95th percentile
≤ 10 % vs a 4× refined reference on a random 30 m two-fuel mosaic with 4× speed contrast).


## D2: length-to-breadth relation

**Question:** which LB relation, which coefficients, which units?

| Source (as reached) | Relation | Wind variable / units | Status |
|---|---|---|---|
| Finney 1998, *FARSITE: Fire Area Simulator — model development and evaluation*, RMRS-RP-4 (search excerpts of the PDF on frames.gov / fs.usda.gov) | LB = 0.936 e^(0.2566 U) + 0.461 e^(−0.1548 U) − 0.397; "the relationship developed by Anderson (1983) … assuming the fires grow as a single ellipse"; −0.397 "to have LB = 1.0 on flat terrain with no wind"; "ellipses with LB greater than 8 are truncated" | "the 'effective' midflame windspeed (U m s⁻¹)" | [sourced: excerpt] |
| Anderson 1983, INT-305 (original) | original form (without −0.397) | not seen | **not accessed** (blocked) |
| BehavePlus source `xfblib.cpp` (search excerpt) | surface LB = 1 + 0.25 × effective wind speed | mi/h | [sourced: excerpt]. The same file cites Rothermel (1991) only for a *crown-fire* relation (20 ft wind, coefficient 0.125), so CRITICAL_REVIEW's attribution of the linear surface relation to Rothermel 1991 is **not confirmed** |
| pyretechnics 2026.8.10 (read in full) | "behave" mode: 0.936 e^(0.1147 U) + 0.461 e^(−0.0692 U) − 0.397, cap 8; "rothermel" mode: 1 + 0.25 U | mi/h | [sourced: code] |
| ELMFIRE docs (search excerpt) | "Anderson (1983) as modified by Finney in FARSITE", L/W = 1 at zero wind, cap 8 | mi/h | [sourced: excerpt]; coefficients not seen |
| A WildEST report (search excerpt) | the same exponential form with "effective midflame wind speed (mi/h)" and different transcription (0.93, 0.15481) | mi/h | [sourced: excerpt]. Coefficients disagree with Finney 1998 |

**Verification [verified]:** 0.2566 / 2.23694 = 0.11471 and 0.1548 / 2.23694 = 0.06920. The m/s and
mi/h forms are the same function within coefficient rounding (< 0.5 % for 0–12 m/s;
`test_anderson_units_mph_vs_ms_forms_agree`). PLAN v1's error (m/s coefficients with mi/h input) is
confirmed. At 10 mi/h it gives LB 8 (cap) instead of 2.78 (`test_plan_v1_unit_error_is_large`).

**Decision.** Use the FARSITE form with U_E in m/s, cap 8 (`ellipse.lb_anderson_ms`, `rothermel.head_and_shape(lb_model="farsite")`).
It is the relation of the 2-D growth-model lineage this project compares itself with (FARSITE/FlamMap,
ELMFIRE), and it takes the effective wind from E5. BehavePlus' linear relation is kept as a sensitivity
(`lb_model="behaveplus"`). The two diverge strongly: LB at 10 / 20 mi/h is 2.78 / 8 (cap) vs 3.5 / 6.0
(`test_lb_relations_at_reference_speeds`). **Still open:** read the full text of RP-4 and INT-305 on the Mac
(blocked here), and resolve the WildEST transcription discrepancy (0.93 vs 0.936).

**10 m → 20 ft (E12).** No primary source was found for ÷ 1.15. A press source reports ÷ 1.2 for the NWS. A
neutral log profile gives 1.09 / 1.12 / 1.16 / 1.20 for z0 = 0.03 / 0.1 / 0.3 / 0.5 m (computed). Because the
factor multiplies wind speed, its error is absorbed by `a_u` (D3) and cannot be identified separately. This
is stated as a limitation, not resolved.

## D3: wind multiplier on wind speed, and input uncertainty

Implemented in `firepath.rothermel.head_and_shape` (E2–E7 on a given R0). Tests in
`tests/test_wind_parameterisation.py` (8 tests, all pass) [verified]:

| Test | Result |
|---|---|
| φ_w inversion round trip | exact (rel 1e-12) |
| wind/slope vector combination | aligned: R0(1 + φ_w + φ_s); opposed: R0(1 + \|φ_w − φ_s\|) |
| **`a_u` ≡ scaling the input wind** (FARSITE and BehavePlus LB) | identical R_head, LB, e (rel 1e-12) |
| v1 `a_w` inside φ_w | effective wind × a_w^(1/B). For the illustrative fine-fuel bed (σ = 2000 ft⁻¹) B = 1.53, so a_w = 1.3 changes U_E by 1.19. The shape distortion is real but smaller than CRITICAL_REVIEW first stated (corrected there) |
| `k` | scales R_head, leaves LB unchanged |
| elasticity d ln R / d ln a_u | = B φ_w/(1 + φ_w), the same as for the input wind |
| **`a_u` = 1.2, λ = 1 vs `a_u` = 1, λ = 1.2** | **bit-identical arrival fields** in full propagation |
| Andrews 2013 ROS cap | never increases R_head |

**Separating model sensitivity from input uncertainty.** The model sees only the product λ·a_u, so no
amount of fitting can split them. The plan therefore splits them by design:
1. `a_u` is the systematic correction (HRRR speed bias at the fire, the E12 conversion, WAF error). It is
   estimated on the calibration fires and frozen.
2. λ is the input uncertainty for scenarios. It is centred at 1, and its spread comes from the *random*
   part of an independent HRRR-vs-RAWS comparison (station data, M1b). Using the full HRRR error,
   bias included, would count the bias twice.
3. Reports keep the two apart: the parameter range (behavioural set of `a_u`) and the input range (λ).

What this does **not** establish: that a single `a_u` transfers between fires or wind regimes (M3/M4),
and that the HRRR error is stationary. The illustrative fuel bed is not an SB40 model; the full fuel table
(E1) is still M1a work.

## M1a-2 (exploratory, superseded for scheme selection)

> All level-set numbers in the D1 bake-off section above and in this M1a-2 section came from the level
> set **before** the narrow band, reinitialization and extension velocities (METHOD L5). The code now
> defaults to the fixed version, so re-running `make bakeoff` or `firepath.mosaic` gives different values.
> The committed JSON files are the historical record.

Pre-registered in `validation/M1A2_PREREGISTRATION.md` (commit `379068e`). Raw results are in
`validation/m1a2_*.json` and `m1a_bakeoff_hybrid.json`.

- **E2, radius-16 graph under a 90° wind change: failed.** Max error 3.3 % at LB 2, 13.6 % at LB 4 (limit
  5 %), no better than radius 8 (13.7 %). Long edges cannot turn mid-edge, so a bigger stencil does not help.
- **E3, level-set barrier treatment:**
  - zero-flux barrier faces let the front through a one-cell gap (it had been blocked completely);
  - a **hybrid** (level set, then label-setting seeded with the level-set arrivals) passed the gap and
    lake fixtures;
  - on the bake-off fixture the hybrid passed criteria 1 and 3, but criterion 2 at LB 8 came out at
    3.2 % (limit 3 %).
- **E1, mosaic vs refined references: inconclusive.** The two fine-grid references (radius-16 graph,
  level set) disagreed (LB 4: median 2.8 %, p95 10.5 %), so by the rule candidates had to pass against
  both, and none did.
  - Deviation: cells beyond the solver horizon had first counted as infinite error. The solvers were then
    run to 6,000 min and scored on reference arrivals ≤ 4,000 min.
- **Defect found: level-set phantom arrivals.** In the isotropic mosaic, the level set burned 537–568 cells
  before their hard physical lower bound (distance from the initial raster region ÷ maximum speed),
  e.g. 679 min where ≥ 1,308 min is possible. Cause: no narrow band or reinitialization (see M1a-3).
- **Practice review.** After these results, the owner asked for the approach to be checked against
  established practice (`PRACTICE_REVIEW.md`). The bake-off and E1 had mixed code verification, solution
  verification and code-to-code comparison, and had judged a level set without reinitialization. The
  approved revision is M1a-3.

## M1a-3: revised verification (V&V-based), the basis for D1

Pre-registered in `validation/M1A3_PREREGISTRATION.md` (commit `e4d981a`) before the runs. This is
**numerical verification only**: it shows how well each scheme solves the *model's* equations. It says
nothing about agreement with real fires (validation, PLAN §8–9, separate).

**The 5 % / 10 % thresholds are FirePath acceptance criteria, not industry standards.** For context:
Muñoz-Esparza et al. (2018) report < 1 % ROS error for a state-of-practice level set on analytic cases.
Every result is reported as a median (typical error) **and** a 95th percentile (tail).

### Fixes made before the runs (reported as deviations from the v2 wording)

1. **Level set, state of practice:** narrow band (8 cells) and geometric reinitialization every 10 steps
   (as pre-registered), plus two refinements chosen on 30 m smoke tests *before* the runs:
   - redistancing interface-adjacent cells too, which was more accurate than keeping them;
   - **extension velocities** (Adalsteinsson & Sethian 1999), because reinitialized fronts otherwise
     arrived *early* when entering slower fuel (−2.6 % at a 4× contrast; the strip was 10 min early).
2. **Regression test** `tests/test_levelset_regression.py`: no cell may burn before distance-from-raster ÷
   max speed (no slack). The pre-fix code fails it with 568 violations; the fixed code has 0 in all three
   mosaic cases. Graph arrivals also have 0.
3. **Barrier reference (B):** the geodesic is measured from the **raster** initial region (the cells all
   schemes start from), not from the ideal disc. The disc reference made every graph scheme look 2 % early,
   which is an initial-condition mismatch, not a physics violation. This choice was made after seeing the
   disc-reference results, so both are reported.

### A. Code verification (exact solutions; Δ = 30 / 15 / 7.5 m)

Median / p95 relative arrival error (%) at 30 m; observed order p from the medians (30→15, 15→7.5); cases
failing at 30 m are listed. Full tables: `validation/m1a3_A_<scheme>.json`.

| Scheme | Cases passing at 30 m (of 17) | Failures at 30 m (median / p95 %) | Converges? | Errors at 7.5 m (median, worst p95) |
|---|---|---|---|---|
| **LS** (level set) | 14 | LB 8 at 22.5°: 5.36 / 6.96; LB 8 at 45°: 7.93 / 17.1; wind change LB 4: 1.25 / 11.5 | **yes**, p ≈ 1.3–2.3 on almost all cases (the circle: 1.41 → 0.29 → 0.12 %) | ≤ 0.63 %, ≤ 1.21 % |
| **G8** (radius-8 graph) | 14 | the three LB 8 ellipses: p95 20.0–29.4 % (medians 1.5–3.9 %) | **no**: erratic p (−2 to 2.3); the LB 8 tail stays ≈ 17 % at 7.5 m (fixed-stencil angular error) | ≤ 1.31 %, ≤ 17.7 % |
| **HY** (hybrid) | 16 | LB 8 at 45°: 2.07 / 16.1 | partly: inherits the graph's raster-start bias (circle 1.23 % *early* at 30 and 15 m) | ≤ 0.82 %, ≤ 1.73 % |
| **G16** (radius-16 graph) | 14 | the three LB 8 ellipses: p95 16.9–21.0 % (medians 1.2–2.6 %) | **no clean order** (p −2.1 to 2.2). The LB 8 tail shrinks with refinement (p95 2.7–4.3 % at 15 m) | ≤ 0.91 %, ≤ 3.87 % |

Run time for all 17 cases (pure Python/NumPy, cloud container, 4 vCPU shared by 3–4 jobs), at 30 / 15 / 7.5 m: LS 16 / 84 / 777 s · G8 21 / 86 / 359 s · HY 34 / 160 / 1,058 s · G16 93 / 459 / 1,816 s. These times are relative indications only, not Rust estimates.

Reading: the level set behaves like a consistent scheme, with errors that shrink at about second order
under refinement. At 30 m its error near the small initial disc and for very elongated fires is still
above the FirePath limits. The graph's error does not shrink with refinement, because its angular bias
is built into the stencil. In the LB 8 tail that bias is large.

### B. Barriers (geodesic references, 30 m)

| Scheme | Gap: never early / within the upper tolerance / worst late (raster ref) | Same, disc ref | Lake | Thin-wall leaks | **Pass** |
|---|---|---|---|---|---|
| G8 | ✓ / ✓ / 3.8 % | ✗ (−2.2 % early) / ✓ | ✓ | 0 | **✓** |
| G16 | ✓ / ✓ / 3.8 % | ✗ / ✓ | ✓ | 0 | **✓** |
| LS | ✓ / **✗** / 17.2 % | ✓ / ✓ / 14.3 % | ✓ (319 vs geodesic 290 min) | 0 | **✗** |
| HY | ✓ / ✓ / 3.8 % | ✗ / ✓ | ✓ | 0 | **✓** |

### C. Solution verification on the random two-fuel mosaic (no exact solution)

Each scheme on its own 30 / 15 / 7.5 m sequence. Richardson is used only where its assumptions hold
(monotone convergence, 0.5 ≤ p ≤ 3). If fewer than 80 % of scored cells qualify, no acceptance claim is
made and only the raw 30 m vs 7.5 m difference is reported.

| Scheme / case | Richardson-applicable share | Raw \|f30 − f7.5\|/f7.5 median / p95 | Est. 30 m error median / p95 (applicable cells only) | Lower-bound violations | Pass |
|---|---|---|---|---|---|
| G8 iso | 15 % | 2.7 % / 9.4 % | (2.0 % / 5.9 %, not claimable) | 0 | ✗ (not applicable) |
| G8 LB 2 | 67 % | 2.6 % / 10.5 % | (4.7 % / 13.6 %) | 0 | ✗ (not applicable) |
| G8 LB 4 | 53 % | 2.2 % / 15.2 % | (5.5 % / 21.2 %) | 0 | ✗ (not applicable) |
| LS iso | 76 % | 4.7 % / 8.7 % | (6.1 % / 12.1 %) | 0 | ✗ (not applicable) |
| LS LB 2 | 68 % | 4.0 % / 9.0 % | (6.6 % / 12.8 %) | 0 | ✗ (not applicable) |
| LS LB 4 | 62 % | 2.8 % / 8.2 % | (3.9 % / 12.3 %) | 0 | ✗ (not applicable) |
| HY iso | 15 % | 2.7 % / 9.4 % | (2.0 % / 5.9 %) | 0 | ✗ (not applicable) |
| HY LB 2 | 68 % | 2.6 % / 10.4 % | (4.7 % / 13.1 %) | 0 | ✗ (not applicable) |
| HY LB 4 | 42 % | 2.0 % / 14.3 % | (4.3 % / 20.1 %) | 0 | ✗ (not applicable) |

G16 was not run on the mosaic (pre-registered: code-verification cases only, because of its cost).

**Richardson/GCI was not applicable in any case.** Fewer than 80 % of cells converged monotonically
within the 0.5 ≤ p ≤ 3 window (15–76 %). Two reasons: speed discontinuities at fuel edges make
convergence non-monotone, and for the graph schemes the fixed-stencil angular error does not vanish
under refinement. So no scheme can claim an acceptable mosaic error from solution verification.

**Code-to-code cross-check (a comparison, not a verification).** Graph arrival times are upper bounds on
the model's exact solution (each graph path is a physical path with exactly integrated travel time).
So wherever the level set is later than G8, its own error is **at least** that difference.
(LS − G8)/G8 on the mosaic, median [p5, p95]:
- isotropic: **10.5 % [6.4, 24.8]** at 30 m → 3.3 % [1.2, 8.6] at 15 m;
- LB 4: **7.2 % [0.1, 23.6]** at 30 m → 3.5 % [0.4, 12.0] at 15 m.

In a 4× contrast mosaic, the level set's 30 m error is therefore ≥ ~7–10 % in median, larger than its own
30 vs 7.5 m difference suggests (pre-asymptotic). At 15 m the bound falls to ~3.5 %.

### Verdict under the pre-registered rule

**No scheme meets the pre-registered acceptance criteria at 30 m.**

| Scheme | A: code verification at 30 m | B: barriers | C: mosaic | Lower bound | Acceptable |
|---|---|---|---|---|---|
| LS | ✗ 14/17 (LB 8 elongation, wind-change tail) | ✗ (gap: 17 % late vs raster geodesic) | ✗ not applicable; ≥ 7–10 % median late vs the G8 upper bound | ✓ 0 | **no** |
| G8 | ✗ 14/17 (LB 8 tails 20–29 %) | ✓ | ✗ not applicable | ✓ 0 | **no** |
| G16 | ✗ 14/17 (LB 8 tails 17–21 %) | ✓ | not run | — | **no** |
| HY | ✗ 16/17 (LB 8 at 45°: p95 16.1 %) | ✓ | ✗ not applicable | ✓ 0 | **no** |

**What the evidence does establish**
- **Level set:** the only scheme that converges at a consistent order (p ≈ 1.3–2.3) on the exact cases.
  At **15 m** it passes every code-verification case with a wide margin (worst median 1.67 %, worst p95
  4.0 %), and its mosaic error bound falls to ≈ 3.5 %. Its weaknesses are concentrated at 30 m:
  - very elongated fires;
  - one-cell gaps (late behind the gap);
  - fuel-speed contrasts (first-order).
- **Graph schemes:** exact at barriers and never early, but their error does not converge. The
  LB 8 tail error is built into the stencil (it does not shrink at radius 8), and graph paths cannot turn
  mid-edge under changing wind.
- **Hybrid:** the best 30 m code-verification record (16/17, failing only the LB 8 / 45° tail) and
  passes barriers. Its cost is a level-set run plus a graph run, and it inherits the graph's
  initial-raster bias.

**Remaining trade-off, for the owner (D1 stays open).** These options are not recommendations, because
none meets the criteria as registered:
1. **Level set at 15 m** (30 m inputs resampled to 15 m; the finer grid adds no data, only numerical
   accuracy). Strongest verification evidence (convergent; passes A at 15 m). Costs ~5× a 30 m run
   (measured 84 s vs 16 s for the 17 cases). Barriers at 15 m and the mosaic at 15 m against the
   upper bound (~3.5 %) still need a formal check under the same criteria.
2. **Hybrid at 30 m**, accepting the documented LB 8 tail (16 % p95 at 45°; LB 8 corresponds to an
   effective midflame wind of ≥ 20 mi/h). This needs an explicit owner decision to relax a
   pre-registered criterion for LB 8 only. It would not be a finding of this verification.
3. Changing the physics to suit the numerics (e.g. capping LB lower) is **not** advised.

Both 1 and 2 would need a short pre-registered confirmation run before M1b.

## D1 decision (owner, 2026-10-24)

The owner chose option 2: **hybrid at 30 m**, relaxing the pre-registered criterion for the LB 8 cases only.
What this means, and what it does not:
- It is a **decision**, not a verification result. M1a-3 stands as written: HY failed 1/17 exact cases
  (LB 8 at 45°: median 2.07 %, p95 16.1 %). That number is reported wherever HY results are shown.
- Scope of the relaxation: cases where LB reaches the cap of 8 (effective midflame wind ≥ ~20 mi/h).
  Every other criterion (the 16 other exact cases, barriers, never-early) keeps its registered limit.
- Consequence for later stages: on validation fires, hours with LB = 8 are flagged, and the
  validation report shows errors split by LB < 8 vs LB = 8, so the known numerical tail is not
  mistaken for model skill or model failure.
- Still required before M1b: a short confirmation run of HY at 30 m with criteria fixed beforehand
  (the heterogeneous mosaic against the G8 upper bound and the lower bound, and the barrier fixtures on
  the real cell size), and the HY cost per cell for the M1b/M2 budget.

## M0 on the build Mac

Not run: there is no route from this session to the Mac. The cloud re-run was identical (3/32
answered). Details in `M0_RESULTS.md`.

## Tests

`uv run pytest -q`: **88 passed** (89 s) on the cloud container [verified]. New in M1a:
`test_levelset.py` (19 tests: analytic accuracy for ENO2/WENO5, Mode A, walls, gap, contrast, viscosity,
determinism), `test_wind_parameterisation.py` (8 tests, D3), the LB tests in
`test_observed_and_inputs.py`, and the exact large-stencil criterion-1 test in `test_stencil.py`. All
earlier fixtures still pass. The bake-off itself is a script (`python -m firepath.bakeoff`); its JSON
outputs are committed under `validation/`.

## Still open (M1a not complete)

- **D1 (owner):** choose between the options in "M1a-3 → Verdict", or ask for more work. Either option
  needs a short pre-registered confirmation run (barriers and mosaic at the chosen resolution) before M1b.
- Level-set barrier accuracy at one-cell gaps (17 % late at 30 m) and first-order error at fuel contrasts:
  known, quantified, not solved. A cut-cell or sub-cell barrier treatment would be the next step if the
  level set is chosen at 30 m.
- Standard cases not yet run: slope ("Valley"; needs the slope-plane geometry) and a four-fuel quadrant
  (no independent exact solution implemented; the half-plane refraction case covers the single-interface
  physics).
- Full Rothermel/SB40 fuel table (E1, E9–E11) with tests against pyretechnics and GTR-153 values.
- WAF crown-fill definition (E11): secondary sources give f = CC·CR/3, which needs CBH. Primary GTR-266
  check pending.
- Full-text checks of Finney 1998 / Anderson 1983 / Andrews 2013 (blocked from this session).
- **M0 on the Mac** (`make probe`): gates M1b.

## M1a-4: HY confirmation at 30 m (2026-10-24)

Pre-registration: `validation/M1A4_PREREGISTRATION.md`, committed before the run. Results:
`validation/m1a4_C.json` (runner `firepath.confirm`).

**Pre-registered verdict: FAIL.** HY at 30 m against LS at 7.5 m on the mosaic:

| Case | median e | p95 e | signed median | HY later than ref. | ref. uncertainty u (median / p95) | lower-bound violations |
|---|---|---|---|---|---|---|
| iso | 5.23 % ✗ | 13.8 % ✗ | −5.2 % | 0 % of cells | 1.6 / 3.5 % | 0 |
| lb2 | 5.05 % ✗ | 13.7 % ✗ | −5.0 % | 4 % | 1.4 / 3.1 % | 0 |
| lb4 | 3.00 % ✓ | 15.2 % ✗ | −2.9 % | 19 % | 0.8 / 2.9 % | 0 |

HY cost in the Python reference: 2.0–2.6 ms per cell at 30 m (single thread, cloud container).

**Post-hoc diagnostic (not pre-registered; `validation/m1a4_diag_upper_bound.json`).** In a static
field, a graph path with exactly integrated edge times is a path the fire can physically follow, so
G8 is an **upper bound** on the true arrival time for its geometry. Comparing with G8 at 7.5 m:

| Case | LS 7.5 m above the upper bound | LS 7.5 m − G8 7.5 m (median / p95) | HY 30 m − G8 7.5 m (median / p95) | HY above the upper bound |
|---|---|---|---|---|
| iso | **99.9 %** of cells | +2.9 / +5.7 % | −2.7 / −0.5 % | 0.8 % |
| lb2 | **99.8 %** | +2.2 / +5.3 % | −2.3 / +1.8 % | 28 % |
| lb4 | 77 % | +1.7 / +4.7 % | −0.5 / +3.8 % | 38 % |

What this shows, and what it does not:
- The reference is **provably late** (≥ 2–3 % median) on almost every cell, so about half of the
  measured −5 % gap is reference error. The test cannot attribute the gap to HY. Choosing LS 7.5 m
  as the sole reference was a design error in M1A4_PREREGISTRATION: M1a-3 had already shown LS to be
  late at fuel contrasts.
- HY 30 m lies between the hard lower bound (0 violations) and the G8 7.5 m upper bound on 99 % of
  cells in iso. Its true error there is bracketed but not measured: it lies between −2.7 % (median
  distance to the upper bound) and the unknown distance from the upper bound to the truth.
- At lb2/lb4, 28–38 % of HY cells sit above the upper bound, by up to ≈ 4 % (p95). That error is real
  and late.
- The criteria are not changed after the run. Under the decision rule, D1 confirmation goes back to the
  owner.

**Recommended next step (M1a-5, to pre-register first):** a bracketing reference that does not rely on
one scheme. Upper bound: G8 and G16 at 3.75 m. Estimate: LS at 15 / 7.5 / 3.75 m with Richardson where
applicable. HY 30 m is judged against the bracket. Estimated cost: ≈ 1 h per case in the background.

## M1a-5: HY at 30 m against a bracketing reference (2026-10-25)

Pre-registration: `validation/M1A5_PREREGISTRATION.md`, committed before the run. Results:
`validation/m1a5.json` (runner `firepath.bracket`; solves cached in `data/interim/m1a5/`, not committed).

**Pre-registered verdict: INCONCLUSIVE** (all three cases). Richardson's assumptions held on too few
cells for the LS estimate to serve as the reference (requirement: ≥ 50 % in the "estimate" category):

| Case | reference: estimate / bound / fallback | HY error vs R: median / p95 | signed median | HY provably late (share; p95 amount) | lower-bound violations |
|---|---|---|---|---|---|
| iso | 28 / 25 / 47 % | 2.44 / 8.90 % | −2.4 % | 2 %; 1.0 % | 0 |
| lb2 | 13 / 55 / 32 % | 2.69 / 10.5 % | −2.2 % | 30 %; 3.6 % | 0 |
| lb4 | 8 / 29 / 64 % | 2.23 / 14.9 % | −0.3 % | 43 %; 5.9 % | 0 |

What the numbers do establish:
- The level set at 15 / 7.5 / 3.75 m does not converge monotonically at most mosaic cells, or its
  extrapolation exceeds the feasible-path upper bound. So no fine-grid estimate of the true arrival
  exists for this mosaic. The reference is in effect the 3.75 m upper bound U.
- Against U, HY at 30 m has median |error| 2.2–2.7 % in all cases. Its p95 is 8.9 % (iso),
  10.5 % (lb2) and 14.9 % (lb4).
- Hard one-sided evidence: HY is **never earlier** than the physical lower bound, and is **provably late**
  (above U) by at most 1.0 / 3.6 / 5.9 % at the 95th percentile.
- Where HY is earlier than U, the true value lies somewhere between, so that part of the "error" is
  partly the bound's own gap and not necessarily HY's.

Under the decision rule, D1 confirmation returns to the owner: HY at 30 m only by an explicit decision,
documented as "not verified on the heterogeneous mosaic; bracketed: never early, late ≤ 6 % (p95)".
