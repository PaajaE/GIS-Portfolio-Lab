# FirePath — local, reproducible pipeline (stages are added milestone by milestone; see PLAN.md §16).
# Requires: uv. `make probe` needs only python3 (standard library).
PY := uv run python -m firepath

.PHONY: setup probe test bakeoff

setup:
	uv sync

probe:              ## M0: reachability / auth / inventory probe -> provenance/probe_<label>.json
	python3 src/firepath/probe.py --label $${LABEL:-build-mac}

test:               ## reference propagation fixtures, observation audit, inputs, probe crawler
	uv run pytest -q

bakeoff:            ## M1a D1 bake-off (analytic fixtures; ~1 h in pure Python) -> validation/m1a_bakeoff_*.json
	for s in levelset levelset5 dijkstra_r8 dijkstra_r2; do $(PY).bakeoff $$s; done
	$(PY).bakeoff combine
