# FirePath — Method

> Status: **specification, revision 3 (2026-10-09), after M1a (`M1A_RESULTS.md`).** Spec section: §7.
> Revision 3 changes: E7 decided (D2), E12 documented, `a_u` adopted provisionally (D3) with a separate
> input-uncertainty factor λ, and the propagation-scheme status after the bake-off (D1 still open).
> No model has been run on real data. Where a choice is still open (decisions D1–D3 in
> `CRITICAL_REVIEW.md`), both options are written down and nothing is silently adopted. The labels
> **[published]** (an equation from the cited literature) and **[FirePath]** (an approximation or choice
> made for this project) separate the two throughout.

## Problem / decision
**Question (spec §7):** can a lightweight, reproducible rate-of-spread / arrival-time model reconstruct
historical wildfire growth well enough to explore alternative fuel, terrain and wind scenarios?

**Who acts:** fire-management and fuels planners, and county emergency managers doing after-action or
planning analysis; analysts studying where a simple surface-spread model works and fails. **Decision
supported:** how much plausible changes in wind, fuel moisture, fuels or slope effect shift *when* a fire
reaches a road or community, and whether that conclusion is robust. Wording: a modelled reconstruction
under stated inputs, **not a forecast, not FARSITE/FlamMap, not an operational system**. Network results
are *exposure* in *network travel time*, not risk.

## Study area and analytical unit
Proposed pool and split: PLAN §2 (USFS Southwestern Region, temporal holdout: calibration Bush 2020, Mangum
2020, Telegraph 2021; validation Tunnel 2022, Pipeline 2022). Pending screening on the build Mac
(`M0_RESULTS.md`). Unit of analysis: 30 m cell (arrival time). Reporting units: fire × observed time step;
road segment; census block.

## Data and rationale
PLAN §4. Established: HRRR 10 m U/V on AWS are grid-relative (GRIB2 flag, verified). Other sources are
unprobed from the build Mac (`M0_RESULTS.md`).

## Harmonization
- **CRS:** NAD83 / UTM 12N (EPSG:26912) per Arizona fire. Measured projection factors: EPSG:5070 has
  ≈ ±0.7–0.9 % anisotropic scale and ≈ 1° angular distortion at the fires; UTM ≤ 0.04 %.
- **Grid:** 30 m. Categorical fields use nearest-neighbour resampling. The DEM is averaged to 30 m
  before slope. HRRR U/V are rotated grid → earth → UTM, then interpolated (PLAN §5).
- **Time:** all times in UTC minutes since a fire reference t0. Weather is piecewise constant on intervals
  I_h = [T_h, T_{h+1}). An HRRR analysis valid at H applies on [H − 30 min, H + 30 min) (nearest analysis)
  **[FirePath]**. The first interval is open to the left and the last to the right.
- **Leakage rules:** PLAN §3. The LANDFIRE version precedes each fire. Observed perimeters enter only as
  initial conditions at t ≤ t0.

---

## Spread-rate model (equation audit)

Units: the Rothermel equations are evaluated in their native English units (ft, lb, BTU, min). Inputs and
outputs are converted at the boundary (m/min), and the conversions are tested. Every row below has an
implementation test in M1a. Rows marked "cross-checked" were compared, line by line, with the
independent open implementation *pyretechnics* 2026.8.10 (read only), **not** with the primary PDFs, which
were unreachable from the review session.

