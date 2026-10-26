# M1b results: Mangum 2020 end-to-end (reference slice) and M2 kernel status

Status 2026-10-26. Mangum is a **calibration** fire, never a validation fire. All model and baseline
parameters are **hand-set placeholders** (run.py header). These numbers check the pipeline, not skill.

## What ran

| Step | Output | Verified by |
|---|---|---|
| Harvest (perimeters, LANDFIRE LF2016 via WCS, 3DEP, HRRR f00, gridMET) | `provenance/harvest_mangum.json` (sha256 per file) | `tests/test_stage_boundaries.py::test_provenance_hashes_match_raw_files` |
| Prepare (warp, Horn slope, HRRR rotation, perimeter audit, moisture) | `provenance/prepare_mangum.json` | `tests/test_prepare.py`; stage-boundary tests (CRS EPSG:26912, grid identity, fuel codes ⊂ SB40 ∪ non-burnable, no nodata, scan and wind time order, wind covers the AOI and all scans) |
| LANDFIRE leakage rule | LF2016 for a 2020 fire | structural test (version year < fire year). The conus_2016 WCS serves no FDist layer, so the "no fire-year disturbance in the AOI" check is not possible from this source |
| Mode A, 90 m, HY (D1), model + B0 + B1 | `validation/m1b_mangum_90m_HY_{model,B0,B1}.json` | output invariants (non-burnable never reached, arrivals ≥ 0, no NaN) |
| One-step-ahead, 90 m, HY | `validation/m1b_mangum_90m_HY_step_model-B0-B1.json` | `tests/test_run_metrics.py` (metric definitions on a hand-checked case) |
| Error maps with legends | `validation/figures/m1b_mangum_90m_HY_error.png` | looked at; bins tested (`test_classify_bins`) |

Window: 2020-06-10 07:13 → 06-17 07:15 UTC, 8 scans (the last scan within 7 days and before 90 % of the
final area), 217 hourly HRRR fields, grid 495 × 399 at 90 m.

## Mode A (interval-censored arrival error, capped at 48 h)

| | scored cells | mean abs (h) | mean signed (h) | early | inside | late |
|---|---|---|---|---|---|---|
| model (k = a_u = a_s = 1) | 183,297 | 34.1 | −33.3 | 96 % | 2 % | 2 % |
| B0 (1 m/min) | 50,118 | 40.2 | −5.4 | 58 % | 3 % | 39 % |
| B1 (0.5 (1 + 0.05 U10^1.5) m/min, WAF 0.4) | 29,864 | 41.5 | 24.9 | 24 % | 3 % | 73 % |

The scored set is CONSISTENT cells plus never-observed cells the run burned (METHOD), so it differs per
run: overprediction adds scored cells. The rows are therefore not a ranking. With hand-set k = 1 the
model spreads far too fast (96 % early); calibrating k, a_u and a_s is M3.

## One-step-ahead (perimeter k → k+1, growth outside perimeter k)

Dice of the growth per step k = 0…6:

| | k0 | k1 | k2 | k3 | k4 | k5 | k6 |
|---|---|---|---|---|---|---|---|
| observed growth (cells) | 107 | 711 | 4228 | 4423 | 2382 | 2480 | 8867 |
| model | 0.05 | 0.14 | 0.22 | 0.39 | 0.22 | 0.15 | 0.32 |
| B0 | 0.08 | 0.24 | 0.25 | 0.54 | 0.29 | 0.17 | 0.30 |
| B1 | 0.22 | 0.31 | 0.26 | 0.50 | 0.49 | 0.29 | 0.27 |

Model growth ratio (modelled / observed growth) 2.2–41×: the same overprediction as in Mode A.
Run time: model 647 s, B0 69 s, B1 66 s for all seven steps (cloud session).

## Not done in M1b, and why

- **HRRR vs RAWS wind check (λ distribution):** blocked. WRCC now refuses hourly and daily listings
  before 2026 without an access code. Q3 is re-opened in PLAN.
- **Domain-limited check (doubling the 5 km buffer):** not meaningful yet. With hand-set k = 1 the model
  reaches the domain edge after 31 h, and 74 % of edge cells burn before the last scan (B0 20 %, B1 0 %),
  so it would be flagged domain-limited by construction. The check runs with calibrated parameters
  (M3), on a second harvest with a 10 km AOI. The HRRR crop (0.1° margin) and the 3DEP tiles already
  cover it; LANDFIRE needs a wider WCS subset.
- **Masked days:** none for Mangum (`validation/masked_intervals.json`).
