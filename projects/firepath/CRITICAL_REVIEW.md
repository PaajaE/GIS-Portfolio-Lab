# FirePath — critical review before implementation

> Date: 2026-10-09. Scope: the plan committed as `f85b51b` (`PLAN.md` v1, `METHOD.md` draft). The task named
> "METHOD.md §5–8 and §12"; in v1 those equations lived in **PLAN.md §5–8 and §12** (METHOD.md was a stub).
> References below are to PLAN v1 unless marked otherwise. The revised specification is now in `METHOD.md`.
>
> Evidence labels: **[verified]**: checked here by computation, a test or a probe, with the evidence named;
> **[sourced]**: from a primary or official source, or an independent implementation, read during this
> review but not re-derived; **[hypothesis]**: an assumption or a recalled equation that still needs a
> source check or an experiment. The primary USFS PDFs (Rothermel 1972, Albini 1976, Anderson 1983,
> Andrews 2012/2018, Scott & Burgan 2005) were **not reachable** from this session (egress 403). Equation
> rows are cross-checked against the open implementation *pyretechnics* 2026.8.10 (PyPI, EPL-2.0, sdist
> sha256 `37aa5694…c665ba66`, read only, not installed or copied). Agreement with it is agreement with
> another implementation, not proof from the primary source.

## Corrections after M1a (2026-10-09; details in `M1A_RESULTS.md`)

- **P0-3, magnitude corrected.** The original text said that for fine fuels B ≈ 0.4–0.6, so a_w = 2 would
  give 15–28 mi/h of effective wind. That was wrong. B = 0.02526 σ^0.54 is ≈ 1.5 for σ = 2000 ft⁻¹ (≈ 0.7
  for σ = 500), so v1's a_w moves the effective wind by a_w^(1/B) ≈ a_w^0.65 for fine fuels
  (`test_v1_a_w_inside_phi_w_distorts_shape`). The finding stands: the shape change is not zero, and
  its size depends on the fuel model, so a_w had no single interpretation. The severity is lower than
  stated.
- **P0-2, source.** The FARSITE report (Finney 1998, RMRS-RP-4) gives the m/s form for the *effective*
  midflame wind, capped at 8 (search excerpts of the primary document). The BehavePlus source code uses
  1 + 0.25 U_E (mi/h). Its attribution to Rothermel (1991) in this review was not confirmed.
- **P0-1.** The M1a bake-off ran. No candidate passed all pre-declared criteria (see M1A_RESULTS).

## Summary