| # | Component | Equation | Source | Units / assumptions | Implementation test (M1a) |
|---|---|---|---|---|---|
| E1 | No-wind, no-slope ROS | R0 = I_R ξ / (ρ_b ε Q_ig), with I_R = Γ′ Σ w_n h η_M η_s (by dead/live category), Γ′ = Γ′_max (β/β_op)^A exp[A(1 − β/β_op)], Γ′_max = σ^1.5/(495 + 0.0594 σ^1.5), A = 133 σ^−0.7913, β_op = 3.348 σ^−0.8189, ξ = exp[(0.792 + 0.681 σ^0.5)(β + 0.1)]/(192 + 0.2595 σ), ε = exp(−138/σ), Q_ig = 250 + 1116 M_f, η_s = 0.174 S_e^−0.19 | **[published]** Rothermel 1972; Albini 1976 (A, multi-class weights); compiled in Andrews 2018 (GTR-371); cross-checked: β_op, ξ, A comment | ft/min; homogeneous, continuous surface fuel bed; steady spread | R0 for all 40 SB models at D1–D4/L1–L4 vs pyretechnics (rel. 1e-6) and vs published GTR-153 values (chart precision) |
| E2 | Wind factor | φ_w = C U^B (β/β_op)^−E; C = 7.47 exp(−0.133 σ^0.55), B = 0.02526 σ^0.54, E = 0.715 exp(−3.59·10⁻⁴ σ) | **[published]** Rothermel 1972; cross-checked | U = midflame wind (ft/min) | closed-form values for 3 models |
| E3 | Slope factor | φ_s = 5.275 β^−0.3 tan²θ | **[published]** Rothermel 1972; cross-checked | θ = slope angle of the cell plane | closed form |
| E4 | Wind–slope combination | **φ⃗_E = φ_w ŵ + a_s φ_s ŝ** (vector sum; ŵ downwind, ŝ upslope, both in the slope plane); R_head = k·g(f)·R0·(1 + \|φ⃗_E\|); direction of max spread = φ⃗_E / \|φ⃗_E\| (upslope if φ_E = 0 and φ_s > 0) | **[published]** vector method (Rothermel 1983; Finney 1998; Andrews 2018); pyretechnics projects onto the slope plane. `k`, `g`, `a_s` are **[FirePath]** multipliers | dimensionless | aligned wind+slope reproduces R0(1+φ_w+φ_s); opposed gives \|φ_w − φ_s\| |
| E5 | Effective wind | U_E = φ_w⁻¹(\|φ⃗_E\|) = [\|φ⃗_E\| (β/β_op)^E / C]^(1/B), always with the **unmodified** published φ_w | **[published]**; cross-checked | ft/min | round trip φ_w(U_E) = φ_E |
| E6 | Wind / ROS limit | default **R_head ≤ max(U_E, k·g·R0)** (same units; the max() keeps the cap from falling below the no-wind ROS, a FirePath guard) | **[published]** Andrews, Cruz & Rothermel 2013 (abstract read; full text to verify). Original U_E ≤ 0.9 I_R kept as a sensitivity | — | both branches |
| E7 | Length-to-breadth | **D2 decided (rev 3):** LB = 0.936 e^(0.2566 U_E) + 0.461 e^(−0.1548 U_E) − 0.397, **U_E = effective midflame wind in m/s**, capped at 8 (≡ 0.1147 / 0.0692 per mi/h). Sensitivity: LB = 1 + 0.25 U_E (U_E in mi/h) | **[published]** Finney 1998 (RMRS-RP-4, FARSITE): Anderson (1983) relation, single ellipse, −0.397 added so that LB(0) = 1, cap 8 from Alexander (1985); m/s units and "effective midflame" read from search excerpts of the primary document (full text not opened; Anderson 1983 not accessed). Sensitivity relation: BehavePlus source code (`xfblib.cpp`) | dimensionless; U_E from E5 | `test_anderson_units_mph_vs_ms_forms_agree`, `test_lb_relations_at_reference_speeds` |
| E8 | Directional spread (ray speed from the ignition point at the rear focus) | e = √(LB² − 1)/LB; r(ψ) = R_head (1 − e)/(1 − e cos ψ), ψ = angle from the max-spread direction | **[published]** elliptical fire shape (Albini & Chase 1980 for e; Richards 1990; used as the travel-time norm by MTT, Finney 2002) | head r(0) = R_head; back (1−e)/(1+e)·R_head | `test_ellipse_basics`; uniform-wind fixture |
| E9 | Moisture damping and extinction | η_M = 1 − 2.59 r + 5.11 r² − 3.52 r³, r = min(M_f/M_x, 1), per category; live extinction M_x,live = max(M_x,dead, 2.9 W′(1 − M_f,dead/M_x,dead) − 0.226) | **[published]** Rothermel 1972; Albini 1976 [to cross-check] | fractions | η_M(0) = 1, η_M(1) = 0; extinction gives R0 = 0, so the cell becomes a barrier (static) |
| E10 | Dynamic fuel models | cured share T = clamp((120 − M_lh)/90, 0, 1) of the live herbaceous load moves to a dead herbaceous class with the live herbaceous SAV and the dead 1-h moisture | **[published]** Scott & Burgan 2005; consistent with the IFTDSS table and pyretechnics | M_lh in % | `test_dynamic_fuel_curing` |
| E11 | Wind adjustment factor | unsheltered WAF = 1.83/ln((20 + 0.36 H)/(0.13 H)), H = fuel bed depth (ft); sheltered WAF = 0.555/(√(f H_c) ln((20 + 0.36 H_c)/(0.13 H_c))) | **[published]** Andrews 2012 (GTR-266), via pyretechnics. **Unresolved:** the definition of the crown-fill portion f (pyretechnics: CC/3, crown ratio 1) and the sheltering threshold | H_c canopy height (ft) | after the source check |
| E12 | 10 m → 20 ft wind | U_20ft = U_10m / 1.15 | **[FirePath convention, unverified]**: no primary source found; one press source gives /1.2 for the NWS; a neutral log profile gives 1.09–1.20 for z0 = 0.03–0.5 m (computed). The factor is a constant multiplier on wind speed, so any error is **absorbed by `a_u`** and cannot be separated from it | — | — |

