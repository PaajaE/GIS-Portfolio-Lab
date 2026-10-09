# Landslide Susceptibility — local, reproducible pipeline (M1: harvest + data QA).
# Requires: uv. Later milestones add a Rust toolchain (rust/) and tippecanoe.
PY := uv run python -m landslide

.PHONY: setup harvest harvest-small harvest-dem feasibility qa test

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

test:
	uv run pytest -q
