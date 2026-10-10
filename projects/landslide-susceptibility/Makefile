# Landslide Susceptibility — local, reproducible pipeline (M1 harvest ... M4 baseline).
# Requires: uv and a Rust toolchain (rust/ is built by `uv sync`). Later milestones add tippecanoe.
PY := uv run python -m landslide
# cargo is needed by `uv sync` (builds rust/) and `make test`; add the usual rustup locations.
export PATH := $(PATH):$(HOME)/.cargo/bin:/opt/homebrew/opt/rustup/bin

.PHONY: setup harvest harvest-small harvest-dem feasibility qa terrain stack hydro units labels aggregate samples prepare baseline bench test

setup:
	uv sync

harvest: harvest-small harvest-dem   ## everything into data/raw + provenance/harvest_manifest.json

harvest-small:      ## boundaries, WBD, inventory snapshot, MRMS, geology, NLCD/canopy, SSURGO, roads, buildings
	$(PY).harvest small

harvest-dem:        ## 3DEP 1 m tiles -> 5 m block means (download, aggregate, delete), mosaics, tile metadata
	$(PY).harvest dem
	$(PY).harvest dem-dates

feasibility:        ## clustering, rainfall confounding, Watauga overlap -> validation/feasibility.json
	$(PY).feasibility

qa:                 ## data QA report -> validation/M1_DATA_QA.md
	$(PY).qa

terrain:            ## Rust terrain kernels on the 5 m DEM mosaics -> data/interim/terrain_<region>/*.tif
	$(PY).terrain

stack:              ## NLCD, canopy, rainfall, geology, soils onto the 5 m grid -> data/interim/stack_<region>
	$(PY).stack

hydro:              ## 10 m D8, contributing area, HAND, distance to channel -> data/interim/hydro_<region>
	$(PY).hydro

units:              ## half-basin slope units at 0.05 / 0.1 / 0.2 km2 -> data/interim/units_aoi
	$(PY).units

labels:             ## positives, exclusions, domain, sample tables, modifier audit, density -> data/interim/labels_aoi
	$(PY).labels

aggregate:          ## slope-unit predictor tables -> data/out/units_<A>.parquet
	$(PY).aggregate

samples:            ## unrestricted domain sample + runoff-variant positive cells for the M4 checks
	$(PY).samples

prepare: terrain stack hydro units labels aggregate samples   ## M2-M3 stages in order

baseline:           ## M4 logistic regression + spatial validation -> validation/m4_baseline.json, M4_BASELINE.md
	$(PY).baseline

bench:              ## Rust vs reference timing at several sizes -> benchmarks/terrain_kernels.json
	$(PY).bench

test:
	uv run pytest -q
	cd rust && cargo test -q
