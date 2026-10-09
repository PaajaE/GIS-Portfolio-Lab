# M1a-2 pre-registration (D1 experiments)

> Written and committed **before** any of these experiments was run (2026-10-09). The criteria below must
> not change after results are seen. Any deviation will be reported as a deviation in `M1A_RESULTS.md`.

## E1: heterogeneous mosaic vs a refined-grid reference

- **Map.** 61 × 61 cells of 30 m. Two fuels from a Gaussian random field (NumPy `default_rng(20261009)`,
  white noise smoothed with a Gaussian of σ = 3 cells, thresholded at its median, so ≈ 50/50 patches).
  Head ROS 1.0 m/min (fast) and 0.25 m/min (slow): a 4× contrast. No barriers.
- **Cases:** (i) isotropic; (ii) LB 2, wind 20°; (iii) LB 4, wind 20° (eccentricity from LB, uniform
  over the map).
- **Initial condition (Mode A):** a disc of radius 2.5 coarse cells (75 m) centred at coarse cell
  (30, 12), rasterized by the cell-centre rule at each resolution.
- **Refined reference:** the same physical map at 10 m (3×, nearest-neighbour upsampling of the coarse
  fuel map, so the fuel geometry is identical and coarse cell centres coincide with fine cell centres).
  It is solved by **both** the radius-16 graph and the WENO5 level set.
  - *Reference validity:* if the two refined solutions agree within median |rel diff| ≤ 1 % and 95th
    percentile ≤ 3 %, the reference is their mean.
  - Otherwise each candidate is scored against **each** refined solution and must pass against both.
- **Scored cells:** coarse cells outside the initial disc, ≥ 5 cells from its edge, with a reference
  arrival ≤ the simulation end.
- **Pass criteria per case:** median |relative error| ≤ 5 % **and** 95th percentile ≤ 10 %
  (the proposal in M1A_RESULTS, with 3× instead of 4× refinement so that cell centres coincide; fixed
  here before running).
- **Candidates at 30 m:** WENO5 level set (B5), radius-16 graph, radius-8 graph (context), and any
  barrier-improved level-set variant from E3.

## E2: radius-16 graph under a 90° wind change

The bake-off criterion 3 fixture unchanged (121 × 121, source (90, 30), wind 10° → 100° at 600 min,
LB 2 and 4, cells ≥ 25 cells away with reference ≤ 2500 min). **Pass:** max |relative error| ≤ 5 %.

## E3: improved level-set barrier treatment

Any modified level-set scheme must pass, with the same tolerances the label-setting scheme passes:
- one-cell-gap wall (25 × 25, wall at column 12, gap at row 18, source (5, 4)): for every evaluated cell,
  arrival ≤ geodesic × 1.0276 + 2 cells of travel time, and arrival ≥ geodesic × 0.99 (no early
  arrival). The geodesic is measured from the edge of the 2-cell ignition disc;
- lake at the initial boundary (61 × 61): arrival at (30, 25) ≤ geodesic × 1.0276 + 2 cells, and
  ≥ geodesic × 0.99;
- no leaks through one-cell straight or diagonal walls;
- **and** it must still pass bake-off criteria 1 and 3 on the original fixture, with criterion 2
  reported.

## Decision rule (unchanged from CRITICAL_REVIEW P0-1, extended by E1)

A scheme is recommended only if it passes bake-off criteria 1–4 **and** E1 for all three cases. If
several pass, the cheapest by measured run time is recommended. If none passes, no scheme is
recommended: the trade-off is summarized and the decision goes back to the owner.
