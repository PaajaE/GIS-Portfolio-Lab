# FirePath — M1a results (mathematical specification and analytic fixtures)

> Date: 2026-10-09. Scope: decisions D1–D3 from `CRITICAL_REVIEW.md`, analytic fixtures only, no data.
> Everything here comes from the pure-Python/NumPy reference implementations on the cloud container
> (Linux x86_64, 4 vCPU). Times are **not** Rust estimates. Evidence labels as in CRITICAL_REVIEW:
> [verified] by computation or test here, [sourced] from documents (here mostly search-engine excerpts,
> because the primary PDFs were blocked from this session), [hypothesis].

## Summary

| Decision | Outcome |
|---|---|
| **D1 propagation scheme** | **Not decided: no candidate passed all pre-declared criteria.** Under the rule fixed in CRITICAL_REVIEW, the decision returns to the owner and M1b does not start. The WENO5 level set came closest (it passes criteria 1 and 3, misses criterion 2 at LB 8 by 0.5 pp, and fails the barrier fixtures). Radius-8 label-setting fails criteria 1–3 and passes the barriers |
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

- **D1:** owner decision after the two experiments above. M1b and the Rust kernel depend on it.
- Full Rothermel/SB40 fuel table (E1, E9–E11) with tests against pyretechnics and GTR-153 values. Not
  started in this session.
- WAF crown-fill definition (E11) and full-text checks of Finney 1998 / Anderson 1983 / Andrews 2013:
  blocked here, to do on the Mac.
- Inclined-plane (slope-plane geometry) fixture.
- **M0 on the Mac** (`make probe`), which gates M1b.
