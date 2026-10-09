# Landslide Susceptibility — local, reproducible pipeline (M1: harvest + data QA).
# Requires: uv and a Rust toolchain (rust/ is built by `uv sync`). Later milestones add tippecanoe.
PY := uv run python -m landslide
# cargo is needed by `uv sync` (builds rust/) and `make test`; add the usual rustup locations.
export PATH := $(PATH):$(HOME)/.cargo/bin:/opt/homebrew/opt/rustup/bin

.PHONY: setup harvest harvest-small harvest-dem feasibility qa terrain bench test

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

bench:              ## Rust vs reference timing at several sizes -> benchmarks/terrain_kernels.json
	$(PY).bench

test:
	uv run pytest -q
	cd rust && cargo test -q
