# FirePath — Method

> Status: **draft (planning)**, 2026-10-09. Spec section: §7. Only what research has established is
> written here; the proposed design is in [`PLAN.md`](PLAN.md) and moves here as it is implemented and
> verified. No model has been run.

## Problem / decision
**Question (spec §7):** can a lightweight, reproducible rate-of-spread / arrival-time model reconstruct
historical wildfire growth well enough to explore alternative fuel, terrain and wind scenarios?

**Who acts:** fire-management/fuels planners and county emergency managers doing after-action or planning
analysis; analysts studying where a simple surface-spread model works and fails. **Decision supported:**
how much plausible changes in wind, fuel moisture, fuels or slope effect shift *when* a fire reaches a
road or community, and whether that conclusion is robust. Output wording: a modelled reconstruction under
stated inputs — **not a forecast, not FARSITE/FlamMap, not an operational system**; network results are
*exposure* in *network travel time*, not risk.

## Study area and analytical unit
Unknown until M0 screening. Proposed: five USFS Southwestern Region (Arizona) fires 2020–2022, temporal
holdout (PLAN §2). Unit of analysis: 30 m cell (arrival time). Reporting units: fire × observed time step
(validation), road segment (closure time), census block (population exposure).

## Data and rationale
Proposed table in PLAN §4. Established so far: HRRR 10 m U/V on AWS are grid-relative (verified from a
GRIB2 sample) and must be rotated; other sources not yet probed from the build machine.

## Harmonization
- CRS decision: NAD83 / UTM 12N (EPSG:26912) per Arizona fire. Verified projection factors at the candidate
  fires: EPSG:5070 has ≈ ±0.7–0.9 % anisotropic scale and ≈ 1° angular distortion, UTM 12N ≤ 0.04 %.
- Resolution 30 m (LANDFIRE native); categorical → nearest; DEM averaged before slope; winds rotated
  before interpolation. Temporal rules (LANDFIRE version predating each fire) in PLAN §3 — to verify in M0.

## Baseline
Proposed (PLAN §7): B0 isotropic constant rate; B1 wind-only ellipse with hourly HRRR wind. Not run.

## Advanced method
Proposed (PLAN §6): Rothermel surface ROS per Scott & Burgan fuel model with stated multipliers, wind/slope
vector combination, Anderson (1983) length-to-breadth ellipse, time-dependent Dijkstra on a 16-neighbour
stencil with exact traversal integration. Not implemented.

## Validation
Design pre-registered in PLAN §8–9 (temporal holdout, locked parameters, growth-only and arrival-time
metrics, G1/G2 criteria stated before results). No results.

## Uncertainty and sensitivity
Design in PLAN §10. Ensembles are "scenario agreement", not probability, unless justified. No results.

## Decision metric
Arrival time per cell (h since fire-specific t0, UTC); modelled closure time per road segment; population
without a modelled road connection by hour — each with scenario range and the fire's validation error.

## Rust component
Planned (PLAN §12): time-dependent propagation and parallel scenario execution; Python heapq reference as
oracle. Why Rust: ≈ 25,000 propagations of 0.5–4 M cells with time-dependent costs (estimate, to be
measured). Not implemented.

## Limitations and omitted processes
Spotting, crown-fire transition, dynamic moisture, fire–atmosphere feedback, suppression/firing operations,
sub-cell fuel heterogeneity, terrain-resolving wind, unburned islands — expected biases in PLAN §15.

## Decisions log
| Date | Decision | Alternatives considered | Reason |
|---|---|---|---|
| 2026-10-09 | Arrival-time (ROS → anisotropic propagation) model, not a burn/no-burn CA | cellular automaton | spec §7; arrival time supports timing, closures, exposure by hour |
| 2026-10-09 | Proposed pool: USFS R3 (Arizona/NM) 2019–2022; temporal-holdout split | California R5 pool; leave-one-fire-out | surface-fuel-dominated, NIROPS coverage, one fuel-climate domain; split decided by date, not fit (pending approval, Q1) |
| 2026-10-09 | NIROPS IR perimeters as primary time-stamped targets | NIFS operational archive (edit times), FEDS/FIRMS (satellite) | observation time, airborne resolution; others as cross-checks/fallback |
| 2026-10-09 | UTM per fire instead of LANDFIRE's EPSG:5070 | native Albers + Jacobian correction | measured Albers anisotropy (≈ 0.8 %) and angular distortion (≈ 1°) would bias an anisotropic model |
| 2026-10-09 | Rotate HRRR U/V from grid- to earth-relative | use as-is | GRIB2 flag verified grid-relative; ≈ 9° direction error near Flagstaff otherwise |
| 2026-10-09 | Moisture multiplier not calibrated (scenario variable) | calibrate with k | confounded with k (both scale R0) |
| 2026-10-09 | Ensemble = scenario agreement, not probability | probability of burning | input ranges are not calibrated distributions; 2 validation fires cannot establish reliability |
| 2026-10-09 | TIGER/Line roads + 2020 census blocks | OpenStreetMap | public domain; avoids ODbL share-alike on the derived network |