| Rank | ID | Finding (PLAN v1 reference) | Status after this task |
|---|---|---|---|
| **P0** | P0-1 | 16-neighbour Dijkstra cannot represent elongated ellipses (§6.4). The "2.7 %" error holds only for isotropic spread; at LB 4 the head-direction error reaches 86 % | **open: owner decision D1** (propagation scheme), plus an M1a bake-off |
| **P0** | P0-2 | Length-to-breadth relation (§6.2): coefficients are the m/s form but labelled mi/h. That is a 2.24× error in the exponent (LB 8 instead of 2.8 at 10 mi/h) | units fixed **[verified]**; which LB relation to use is **open: decision D2** |
| **P0** | P0-3 | Wind multiplier `a_w` inside the vector sum, followed by effective-wind inversion with the *unmodified* wind function (§6.1, §6.7). `a_w` then silently changes the ellipse shape | **open: decision D3** (recommend a wind-speed multiplier) |
| **P0** | P0-4 | Edge-arrival function and hourly integration not defined (§6.3, §6.5) | **resolved**: specification + FIFO proof + fixtures **[verified]** |
| **P0** | P0-5 | Initial-perimeter (Mode A) semantics undefined (§6.6). Interior barrier cells could act as sources (lake-hopping) | **resolved**: specification + 6 fixtures **[verified]** |
| **P0** | P0-6 | Barrier rule "any crossed cell" leaks through one-cell diagonal walls: (1,1) and (3,1)-type moves pass through grid vertices (§6.3) | **resolved**: vertex rule + full-propagation fixture **[verified]** |
| **P0** | P0-7 | Fuel-moisture inputs undefined (§4, §6.7) | **specified and tested** (mapping). The live-moisture value is still a [hypothesis] (P1-7) |
| **P0** | P0-8 | Data feasibility unverified on the build Mac (§0, M0) | **open**: probe implemented and run **only in the cloud session**. The Mac run is pending |
| P1 | P1-1 | Wind limit (§6.1 "cap at the Rothermel/Andrews limit") conflates two different rules | decision in METHOD (Andrews et al. 2013 cap); primary text to verify |
| P1 | P1-2 | Rothermel ROS is along the slope surface, but edges are horizontal (§6.3) | specification: planar slope per cell, horizontal-speed conversion; fixture in M1a |
| P1 | P1-3 | Sheltered WAF needs a crown-fill definition; v1 said CBH is "not used" (§4) | unresolved: source check (GTR-266) |
| P1 | P1-4 | Under changing wind, graph paths bend only at nodes (§6.5) | measured < 5 % at LB 1.5 with radius 4 **[verified]**; larger LB goes into the bake-off |
| P1 | P1-5 | No procedure for non-nested / corrected perimeters (§8–9) | specified + implemented + synthetic tests **[verified]** |
| P1 | P1-6 | The interval-censored primary metric is lenient when intervals are wide (§8) | secondary measures and a pre-declared width split added |
| P1 | P1-7 | Live fuel moisture has no data source (§4) | [hypothesis] L1 for pre-monsoon fires. Smallest check: NFMD samples |
| P1 | P1-8 | Identifiability: `k`, wind multiplier and `m` are confounded (§8) | expectations pre-declared; profile checks |
| P1 | P1-9 | HRRR analysis → interval assignment ambiguous (§6.5) | decision: nearest-analysis, centred intervals |
| P1 | P1-10 | 10 m → 20 ft factor 1.15 cited as "standard" without a source (§5) | [hypothesis]: source check in M1a |
| P1 | P1-11 | Level-set option (if chosen) uses a front-normal speed: pyretechnics applies the ray-speed expression to the front normal, which is not the support function of the ellipse | equation must be audited if D1 = level set |
| P1 | P1-12 | v1 run-time estimates were guesses (§12, §16) | Python reference measured: ≈ 75 µs/cell (radius 2), ≈ 1.6 ms/cell (radius 8) on the cloud container **[verified]** |
| P2 | P2-1 | Cell-centre rasterization drops perimeter features narrower than about one cell | documented + fixture **[verified]** |
| P2 | P2-2 | HRRR on S3 answered `NoSuchBucket` intermittently (1 of 3 identical requests) | retries in probe/harvest **[verified]** |
| P2 | P2-3 | Mendeley NIROPS dataset licence unknown | probe records it on the Mac |
| P2 | P2-4 | The plan's "artefact check 16 vs 32 stencil" (§10) is insufficient, since both are biased | replaced by the bake-off criteria |

## P0 findings in detail

### P0-1: stencil angular error grows with fire elongation [verified]

*Claim in v1 (§6.4):* "16-neighbour 2.7 %… The error grows for elongated ellipses. Mitigation: … the default
stencil is the smallest that keeps the error < 3 % at LB ≤ 4."

*Analysis.* In a homogeneous medium, the set a label-setting (Dijkstra) search can reach in unit time is
the convex hull of the points r(φ_k)·û(φ_k) over the stencil directions φ_k, where r is the ray speed from
the rear focus (METHOD E8). The true set is the ellipse. The relative arrival-time error in a direction is
ρ_true/ρ_hull − 1. For an elongated ellipse the ray speed is sharply peaked at the head. Two stencil
directions on either side of the wind direction both "see" much lower speeds, and their chord cuts deep
inside the ellipse. `firepath.stencil.stencil_error` computes this exactly. **The full-propagation fixture
reproduces the prediction to 0.1 %** (`test_uniform_wind_ellipse_vs_independent_graph_and_continuum`;
measured / predicted forward error, wind 13°: radius 2, LB 2: 20.5 / 20.5 %; radius 2, LB 4:
86.5 / 86.5 %; radius 4, LB 2: 5.5 / 5.5 %; radius 8, LB 4: 4.4 / 4.4 %).