**Free parameters** (revision 3: D3 adopted provisionally, see M1A_RESULTS §D3):

| Parameter | Meaning | Range | Calibrated |
|---|---|---|---|
| `k` | global spread coefficient (outside the bracket in E4) | 0.2–5, log | yes |
| `a_u` (D3, provisional; v1 had `a_w` on φ_w) | systematic multiplier on the 20 ft wind speed before WAF: absorbs HRRR speed bias, the E12 conversion and WAF error; acts on φ_w and LB only through E2/E5/E7 | 0.5–2, log | yes (then fixed) |
| λ (not a model parameter) | **input-uncertainty** multiplier on wind speed in scenarios; effective speed = λ·a_u·U20. Centred at 1; its spread comes from independent HRRR-vs-station *random* error, not bias (the bias is in `a_u`) | from data (M1b) | no: scenario only |
| `a_s` | multiplier on φ_s inside the vector sum | 0.3–3, log | yes, if identifiable |
| `g_timber/g_grass` | fuel-group multiplier (TL/TU vs GR/GS/SH) | 0.3–3, log | yes, if identifiable |
| `m` | multiplier on the three dead moistures | 0.7–1.3 | **no**: scenario variable (confounded with `k`) |

### Slope-plane geometry [FirePath]
Each cell is a plane with gradient g = ∇z (from the 30 m DEM, Horn). A horizontal unit direction d has
surface rise p = g·d. The ellipse lives in the slope plane (E4/E8). The angle ψ is measured there between
the surface direction (d, p)/√(1+p²) and the max-spread direction. The **horizontal-plane speed** used by
propagation is s_h(d) = r(ψ)/√(1 + p²). On flat cells this reduces to the planar ellipse. To be tested on an
inclined-plane fixture (M1a).

### Fuel moisture [FirePath mapping of published scenarios]
- M1: dead 100-h = gridMET fm100, the median over the fire's evaluation window (one value per fire,
  static).
- M2: 10-h = fm100 − 1, 1-h = fm100 − 2 (floor 2 %). These are the offsets of the Scott & Burgan
  D1–D4 scenarios, so fm100 = 5/8/11/14 reproduces them exactly (tested).
- M3: live herbaceous and woody moisture from a pre-declared Scott & Burgan live scenario. **L1 (30/60 %)
  for the April–June Arizona fires [hypothesis]**, L2 as a scenario. Check: NFMD samples (PLAN M0/M1a).
