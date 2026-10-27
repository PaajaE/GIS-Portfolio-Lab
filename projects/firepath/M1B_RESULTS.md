# M1b results: Mangum 2020 end-to-end (reference slice) and M2 kernel status

Status 2026-10-26. Mangum is a **calibration** fire, never a validation fire. All model and baseline
parameters are **hand-set placeholders** (run.py header). These numbers check the pipeline, not skill.

## What ran

| Step | Output | Verified by |
|---|---|---|
| Harvest (perimeters, LANDFIRE LF2016 via WCS, 3DEP, HRRR f00, gridMET) | `provenance/harvest_mangum.json` (sha256 per file) | `tests/test_stage_boundaries.py::test_provenance_hashes_match_raw_files` |
| Prepare (warp, Horn slope, HRRR rotation, perimeter audit, moisture) | `provenance/prepare_mangum.json` | `tests/test_prepare.py`; stage-boundary tests (CRS EPSG:26912, grid identity, fuel codes ⊂ SB40 ∪ non-burnable, no nodata, scan and wind time order, wind covers the AOI and all scans) |
| LANDFIRE leakage rule and stale fuels | LF2016 for a 2020 fire; `provenance/stale_fuels_mangum.json` from the annual WCS disturbance layers LF2020_Dist17–20 | version year < fire year (test). The 2020 disturbance layer covers 99.9 % of the final perimeter, so LF2020 fuels would leak the outcome (test). Stale fuels: 13.5 % of burnable cells inside the final perimeter (8.8 % of the AOI) were disturbed in 2017–2019 and are missing from LF2016 fuels; the recoded-fuel sensitivity scenario is M5 |
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

### 30 m sub-window (model only)

400 × 400 cells (12 × 12 km) at 30 m centred on the first perimeter (rows 1059–1459, cols 9–409 of the
30 m grid), same window and hand-set parameters: 157,188 scored cells, mean abs 41.6 h, signed −41.0 h,
95 % early, 4 % inside, 1 % late; Dice per scan 0.12–0.41. Run time 1,605 s (Rust HY, cloud). The window
edge is a hard domain limit and most of the fire grows outside it, so this row checks that the 30 m path
runs end to end; it is not comparable with the 90 m rows.
`validation/m1b_mangum_30m_HY_w400_model.json`.

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

## M2 benchmark (cloud session, `benchmarks/propagation.json`)

Mangum 90 m model field, 24 h from the first perimeter; Intel Xeon 2.8 GHz, 4 logical CPUs. Not the
build Mac: M7 repeats it there.

| window | cells reached | graph r8: ref / Rust (s) | level set: ref / Rust (s) | HY: ref / Rust (s) |
|---|---|---|---|---|
| 64 × 64 | 3,072 | 14.2 / 0.56 (25×) | 14.6 / 4.9 (3.0×) | 29.3 / 5.4 (5.4×) |
| 128 × 128 | 4,566 | 23.6 / 0.88 (27×) | 26.0 / 8.2 (3.2×) | 48.9 / 9.3 (5.3×) |
| 204 × 197 (clipped at the grid edge) | 4,566 | 23.3 / 0.94 (25×) | 29.5 / 8.6 (3.4×) | 52.7 / 9.6 (5.5×) |

Rust and reference agree: level set identical, graph and HY within 2.3e-13 min. In 24 h the fire
reaches the same 4,566 cells in the two larger windows, so those rows differ only in grid overhead; the
sizes do not scale the work. The level set dominates HY in Rust (≈ 90 % of its time) and gains only
≈ 3×: its cost is the CFL-limited step count (head ROS up to 68 m/min at 90 m), which the port does not
change. Scenario rows (10 runs, 128 × 128): 99.8 s on 1 worker, 52.8 s on 2 (1.89×), 32.7 s on 4
(3.05×), results identical to 1 worker.