Worst forward relative arrival error over wind angles 0–45° (asymptotic, %):

| Stencil (Chebyshev radius → directions) | LB 1.5 | LB 2 | LB 3 | LB 4 | LB 6 | LB 8 |
|---|---|---|---|---|---|---|
| 1 → 8 | 32.4 | 61.5 | 144 | 260 | 589 | 1050 |
| 2 → 16 (v1 default) | 10.8 | 20.5 | 48.0 | 86.5 | 196 | 350 |
| 3 → 32 | 5.1 | 9.8 | 22.9 | 41.2 | 93.4 | 167 |
| 4 → 48 | 3.0 | 5.6 | 13.2 | 23.8 | 53.9 | 96.0 |
| 8 → 176 | 0.8 | 1.4 | 3.4 | 6.1 | 13.8 | 24.7 |
| 12 → 368 | 0.3 | 0.6 | 1.5 | 2.7 | 6.2 | 11.0 |

With the corrected LB relation (P0-2), effective midflame winds of 5–15 mi/h give LB ≈ 1.6–5.0. The v1
scheme would therefore err by 20–120 % in the head direction, depending on the wind angle relative to the
grid. *Consequence if unresolved:* the arrival times would be dominated by a **grid-orientation artefact**.
Calibration would absorb it into `k` and the wind multiplier, which would then be fire- and wind-angle
specific, and validation errors would be uninterpretable. This is exactly the "artefact credited as a
physical driver" failure the project lessons warn against.

*Options (published approaches; none is adopted silently):*
- **A. Large-stencil label-setting** (radius 8–12). This keeps the specification in METHOD (exact FIFO,
  deterministic Dijkstra). Cost per cell is ×40–100 vs radius 2 (measured: 1.6 ms vs 75 µs per cell in
  the Python reference). Fronts can bend only at nodes 6–9 cells apart, which smears fuel heterogeneity.
  The error is still 11–25 % at LB 8.
- **B. Eulerian level set** with explicit time stepping (the ELMFIRE lineage; *pyretechnics* implements it
  with a superbee flux limiter [sourced]). Time-varying wind is natural and there is no hard angular
  limit. Costs: numerical diffusion rounds the head, a CFL time step is needed, and the front-normal speed
  needs its own equation audit (P1-11). The Dijkstra/FIFO specification would be replaced by a
  time-stepping specification. Rust still owns cell state, the update and the parallel scenarios.
- **C. Lower the elongation** (cap LB at 2–3 or use 1 + 0.25 U). This changes the physics to suit the
  numerics, and at LB 3 the error is still 48 % with 16 neighbours. **Not recommended.**

*Recommendation, decision D1:* approve an **M1a bake-off** between A (radius 8) and B, on analytic
fixtures only. The acceptance criteria are fixed now: (1) worst forward arrival error ≤ 5 % for LB ≤ 4 and
≤ 10 % at the LB cap, over wind angles 0–45° in 2.5° steps; (2) spread of burned area across wind angles
≤ 3 %; (3) Minkowski (wind-change) fixture error ≤ 5 %; (4) barrier and initial-perimeter fixtures
pass; (5) the measured cost per 10⁶ cells × 24 h. Among the schemes that pass 1–4, the cheapest wins.
If none passes, report that and stop before M1b.

### P0-2: LB coefficients are in m/s, not mi/h [verified units / sourced form]