- M4: dynamic transfer per E10.
- M5: `m` scales M1–M2 only.

**Fixed during calibration:** M1–M4, `m` = 1, λ = 1, LB relation (D2), stencil/scheme (D1), WAF rule,
wind conversion. **Separation of model sensitivity from input uncertainty (D3):** `a_u` and λ enter only as
the product λ·a_u, so the model cannot tell them apart (tested: identical arrival fields). The separation is
by design: `a_u` is estimated once on the calibration fires and frozen; λ is varied only in scenarios, with
a distribution taken from an independent comparison (HRRR vs RAWS). Results report the two sources apart:
the parameter range (behavioural set of `a_u`) and the input range (λ).

**Scenario variables:** `m`, live scenario, wind-speed and direction offsets, fuel map
version, `a_s` within its behavioural range. **Identifiability (expected; profiles decide):** `k` strong;
`k`–`a_U` correlated on wind-driven days; `a_s`, `g` weak unless the calibration fires contrast them;
`m` not separable from `k`.

---

## Propagation (specification)

The spread field is *speed per cell per interval along any horizontal direction*:
s_{c,h}(d) > 0 for burnable cells, from E4–E8 and the slope-plane conversion. A **barrier** is a cell with
non-burnable fuel (NB 91/92/93/98/99), missing fuel, missing DEM, or R0 = 0 at its static moisture.
Barriers are time-invariant, because moisture is static and wind never makes a burnable cell's speed zero
(R_head ≥ R0·k·g > 0 and e < 1).

**D1 is open after the revised verification (M1a-3, `M1A_RESULTS.md`)**: no scheme meets the
pre-registered criteria at 30 m. The level set (with L5) is the only scheme that converges at a
consistent order and passes every exact case at 15 m. The graph schemes are exact at barriers but carry
a non-convergent angular error. Earlier status (M1a bake-off): no candidate passed all pre-declared
criteria.
Both candidates are implemented and specified, and neither is adopted.
- **Label-setting** (P1–P4 below, `firepath.reference`). Exact on its graph and on barriers. Its
  angular error is exactly predictable (`firepath.stencil_table`). At radius 8 it fails the accuracy,
  area-spread and wind-change criteria.
- **Eulerian level set** (L1–L4 below, `firepath.levelset`). The WENO5 variant passes the accuracy and
  wind-change criteria, misses the area-spread criterion at LB 8 (3.5 % vs 3 %), and fails the barrier
  fixtures (late behind one-cell gaps and around obstacle corners). It also has an O(Δx) delay at fuel-speed
  contrasts (diagnostic).

