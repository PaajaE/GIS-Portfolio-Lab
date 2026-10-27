"""Scenario results are bit-identical across thread counts (M2 exit criterion)."""

import numpy as np

from firepath.ensemble import run_many
from firepath.reference import uniform_field


def _fields(k, n=40):
    out = []
    for s in range(k):
        rng = np.random.default_rng(500 + s)
        burn = rng.random((n, n)) > 0.08
        f = uniform_field((n, n), r_head=1.0, ecc=0.5, theta=0.3, t_change=[40.0, 80.0], burnable=burn,
                          cell_m=30.0, tan_slope=rng.uniform(0, 0.5, (n, n)), upslope=rng.uniform(-3, 3, (n, n)))
        f.r_head[:] = rng.uniform(0.5, 3.0, f.r_head.shape)
        f.ecc[:] = rng.uniform(0.0, 0.85, f.ecc.shape)
        burn[n // 2 - 2:n // 2 + 2, n // 2 - 2:n // 2 + 2] = True
        out.append(f)
    return out


def test_bit_identical_across_thread_counts():
    n = 40
    inside = np.zeros((n, n), bool)
    inside[n // 2 - 2:n // 2 + 2, n // 2 - 2:n // 2 + 2] = True
    fs = _fields(8, n)
    ref = run_many(fs, workers=1, inside=inside, t_stop=200.0)
    for w in (2, 4, 10):
        got = run_many(fs, workers=w, inside=inside, t_stop=200.0)
        for a, b in zip(ref, got):
            assert np.array_equal(a.arrival, b.arrival) and np.array_equal(a.status, b.status)