v1 §6.2 wrote `LB = 0.936·e^(0.2566·U) + 0.461·e^(−0.1548·U) − 0.397 (U in mi/h)`. The coefficients
0.2566 and 0.1548 divided by 2.2369 (m/s → mi/h) give 0.1147 and 0.0692, the mi/h coefficients used by
pyretechnics in its "behave" mode [sourced]. `test_anderson_units_mph_vs_ms_forms_agree` confirms the two
forms agree within 0.5 % (coefficient rounding). With mi/h input the v1 formula gives LB = 8 (cap) at
10 mi/h instead of 2.78 (`test_plan_v1_unit_error_is_large`). *Consequence:* far too elongated fires,
which would also amplify P0-1. The remaining choice between the Anderson-type relation (FARSITE/BehavePlus
lineage) and 1 + 0.25 U (attributed to Rothermel 1991) is **decision D2**. Recommendation: the mi/h
Anderson-type form with a cap of 8 as the default, and 1 + 0.25 U as a sensitivity. Before calibration,
verify which relation BehavePlus/Andrews (2018) document [hypothesis until checked].

### P0-3: the wind multiplier changes shape through the effective-wind inversion [verified algebra]

v1: `φ_E = |a_w φ_w ê_w + a_s φ_s ê_s|`, then `U_E = φ_w⁻¹(φ_E)` with the published φ_w = C U^B (β/β_op)^−E.
For wind only, `U_E = a_w^{1/B} U`. With B ≈ 0.4–0.6 (fine fuels), `a_w = 2` turns 5 mi/h into
≈ 15–28 mi/h of "effective" wind for the LB calculation. So `a_w` scales the head ROS by `a_w` but the
ellipse shape by a much larger factor. *Consequence:* a calibrated `a_w` would mix two effects and could
not be interpreted as a wind sensitivity. Options: (a) **wind-speed multiplier `a_U` on the 20 ft wind
before WAF**, which acts consistently through φ_w and LB with published functions only; (b) a multiplier
on φ_w with inversion of the *modified* function (wind-only LB unchanged; a FirePath-specific construction).
*Recommendation, decision D3:* (a). `a_U` is then the same knob as the wind-speed scenario factor, so the
scenarios are stated relative to the calibrated `a_U`. The published vector combination (E4), the
effective-wind inversion (E5) and LB(U_E) (E7) are mutually consistent when no multiplier sits inside φ_w.
Multipliers outside the bracket (`k`, `g`) do not affect the shape. `a_s` scaling φ_s before the vector sum
makes the slope-equivalent wind grow with `a_s`, which is the intended behaviour of a slope sensitivity.

### P0-4: edge-arrival function, resolved

METHOD "Propagation §P1–P4" defines A_e(t_u) as the solution of the progress equation along the
centre-to-centre segment, with piecewise-constant speed in (cell, interval). It gives the event-driven
algorithm, proves FIFO (A_e strictly increasing, A_e(t) > t), and lists what FIFO does *not* establish.
Tests: comparison with independent fine time-marching on random fields (6 intervals, random speeds and
ellipses; |Δ| ≤ 2·10⁻³ min); strict FIFO on 20 random fields × 16 offsets × 400 departure times;
departure exactly on an interval boundary; two 1-D strips with different fuels where the wind change
falls inside an edge, including one edge that contains both the interval change and the fuel change
(hand-computed arrivals, |Δ| ≤ 10⁻⁹ min).

### P0-5: initial perimeter, resolved

METHOD "Initial perimeter (Mode A)" defines the source set, zero-cost traversal of inside burnable cells,
inside barriers, and the equivalence of seeding all inside cells vs boundary cells only. Fixtures:
- **Large polygon** (disc radius 15.3 cells) vs Shapely distance. Every arrival ≥ distance to the
  raster interior. Mean signed error vs the true polygon distance, 5–12 cells out: **−0.17 cells**
  (95th percentile |error| 0.43 cells). Centre-sourcing would bias it by about +0.5 cell (analytic
  argument, not run).
- **One-cell protrusion:** it is a source, and the arrival 2.5 cells beyond the tip is exact.
- **Sub-cell protrusion:** it is lost by rasterization (documented).
- **Lake straddling the boundary:** not a source; the arrival is lower-bounded by the geodesic around
  the lake.