**L1. Equation.** φ < 0 is burned. φ_t + H(∇φ) = 0, where H(p) is the support function of the unit-time
spread set (focus-anchored ellipse, E8): H(p) = a[e(p·ŵ) + √((p·ŵ)² + (1 − e²)(p·ŵ⊥)²)], with
a = R_head/(1 + e). This is the front-normal speed of the Huygens envelope **[published principle]**. It
is not the ray speed applied to the normal direction, which pyretechnics uses.
**L2. Discretisation [FirePath].** Local Lax–Friedrichs numerical Hamiltonian with the dissipation bound
|∂H/∂p| evaluated at the corners of the local one-sided gradient box, capped by the half-extent of the
spread set. ENO2 + Heun (B2) or WENO5 + TVD-RK3 (B5). dt = 0.4 Δx / max(α_x + α_y), with steps aligned to
the weather-interval boundaries. Ghost cells by edge replication.
**L3. Barriers [FirePath].** Barrier cells are frozen (φ ≥ Δx). Faces adjacent to a barrier carry zero
flux (the ghost value is the cell's own value), and high-order stencils that touch a barrier fall back to
first order. Without this, the front choked at one-cell gaps.
**L4. Arrival and ignition.** The arrival is the linear interpolation of the zero crossing within a step.
A point ignition is a disc of radius r0 (2 cells in the bake-off). Under ENO2, discs smaller than about
one cell vanish. Mode A: φ0 = signed distance to the cell-centre raster region; inside barriers are not
sources.

**L5. Narrow band, reinitialization and extension velocities (M1a-3, state of practice).**
- *Narrow band:* only cells with |φ| < (8 − 0.5) cells evolve; the rest are clamped at ±8 cells.
- *Reinitialization:* every 10 steps, geometric. φ ← ±(distance from each cell centre to the zero
  crossings), where the crossings are interpolated linearly on grid edges and densified along the chord
  inside each grid square, using a KD-tree. Interface-adjacent cells are redistanced too, which kept the
  crossing positions and measured more accurately than keeping their old values.
- *Extension velocities:* every step, each cell takes the spread parameters (a, e, ŵ) of the cell that
  contains its nearest interface point (Adalsteinsson & Sethian 1999).

Why: without the band and reinitialization, the field far ahead of the front distorted in heterogeneous
fuel until spurious zero crossings appeared. 537 cells in the isotropic mosaic burned before
distance / max speed allowed (regression test `tests/test_levelset_regression.py`). Without extension
velocities, reinitialized fronts arrived *early* when passing from fast into slow fuel.

**Remaining known error [verified]:** first-order behaviour at fuel-speed discontinuities. For example,
the 1-D strip is −11 % at the first slow cell, and the contrast case is −1.1 % at 30 m. These errors are
quantified by grid convergence in M1A_RESULTS.

**P1. Edges.** For a stencil offset δ = (dr, dc) (primitive, Chebyshev radius ≤ ρ), the edge e = (u, δ) is
the straight segment from the centre of u to the centre of v = u + δ, of length L = Δ‖δ‖ in direction
d_e. Exact rational traversal gives ordered pieces (c_j, ℓ_j) with ℓ_j > 0 and Σ ℓ_j = L
(`firepath.stencil.traversal`).

**P2. Edge-arrival function.** Let P(t) be the distance travelled along the segment, with P(t_u) = 0 and
dP/dt = s_{c(P), h(t)}(d_e), where c(P) is the piece containing P. Then A_e(t_u) = min{t : P(t) = L}.
The speed is piecewise constant on rectangles (piece × interval), so A_e is computed exactly by
event stepping. In the current piece with remaining length ℓ at time τ in interval h (ending at T_{h+1}):
if τ + ℓ/s ≤ T_{h+1}, then τ ← τ + ℓ/s and move to the next piece; else ℓ ← ℓ − s(T_{h+1} − τ),
τ ← T_{h+1}, and continue with h + 1. Pieces inside initial-perimeter burnable cells have infinite speed
(zero cost, see I3). There is no waiting state: speeds are positive.

**P3. FIFO.** For every valid edge, A_e is continuous and strictly increasing, and A_e(t) > t. *Proof
sketch:* within one piece, the time to cover a fixed length starting at τ is the inverse of the strictly
increasing, continuous cumulative-distance function D(τ′) = ∫_τ^τ′ s dt. Departing later never covers the
same distance sooner, so the per-piece map is strictly increasing. A_e is a composition of such maps.
Tested: strict monotonicity on random fields (20 × 16 offsets × 400 departures), agreement with
independent time marching.

**P4. Algorithm.** Label-setting on the heap key (arrival, cell index) with total order. Pop the minimum,
finalize, relax all valid edges with A_e. Under FIFO, this computes earliest arrival times on the
time-dependent graph, and waiting at nodes never helps (Dreyfus 1969; Orda & Rom 1990; Kaufman & Smith 1993).
Ties change only the order of pops, never the final labels. Stop when the popped minimum exceeds t_stop;
labels > t_stop become "not reached".

**What FIFO does not establish:** (i) the graph solution approximates the continuum front. Directions are
limited to the stencil and bend only at nodes. The error is quantified in CRITICAL_REVIEW P0-1 and is
**large for elongated fires** at radius 2. (ii) Huygens superposition of instantaneous ellipses under
changing wind is physically right (no acceleration, transients or memory). (iii) The ROS inputs are
right. The graph solution is never earlier than the continuum solution of the same model (tested: point
ellipse, Minkowski wind change), so stencil error always delays arrival.

### Edge geometry and barriers
- **B1:** a transition is invalid if it leaves the grid or **any crossed cell (positive length) is a
  barrier**. This covers straight moves, knight moves (two intermediate cells, each ¼ of the length) and
  longer moves.
- **B2:** a segment for δ = (dr, dc) passes through a grid vertex iff dr and dc are both odd (e.g. (1,1),
  (1,3), (3,1)). The two cells that touch the vertex but are not crossed meet the segment in one point.
- **B3:** a transition through a vertex whose **two side cells are both barriers** is invalid (a
  one-cell-thick diagonal wall). A single barrier corner is passable.
- **B4:** fuel changes along an edge are handled by piece-wise speeds (P2). A partially crossed cell
  contributes only its crossed length.
- Tested: exact tables for (0,1), (1,1), (1,2), (1,3); invariants up to radius 4; a full-propagation
  anti-diagonal wall at radius 1–3; a wall with a gap lower-bounded by the visibility-graph geodesic.

### Initial perimeter (Mode A)
- **I1:** inside(c) ⇔ the centre of c lies in the observed perimeter P0 (cell-centre rule).
- **I2:** S = {c : inside(c) ∧ burnable(c)}. Arrival t0, status *initial*. Inside barriers keep status
  *barrier*: they are never sources and still block transitions (no lake-hopping).
- **I3:** pieces of an edge inside S cost nothing. The front at t0 is therefore the boundary of the union
  of S's squares, not the cell centres. Measured on a disc: mean signed error −0.17 cells, 5–12 cells out.
- **I4:** outside cells never relax inside cells. Seeding only cells of S that have a valid edge to an
  outside burnable cell gives identical results (tested, bit-identical).
- **I5:** perimeter features narrower than one cell that contain no cell centre are lost (tested). This is
  a rasterization limit.
- **Mode B:** point ignitions at burnable cells. An ignition on a barrier is an error.

### Output
`arrival_h` (float32 hours since t0, written from float64) and `status` (0 not reached, 1 reached,
2 initial, 3 barrier, 4 outside domain), as PLAN §14.

---

## Observations and validation metrics

**O1. Perimeter sequence audit** (`firepath.observed.audit_sequence`; perimeters are never forced to be
nested):
- Times must be strictly increasing (scan time, UTC). A duplicate or decreasing time is an error to
  resolve at source.
- For each step k, report the cells newly included, and the cells removed from P_{k−1}, split into
  **jitter** (within 1 cell of P_k) and **retraction** (farther: a possible correction of earlier
  mapping or a real interpretation change).
- Per cell: CONSISTENT (enters once, stays), INITIAL (in P0, stays), NEVER, INCONSISTENT (leaves after
  entering).
- Observed arrival interval: (t_{k*−1}, t_{k*}] at first entry k*; INITIAL (−∞, t0]; NEVER (t_K, ∞).
  INCONSISTENT cells keep their first-entry interval for reporting but are **excluded from the primary
  metric** and counted.
- Per-step overlap metrics use P_k as observed. Steps whose retraction share exceeds 2 % of P_{k−1} are
  flagged in the report before scoring. The threshold is fixed now.

**O2. Primary metric (unchanged from PLAN §8):** signed interval error (`interval_error`): early = t − lo
(< 0), late = t − hi (> 0), 0 inside the interval; capped at 48 h; averaged over cells burned in the
observation or the model within the window, excluding INITIAL and INCONSISTENT cells and masked days;
equal weight per fire. **Limitation:** with wide intervals (missing flights), any arrival within the
interval scores 0. The metric then measures consistency, not timing precision.

**O3. Secondary measures (pre-declared):**
- distribution of interval widths per fire;
- shares of early / inside / late cells, with the median signed error of each;
- **boundary timing error** T_model(x) − t_k at points every 30 m along each observed perimeter
  (positive = model late);
- modelled/observed area ratio per step (> 1 = model fast);
- growth-only Dice, IoU/Dice, boundary distances, Hausdorff (PLAN §9);
- the primary metric recomputed on intervals ≤ 30 h, reported as a split, never as a replacement.

**O4. Satellite detections:** comparison only (PLAN §2.4).

## Baseline
PLAN §7. B0 isotropic constant rate; B1 wind-only ellipse driven by the hourly wind (it uses E7 and the
same propagation scheme, so stencil artefacts affect model and baseline alike). Calibrated the same way.

## Validation
PLAN §8–9 (temporal holdout, locked parameters, G1/G2 criteria stated before results). Not run.

## Uncertainty and sensitivity
PLAN §10, plus the D1 bake-off criteria as the artefact acceptance (CRITICAL_REVIEW P0-1). Not run.

## Decision metric
Arrival time per cell; modelled closure time per road segment; population without a modelled road
connection by hour. Each comes with its scenario range and its fire's validation error.

## Rust component
Planned after M1a (PLAN §12, §16). The Python reference here is the oracle. Measured cost on the cloud
container (4 vCPU, x86_64): ≈ 75 µs per cell at stencil radius 2 and ≈ 1.6 ms per cell at radius 8, for
time-varying elliptical spread.

## Limitations and omitted processes
Spotting, crown-fire transition, dynamic moisture, fire–atmosphere feedback, suppression and firing
operations, sub-cell fuel heterogeneity, terrain-resolving wind, unburned islands (PLAN §15). Also:
stencil-direction error (until D1), sub-cell perimeter features, static moisture per fire.

## Decisions log
| Date | Decision | Alternatives considered | Reason |
|---|---|---|---|
| 2026-10-09 | Arrival-time (ROS → anisotropic propagation) model, not a burn/no-burn CA | cellular automaton | spec §7 |
| 2026-10-09 | Proposed pool: USFS R3 2019–2022, temporal holdout | California R5; leave-one-fire-out | PLAN §2 (pending approval, Q1) |
| 2026-10-09 | NIROPS IR perimeters as primary targets | NIFS archive (edit times), FEDS/FIRMS | observation time, airborne resolution |
| 2026-10-09 | UTM per fire | native Albers + Jacobian | measured Albers anisotropy |
| 2026-10-09 | Rotate HRRR U/V | use as is | grid-relative flag verified |
| 2026-10-09 | Moisture multiplier not calibrated | calibrate with k | confounded with k |
| 2026-10-09 | Ensemble = scenario agreement | probability | not justified |
| 2026-10-09 | TIGER + census blocks | OSM | public domain; no ODbL |
| 2026-10-09 (rev 2) | Exact edge-arrival integration over pieces × intervals (P2), FIFO (P3) | fixed per-edge speed at departure time | v1 left integration undefined; exactness and FIFO are testable |
| 2026-10-09 (rev 2) | Vertex rule B3 | "any crossed cell" only | diagonal walls leaked |
| 2026-10-09 (rev 2) | Mode A: zero-cost inside burnable cells; inside barriers are not sources | centre sources; all inside cells as sources | unbiased raster front; no lake-hopping |
| 2026-10-09 (rev 2) | LB in mi/h form (0.1147/0.0692); relation choice open (D2) | v1 m/s coefficients with mi/h input | unit error found |
| 2026-10-09 (rev 2) | Moisture mapping M1–M5 | discrete D-scenario lookup | continuous, reproduces D1–D4 exactly |
| 2026-10-09 (rev 2) | Nearest-analysis HRRR intervals | analysis applies for the following hour | removes a systematic 30 min lag |
| 2026-10-09 (rev 2) | Non-nested perimeters audited, not forced (O1) | union/forced nesting | forcing would hide corrections |
| open (D1) | Propagation scheme | radius-8 Dijkstra; Eulerian level set | 16-stencil error 20–120 % for LB 2–5 |
| open (D3) | Wind-speed multiplier `a_U` | `a_w` on φ_w | `a_w` changes the ellipse shape via E5 |
