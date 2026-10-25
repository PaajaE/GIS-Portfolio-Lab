# FirePath — local, reproducible pipeline (stages are added milestone by milestone; see PLAN.md §16).
# Requires: uv. `make probe` needs only python3 (standard library).
PY := uv run python -m firepath

.PHONY: setup env probe harvest test bakeoff

setup:
	uv sync

env:                ## create the git-ignored .env from .env.example (keeps an existing .env)
	@test -f .env && echo ".env exists, not overwritten" || (cp .env.example .env && echo "created .env: fill in FIRMS_MAP_KEY")

probe:              ## M0: reachability / auth / inventory probe -> provenance/probe_<label>.json
	python3 src/firepath/probe.py --label $${LABEL:-build-mac}

harvest:            ## M1b raw inputs + provenance/harvest_<fire>.json (FIRE=mangum; STEPS optional)
	uv run python -m firepath.harvest $${FIRE:-mangum} $(STEPS)

test:               ## reference propagation fixtures, observation audit, inputs, probe crawler
	uv run pytest -q

bakeoff:            ## M1a D1 bake-off (analytic fixtures; ~1 h in pure Python) -> validation/m1a_bakeoff_*.json
	for s in levelset levelset5 dijkstra_r8 dijkstra_r2; do $(PY).bakeoff $$s; done
	$(PY).bakeoff combine