- **Wall next to the perimeter:** knight moves cannot jump it.
- **Boundary-only seeding:** gives bit-identical results to seeding all inside cells.

### P0-6: barrier leak through grid vertices, resolved

A segment for offset (dr, dc) passes through a grid vertex iff dr and dc are both odd. The two cells
touching that vertex meet the segment in a single point (zero length), so the v1 rule never inspected them.
A (1,1) move between two diagonal barrier cells crosses a one-cell-thick diagonal wall. The new rule (METHOD
B3) also invalidates a transition when **both** side cells at a crossed vertex are barriers. Exact rational
traversal tables are tested for (0,1), (1,1), (1,2), (1,3) and invariants for all offsets up to radius 4. A
full-propagation fixture with an anti-diagonal wall, at radius 1/2/3, keeps the far side unreached. A wall
with a gap is lower-bounded by the Shapely visibility-graph geodesic.

### P0-7: fuel moisture, specified

Mapping (METHOD M1–M5, `firepath.moisture`, tested): dead 100-h = gridMET fm100 (median over the evaluation
window, per fire); 10-h = fm100 − 1; 1-h = fm100 − 2 (floor 2 %). These are the fixed offsets of the
Scott & Burgan dead scenarios, so fm100 = 5/8/11/14 reproduce D1–D4 exactly. This is a FirePath
approximation, not a published mapping. Live herbaceous and woody moisture come from a pre-declared Scott &
Burgan live scenario: **L1 (30/60 %) for these pre-monsoon (April–June) Arizona fires**, which is a
[hypothesis]. Dynamic models transfer live herbaceous load by `clamp((120 − M_lh)/90, 0, 1)` [sourced:
consistent with the IFTDSS table and pyretechnics]. `m` multiplies the three dead classes only. It is fixed
at 1 in calibration and is a scenario variable. Identifiability: see P1-8.

### P0-8: data feasibility, open

`src/firepath/probe.py` (standard library only, non-destructive) was run **in this cloud session only**:
32 endpoint checks: 3 answered (two HRRR checks on AWS S3, PyPI); 28 were refused by the session's egress proxy
(`Tunnel connection failed: 403`); gridMET THREDDS timed out. The NIROPS crawler and the NIFC service query
could not run. The crawler is tested against a local fake directory tree. **None of this says anything
about the build Mac.** Details are in `M0_RESULTS.md`. *Consequence:* M1b (first data slice) cannot start;
M1a (no data) can.

## P1 findings (selected detail)

- **P1-1 wind limit.** The original Rothermel limit caps the effective wind at 0.9·I_R (pyretechnics
  implements it as an option [sourced]). Andrews, Cruz & Rothermel (2013) found both the original and a
  revised limit too restrictive and recommend limiting the **rate of spread to the effective midflame wind
  speed** instead [sourced: abstract]. Recommendation: Andrews 2013 cap as the default (R_head ≤ U_E, same
  units), the original limit as a sensitivity. Verify the full text in M1a.
- **P1-2 slope-plane geometry.** Rothermel's spread rate and ellipse are on the slope surface;
  pyretechnics projects wind and slope vectors onto the slope-tangential plane [sourced]. Specification
  (METHOD G1): per cell, a planar surface with gradient ∇z. A horizontal direction d maps to the surface
  direction (d, ∇z·d)/√(1+(∇z·d)²). The ray speed is evaluated at the angle on the surface. The horizontal
  speed is s_h = s_surface / √(1 + (∇z·d)²). On a 30° slope that is 15 % slower up- and downslope than a
  horizontal treatment. Fixture: inclined plane with an analytic ellipse (M1a).
- **P1-3 sheltered WAF.** Andrews (2012) gives unsheltered `1.83/ln((20+0.36H)/(0.13H))` and sheltered
  `0.555/(√(f·H_c)·ln((20+0.36H_c)/(0.13H_c)))` (H in ft) [sourced via pyretechnics]. pyretechnics uses
  crown-fill portion f = CC/3 with crown ratio 1, and "sheltered if f ≥ 0.05 and H_c ≥ 6 ft". Whether
  Andrews (2012) defines f with a crown ratio (which would need LANDFIRE CBH) is **unresolved**. Smallest
  check: read GTR-266 equations 2–6.
