# FirePath — local, reproducible pipeline (stages are added milestone by milestone; see PLAN.md §16).
# Requires: uv. `make probe` needs only python3 (standard library).
PY := uv run python -m firepath

.PHONY: setup probe test

setup:
	uv sync

probe:              ## M0: reachability / auth / inventory probe -> provenance/probe_<label>.json
	python3 src/firepath/probe.py --label $${LABEL:-build-mac}

test:               ## reference propagation fixtures, observation audit, inputs, probe crawler
	uv run pytest -q
