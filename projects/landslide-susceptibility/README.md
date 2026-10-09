# Landslide Susceptibility — Buncombe + Yancey, NC

> Status: **M1 (harvest + data QA)**. No model, no app yet. Plan: [`PLAN.md`](PLAN.md) · method draft:
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
make test
```

`data/` is git-ignored. Provenance (URLs, checksums, service edit dates, lidar dates per tile) is written to
`provenance/harvest_manifest.json`.
