# M1a-5 — HY at 30 m against a bracketing reference (pre-registration)

> Committed **before** the run (2026-10-25), after M1a-4 (`M1A_RESULTS.md`): its single-scheme reference
> (LS 7.5 m) was shown to lie above a feasible-path upper bound, so that test could not attribute the gap
> to HY. Owner approved this follow-up. Numerical verification only. The thresholds are FirePath
> acceptance criteria, unchanged from M1a-3/M1a-4.

## Cases and grids
The M1a-3 random two-fuel mosaic (`firepath.mosaic`, unchanged seed; fuel map defined on the 30 m grid
and repeated, so every grid sees the same fuel geometry): `iso`, `lb2`, `lb4`. Fine grids: 15, 7.5 and
3.75 m (factors 2, 4, 8). Fine values are block means around each coarse centre, as in M1a-3.

## Reference, per scored coarse cell
1. **Upper bound** U = min(G8, G16) at 3.75 m. In a static field a graph path with exactly integrated
   edge times is a path the fire can follow, so U ≥ the true arrival (for the 3.75 m start raster).
2. **Estimate** from LS at 15 / 7.5 / 3.75 m. Richardson applies under the M1a-3 rules (monotone,
   |f7.5 − f3.75| < |f15 − f7.5|, 0.5 ≤ p ≤ 3). Then f_ext = f3.75 + (f3.75 − f7.5)/(2^p − 1).
3. **Reference R:**
   - Richardson applies and f_ext ≤ U: R = f_ext (category "estimate").
   - Richardson applies and f_ext > U: R = U ("bound").
   - Richardson does not apply: R = min(LS3.75, U) ("fallback"; an upper-side value).
   The share of each category is reported.

## Metrics
- e = |HY30 − R| / R on the M1a-3 scored mask (≥ 5 cells beyond the start disc; finite on all grids;
  R ≤ T_END). Median, p95, and the signed median are reported.
- Provable lateness: share of cells with HY30 > U, and (HY30 − U)/U on those cells (median, p95).
- Reference spread: s = (U − R)/R (median, p95). It shows how far apart the bound and the estimate are.
- Lower bound: zero cells earlier than 0.98 × the raster lower bound.

## Outcomes (decided per case; the overall result is the worst case)
- **INCONCLUSIVE** if the reference spread s has median > 2.5 % (half the median criterion), or fewer
  than 50 % of cells are in the "estimate" category. Then the reference cannot resolve the criterion.
- Otherwise **PASS** if median e ≤ 5 %, p95 e ≤ 10 %, p95 of provable lateness ≤ 10 %, and zero
  lower-bound violations. Anything else is **FAIL**.

## Decision rule
- PASS → HY at 30 m is confirmed for M1b and M2.
- FAIL → back to the owner. Fallback: HY at 15 m for the M1b sub-window.
- INCONCLUSIVE → back to the owner. HY at 30 m only by explicit owner decision, documented as unverified
  on the mosaic.
- The criteria are not changed after the run.

## Cost
Measured wall times per scheme and grid (pure-Python reference, single thread per process, cloud
container). Informational.
