# Parcel Intelligence — local, reproducible pipeline.
# Requires: uv, a Rust toolchain (cargo), tippecanoe (for `make tiles`).
PY := uv run python -m parcel_intel

.PHONY: all setup harvest prepare analyze access validate bench tiles web test serve

all: prepare analyze access validate web

setup:
	uv sync

harvest:            ## download sources for the AOI (data/raw), write provenance manifest
	$(PY).harvest

prepare:            ## project, validate, grid, DEM -> slope, parcel raster
	$(PY).prepare

analyze:            ## scenarios, baselines, leave-one-out, sensitivity
	$(PY).analyze

access:             ## patch polygons, frontage, road distance, sewer; final parcels.parquet
	$(PY).access

validate:           ## kernel equality, rasterization vs GEOS, assessor comparison, figures
	$(PY).validate

bench:              ## Rust vs reference timing at several sizes
	$(PY).bench

web:                ## web artifacts (PMTiles, JSON, images) into web/data
	$(PY).export

test:
	uv run pytest -q
	cd rust && cargo test -q

serve:
	npx --yes http-server@14.1.1 web -p 8137 -c-1   # needs HTTP Range support for PMTiles
