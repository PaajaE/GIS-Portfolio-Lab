"""Scenario parallelism (M2): independent propagations (calibration candidates, ensemble members) on a
thread pool. The Rust kernels release the GIL (py.detach), so threads run them concurrently; every
scenario is computed by the same deterministic code on its own inputs, so the results cannot depend on
the number of threads or the scheduling (tested in tests/test_ensemble.py). No Rayon: one run is a
sequential label-setting / time-stepping loop, and the parallelism needed is across runs.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from .levelset import propagate_hybrid


def run_many(fields, *, workers: int | None = None, **kw):
    """propagate_hybrid(f, **kw) for each SpreadField in `fields`, results in input order."""
    workers = workers or int(os.environ.get("FIREPATH_THREADS", os.cpu_count() or 1))
    if workers == 1:
        return [propagate_hybrid(f, **kw) for f in fields]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(lambda f: propagate_hybrid(f, **kw), fields))
