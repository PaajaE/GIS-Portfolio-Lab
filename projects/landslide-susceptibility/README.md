# Landslide Susceptibility — Buncombe + Yancey, NC

> Status: **M6 done** (5 m logistic regression; robust locally, not transferable; geology confound under review);
> local preliminary web prototype (`make web`, `make serve`). Results: [`validation/M4_BASELINE.md`](validation/M4_BASELINE.md),
> [`validation/M5_ADVANCED.md`](validation/M5_ADVANCED.md),
> [`validation/M6_UNCERTAINTY_TRANSFER.md`](validation/M6_UNCERTAINTY_TRANSFER.md). Plan: [`PLAN.md`](PLAN.md) · method draft:
> [`METHOD.md`](METHOD.md) · sources: [`DATA_SOURCES.md`](DATA_SOURCES.md).

**Question (spec §6):** can we build a spatially transferable landslide susceptibility model and show where its
predictions are reliable?

**Approach:**
- **Labels:** the NC Geological Survey inventory of Hurricane Helene (2024) initiation zones.
- **Terrain:** pre-event 3DEP lidar (2017).
- **Validation:** held-out watersheds, inside the area that Helene's rainfall actually tested.
- **Temporal check:** Watauga County (1940 storm → Helene), indicative only.

The output will be a **relative susceptibility ranking**, not hazard, risk or a probability of a future
landslide.

## Commands (run in this directory)
```
uv sync
make harvest        # small sources + DEM tiles -> data/raw, data/interim (about 21 GB transfer, ~2.5 h)
make feasibility    # validation-design feasibility -> validation/feasibility.json
make qa             # data QA -> validation/M1_DATA_QA.md
make prepare        # terrain (Rust), stack, hydrology, slope units, labels, unit tables, extra samples
make baseline       # logistic regression + leave-one-HUC-12-out validation -> validation/M4_BASELINE.md
make advanced       # gradient boosting, 5 m -> unit aggregation, candidates -> validation/M5_ADVANCED.md (~35 min)
make product        # final 5 m ranks + per-k held-out capture
make m6             # sensitivity, ensemble, area of applicability, trigger check, Watauga (~40 min)
make web            # web/data for the local prototype; then `make serve` (http://localhost:8138)
make bench          # Rust vs reference -> benchmarks/terrain_kernels.json
make test
```

`data/` is git-ignored. Provenance (URLs, checksums, service edit dates, lidar dates per tile) is written to
`provenance/harvest_manifest.json`.
