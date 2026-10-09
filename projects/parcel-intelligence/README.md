# Parcel Intelligence — Amherst, MA

**Given a parcel and stated planning assumptions, how much of it remains potentially feasible, which
constraints dominate, and how robust is that conclusion?** (spec §5)

A spatial screen of 6,091 Amherst parcels against FEMA flood zones, MassDEP wetlands and streams,
protected open space, NHESP priority habitat, lidar slope, a lot-line setback and existing development,
under three explicit assumption sets. Per parcel it reports the *largest contiguous potentially feasible
patch*, whether it qualifies (≥ 500 m²), a robustness class across the scenarios, vacant vs built, the
constraint breakdown and the binding site constraint. On built parcels the patch is mostly the yard beside
the building, so results are split and the vacant figures lead (moderate: 314 of 612 screened vacant
parcels qualify). Hand checks are AI-assisted and **pending human review** ([`validation/HAND_CHECKS.md`](validation/HAND_CHECKS.md)).
Result wording: *potential feasibility under stated spatial screening assumptions* — not entitlement.

- Method, validation, sensitivity, Rust benchmark, limitations: [`METHOD.md`](METHOD.md)
- Sources, licences, vintages, checksums: [`DATA_SOURCES.md`](DATA_SOURCES.md), [`provenance/`](provenance/)
- Web app: [`web/`](web/) · hand-check figures: [`validation/figures/`](validation/figures/)

## Run it

Requirements: [uv](https://docs.astral.sh/uv/), a Rust toolchain (`cargo` on PATH; the Makefile also looks in `~/.cargo/bin` and Homebrew's rustup), `tippecanoe` (vector tiles), Node (`npx`) for the dev server.

```bash
uv sync            # Python 3.13 env + builds the Rust extension (rust/, PyO3 via maturin)
make harvest       # download sources for the AOI into data/raw (≈300 MB), write provenance manifest
make all           # prepare → analyze → access → validate → web artifacts
make bench         # Rust vs SciPy reference benchmark → benchmarks/patch_kernel.json
make test          # pytest (unit + fixture + output assertions) and cargo test
make serve         # http://localhost:8137 (needs HTTP Range support for PMTiles)
```

A full `make all` takes about 1.5–2 minutes on an Apple M4. `data/` is not committed; `web/data/` is the
published, derived output.

## Layout

```text
src/parcel_intel/   config (all assumptions) · harvest · prepare · analyze · access · validate · export · bench
                    patches.py = SciPy reference for the Rust kernel
rust/               parcel_kernels: per-parcel opening + connected components (PyO3)
tests/              kernel vs reference, slope, stage-boundary checks on real outputs
web/                static MapLibre app (index.html, app.js, style.css, data/)
```

## Output schema — `data/out/parcels.parquet` (also `web/data/downloads/`)

GeoParquet, EPSG:26986, one row per parcel. Suffix `_con` / `_mod` / `_agg` = scenario.

| Column | Meaning (units) |
|---|---|
| `pid`, `loc_id`, `map_par_id` | internal index, MassGIS parcel id, assessor map-parcel id |
| `site_addr`, `use_code`, `use_desc`, `zoning`, `zone_district`, `year_built`, `is_condo`, `any_exempt`, `n_records`, `total_val` | assessor attributes (representative record) |
| `area_m2` | vector parcel area (m²) |
| `eligible_*` | land-use eligibility (tax-exempt never; Chapter 61 not in conservative) |
| `naive_m2_*` | naive parcel-level screen: whole parcel or 0 (m²) |
| `net_m2_*` | net unconstrained area, no contiguity (m²) |
| `cleaned_m2_*` | feasible area after the 10 m opening (m²) |
| `largest_m2_*` | **largest contiguous potentially feasible patch** (m²) |
| `n_patches_*` | patches ≥ 500 m² |
| `qualifying_*` | eligible and largest patch ≥ 500 m² (a *qualifying patch*) |
| `has_building`, `vacant_land_code`, `vacant` | mapped building footprint in parcel · assessor vacant-land class 13x/39x/44x · vacant = no building or vacant-land class |
| `c_<constraint>_m2_*` | parcel area under each constraint category (m², categories overlap) |
| `relief_<constraint>_m2` | gain in moderate largest patch if that constraint alone is dropped (m²) |
| `binding_constraint_mod`, `dominant_constraint_mod` | site constraint with the largest relief (setback and existing development excluded) / category with the largest area |
| `robustness` | robust · assumption-dependent · only aggressive · constrained · not screened |
| `slope_mean_pct`, `slope_p90_pct`, `slope_max_pct` | slope statistics over parcel cells (%) |
| `frontage_public_m`, `frontage_any_m` | parcel boundary within 12 m of a public / any road centreline (m) |
| `nearest_road_class`, `nearest_road_name` | MassDOT class and name of the nearest road |
| `patch_road_dist_m_mod` | straight-line distance, moderate largest patch → road centreline (m) |
| `sewer_share` | share of parcel area in the Amherst sewer service area (0–1) |

Owner names and owner addresses are not harvested or published.
