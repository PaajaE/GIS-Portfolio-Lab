# M1a-4 — HY confirmation run at 30 m (pre-registration)

> Committed **before** the run (2026-10-24), after the owner chose D1 = hybrid (HY) at 30 m with the
> LB 8 relaxation (`M1A_RESULTS.md`, "D1 decision"). Numerical verification only. The thresholds are
> FirePath acceptance criteria, not industry standards (as in `M1A3_PREREGISTRATION.md`).

## Why this run
M1a-3 left HY's mosaic result open: Richardson's assumptions held on only 15–68 % of cells, so no
error estimate could be accepted from it. The raw same-scheme difference 30 m vs 7.5 m was median
2.0–2.7 %, p95 9.4–14.3 %. A same-scheme difference cannot show a bias that persists under refinement.
This run adds an **independent cross-scheme reference**.

## C*: mosaic, HY at 30 m against the level set at 7.5 m
- Cases: the M1a-3 random two-fuel mosaic, `iso`, `lb2`, `lb4` (`firepath.mosaic`, unchanged seed).
- Reference: **LS at 7.5 m**, the only scheme with consistent observed order (p ≈ 1.3–2.3) on the exact
  cases. Value per coarse cell = mean of the 4×4 fine cells around the coarse centre (as in M1a-3 C).
- Reference uncertainty, reported per cell: u = |LS15 − LS7.5| / LS7.5.
- Error: e = |HY30 − LS7.5| / LS7.5 on the M1a-3 scored mask (≥ 5 cells beyond the start disc,
  finite on all grids, reference ≤ T_END).
- **Pass (every case):** median e ≤ 5 %, p95 e ≤ 10 %, judged on **all** scored cells; zero cells
  earlier than 0.98 × the raster lower bound. The same statistics restricted to cells with u ≤ 2 % are
  reported alongside, but they do not decide the result.
- The mosaic has no LB 8 cells, so the LB 8 relaxation does not apply here.

## Not re-run
- Barriers (B): HY passed all barrier fixtures at 30 m in M1a-3. The cell size is unchanged.
- Exact cases (A): HY 16/17 at 30 m. The single failure (LB 8 at 45°) is the case the owner relaxed.

## Cost (informational, no pass/fail)
HY wall time per cell at 30 m on the mosaic, in the pure-Python reference (single thread, cloud
container), extrapolated linearly to the M1b grid sizes. It is not a Rust estimate.

## Decision rule
- Pass → HY at 30 m is confirmed for M1b and M2.
- Fail → report medians and tails and return to the owner. Fallbacks: HY or LS at 15 m for the M1b
  sub-window, or accept the documented error. The criteria are not changed after the run.
