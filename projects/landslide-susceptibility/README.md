# Landslide Susceptibility — Buncombe + Yancey, NC

> Status (2026-10-24): **finished on the simple path — a local experiment.** The 5 m logistic-regression ranking is
> robust inside Buncombe + Yancey, does **not** transfer beyond them, and is distorted across geology boundaries.
> Exposure is skipped. Static web app in [`web/`](web/) (`make serve`). Results:
> [`validation/M4_BASELINE.md`](validation/M4_BASELINE.md), [`validation/M5_ADVANCED.md`](validation/M5_ADVANCED.md),
> [`validation/M6_UNCERTAINTY_TRANSFER.md`](validation/M6_UNCERTAINTY_TRANSFER.md),
> [`validation/NOGEO_TEST.md`](validation/NOGEO_TEST.md). Plan: [`PLAN.md`](PLAN.md) · method:
> [`METHOD.md`](METHOD.md) · sources: [`DATA_SOURCES.md`](DATA_SOURCES.md).

**Question (spec §6):** can we build a spatially transferable landslide susceptibility model and show where its
predictions are reliable?

**Approach:**
- **Labels:** the NC Geological Survey inventory of Hurricane Helene (2024) initiation zones.
- **Terrain:** pre-event 3DEP lidar (2017).
- **Validation:** held-out watersheds, inside the area that Helene's rainfall actually tested.
- **Temporal check:** Watauga County (1940 storm → Helene), indicative only.

Open items, analytical next steps and the cloud/local split: [`FUTURE_WORK.md`](FUTURE_WORK.md).

The output is a **relative susceptibility ranking** of hillslopes for the initiation of shallow landslides, not hazard,
risk or a probability of a future landslide.

## Result and limits (what the evidence supports)
- **Inside the area:** in watersheds the model never saw (leave-one-HUC-12-out, inside the rainfall that Helene
  actually delivered), flagging the top 10 % of hillslope area captured 59 % of mapped Helene initiation sites
  (95 % interval 48–69 %). The 5 m model beats slope alone (AUC +0.06; M4). Gradient boosting was not detectably better (M5).
- **Beyond the area:** it does not transfer. Leave-one-county-out AUC 0.68 is below slope alone, and the Watauga
  1940 → 2024 check gives 0.50 (indicative only; different mapping method). The geology terms encode the rainfall
  gradient; removing them failed the pre-registered rule (`validation/NOGEO_TEST.md`), so the model is kept as
  a **local experiment** and its top 10 % over-represents one rock-type group.
- **Labels are mapped initiation, not true absence.** One storm (Helene, 2024-09-27), pre-event 2017 lidar, shallow
  initiation only (no run-out, deep-seated or road-related failures). A flagged slope without a mapped failure is
  not a false positive.
- **Not done:** exposure (skipped by the owner), human review of the hand-check sample
  (`validation/hand_check_sample.csv`: 40 frozen locations, no reviewer yet), external reference product, and a
  transferable trigger-based model. See [`FUTURE_WORK.md`](FUTURE_WORK.md).
- **Imagery** in the app (four 2 km × 2 km sites at 1 m, before/after Helene) is display only and never a model
  input; credits and the licence check are in `DATA_SOURCES.md`.

## Running the app
```
make serve          # http://localhost:8138 (static; HTTP Range for PMTiles)
```
`web/data/` (PMTiles, GeoJSON, `summary.json`, site images; about 36 MB) is committed. Regenerating it needs `data/`
(`make data-restore`, then `make web`, then `python -m landslide.m7` for the site images). The public site is
assembled by `.github/workflows/pages.yml` at `/landslide-susceptibility/`.

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

### Data on a new machine or in a cloud session
`data/` is not in git. The inputs that cannot be re-harvested identically (see `data_bundle.txt`) are kept as a
private release of `PaajaE/GIS-Portfolio-Lab-data` (needs `gh` logged in with access):
```
uv sync
make data-restore   # latest bundle -> data/, sha256 verified; then the make targets rebuild the rest
make data-pack      # after a re-harvest: new dated release
```