- **P1-4 changing wind.** The continuum reference is the Minkowski sum of the two hourly ellipses (support
  functions). On it, the graph (radius 4, LB 1.5, wind turning 90°) stays ≥ the continuum and within 5 %
  [verified]. Larger LB is part of the bake-off.
- **P1-6 metric leniency.** A 36 h observation gap scores any arrival within those 36 h as zero error.
  Added (pre-declared, before any result): the distribution of interval widths per fire; signed
  early/inside/late shares; boundary timing error at each observed perimeter (T_model − t_k at points
  sampled every 30 m); modelled/observed area ratio per step; and the primary metric recomputed on cells
  with interval width ≤ 30 h as a reported split, not a replacement.
- **P1-7 live moisture.** Smallest experiment: National Fuel Moisture Database samples within 50 km and
  ±14 days of each ignition (if reachable from the Mac). Otherwise keep L1 and run L2 as a scenario.
- **P1-8 identifiability (pre-declared expectations).** Daily perimeters constrain the integrated
  distance per interval in several directions. Expected: `k` well identified; `k`–`a_U` correlated on
  wind-driven days (R ∝ k·a_U^B), separated partly by flank/back spread and by days with different wind
  speeds; `a_s` and `g_timber/g_grass` weak unless the calibration fires burn steep or mixed-fuel terrain
  under contrasting winds; `m` confounded with `k`, hence fixed. Profiles decide. A flat profile means
  "not identifiable", and the parameter is fixed at 1.
- **P1-9 HRRR timing.** An analysis is valid at the top of the hour. Each analysis applies on
  [H − 30 min, H + 30 min) (nearest analysis), so the first interval starts at ignition − 24 h.
- **P1-10 10 m → 20 ft.** v1 called "÷ 1.15" standard without a source. [hypothesis] until a primary
  reference is found (M1a). The alternative is a log-profile conversion with a stated roughness.
- **P1-11 level-set normal speed.** For a front with outward normal n, the Huygens envelope of
  focus-anchored ellipses moves at the support function h(n) = a e (n·ŵ) + √(a²(n·ŵ)² + b²(n·ŵ⊥)²)
  (a = R/(1+e), b = a√(1−e²)), not at the ray speed r(∠n). pyretechnics applies (1−e)/(1−e cos w) to the
  normal direction [sourced: code]. If D1 = level set, this choice must be tested against the analytic
  ellipse in the bake-off.

## Decision list for the project owner (only items that need approval)

| ID | Decision | Recommendation | Why it needs you |
|---|---|---|---|
| **D1** | Propagation scheme | Run the M1a bake-off (large-stencil Dijkstra vs Eulerian level set) under the criteria above, and accept the winner even if it is the level set | It changes the algorithm the plan promised ("Dijkstra/fast-marching") and the Rust story's details |
| **D2** | Length-to-breadth relation | Anderson-type (mi/h form, cap 8) as the default, 1 + 0.25 U as a sensitivity, both verified at the primary source in M1a | A physics choice that strongly affects results |
| **D3** | Wind sensitivity parameter | Wind-speed multiplier `a_U` before WAF (replaces `a_w` on φ_w) | It changes the spec's named parameter "wind sensitivity" |
| D4 | Fire set and split | Unchanged from v1 (pending the Mac screening) | Already open as Q1 |
| D5 | Run M0 on the Mac (or allow the hosts here) | Run `make probe` on the Mac and commit `provenance/probe_build-mac.json` | Only you can run it there |
| D6 | Credentials | FIRMS MAP_KEY / Synoptic token stay optional; nothing registered | Accounts are yours |
| D7 | Publication / site structure | Unchanged: no Pages or root changes until M9 and your approval | Shared structure |
