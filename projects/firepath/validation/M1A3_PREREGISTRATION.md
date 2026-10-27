# M1a revised (V&V) — pre-registration v2

> Committed **before** the runs it governs (2026-10-09), after the owner approved `PRACTICE_REVIEW.md` §6.
> It supersedes `M1A2_PREREGISTRATION.md` for scheme selection. Earlier results stay on record. This
> concerns **numerical verification only**; historical-fire validation (PLAN §8–9) is separate and unchanged.
>
> The 5 % / 10 % thresholds below are **FirePath acceptance criteria**, chosen by the project. They are
> not industry standards. For context: Muñoz-Esparza et al. (2018) report < 1 % ROS error for a
> state-of-practice level set on analytic cases; Cruz & Alexander's ±35 % is a *validation* standard for
> predicted ROS and is not used here.

## Schemes (each verified independently)

- **G8:** time-dependent label-setting, stencil radius 8.
- **G16:** label-setting, radius 16. Code-verification cases only, because of its cost.
- **LS:** level set, WENO5 + TVD-RK3, local Lax–Friedrichs, zero-flux barrier faces, **narrow band (8 cells)
  + geometric reinitialization every 10 steps** (the state-of-practice fix; anomaly regression test
  `tests/test_levelset_regression.py`).
- **HY:** LS followed by G8 seeded with the LS arrivals (minimum of the two).

## A. Code verification: canonical cases with exact, scheme-independent solutions

The domain is fixed in metres. Each case runs at Δ = 30, 15 and 7.5 m. Errors are relative arrival-time
errors |T − T_exact| / T_exact on scored cells (≥ 300 m from the initial-condition edge, T_exact ≤ the
case's end time, forward half-plane for elliptical cases).

| Case | Exact solution |
|---|---|
| A1 expanding circle (isotropic, disc r0 = 60 m) | (\|x − c\| − r0)/R |
| A2 ellipse, LB 2 / 4 / 8 at wind 0°, 22.5°, 45° | disc ⊕ t·E (support functions) |
| A3 90° wind change, LB 2 / 4 | Minkowski sum (support functions) |
| A4 two-fuel half-plane, 4× contrast, isotropic and LB 2: source in the fast half and in the slow half | refraction: minimum over interface crossing points, including interface-guided (head-wave) paths, by fine 1-D minimisation (Δs = 0.05 m) |
| A5 merging fronts: two discs, isotropic | min of the two disc solutions |

Reported per scheme × case × Δ: median and 95th percentile of the relative error, and the observed order
p = log2(e(Δ)/e(Δ/2)) from the median errors.

**Pass (per scheme):** at Δ = 30 m, median ≤ 5 % **and** p95 ≤ 10 % on **every** case. Convergence is
reported: a scheme whose error does not decrease under refinement is marked "not convergent" (an
expected property of fixed-stencil label-setting) but is not failed for that reason alone.

## B. Barriers (scheme-independent geodesic references)

The existing fixtures (one-cell gap; lake at the initial boundary; no leak through one-cell straight or
diagonal walls) with the E3 tolerances: geodesic × 0.99 ≤ T ≤ geodesic × 1.0276 + 2 cells. All schemes,
at 30 m.

## C. Solution verification: the random two-fuel mosaic (no exact solution)

Same mosaic and cases as E1 (iso, LB 2, LB 4). Each scheme runs on **its own** sequence 30 / 15 / 7.5 m
(fuel map nearest-upsampled, so the geometry is identical). Per coarse cell (coincident centres:
sub-sampling at 15 m by 2 with offset 0, i.e. the coarse centre lies on a fine-cell corner, so the
fine-grid value is the mean of the 2×2 (15 m) or 4×4 (7.5 m) cells around the coarse centre):

- Richardson/GCI is used **only where its assumptions hold**: monotone convergence (f30 − f15 and
  f15 − f7.5 have the same sign and |f15 − f7.5| < |f30 − f15|), with observed order 0.5 ≤ p ≤ 3.
  Extrapolated value f_ext = f7.5 + (f7.5 − f15)/(2^p − 1); estimated 30 m error = |f30 − f_ext| / f_ext.
- Applicability is reported as the share of scored cells meeting the assumptions. If the share is below
  80 %, no acceptance claim is made from Richardson. The raw |f30 − f7.5| / f7.5 is reported instead, and
  the case is marked "Richardson not applicable".
- **Pass:** applicability ≥ 80 % and estimated 30 m error median ≤ 5 % and p95 ≤ 10 %.
- Additional hard check: zero cells earlier than the physical lower bound (distance / max speed).

## Decision rule

A scheme is **acceptable** if it passes A (every case at 30 m), B, and C (all three mosaic cases) and has
zero lower-bound violations. If several are acceptable, recommend the cheapest by measured run time. If
none is, report the trade-off with medians and tails, and return D1 to the owner.
