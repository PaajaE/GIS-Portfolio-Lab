"""Rust graph kernel vs the Python reference (oracle). Tolerance PLAN §12: |dt| <= 1e-9 * max(1, t) and
identical status."""

import numpy as np
import pytest

from firepath.kernels import propagate_graph
from firepath.reference import propagate, uniform_field


def _check(f, radius, **kw):
    a = propagate(f, radius=radius, **kw)
    b = propagate_graph(f, radius=radius, **kw)
    assert np.array_equal(a.status, b.status)
    fin = np.isfinite(a.arrival)
    assert np.array_equal(fin, np.isfinite(b.arrival))
    assert np.all(np.abs(a.arrival[fin] - b.arrival[fin]) <= 1e-9 * np.maximum(1.0, np.abs(a.arrival[fin])))


@pytest.mark.parametrize("seed", range(50))
def test_random_heterogeneous_grids_match_reference(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(12, 25))
    burn = rng.random((n, n)) > 0.12
    terrain = {"tan_slope": rng.uniform(0, 0.7, (n, n)), "upslope": rng.uniform(-3, 3, (n, n))} if seed % 2 else {}
    f = uniform_field((n, n), r_head=1.0, ecc=0.0, theta=0.0, t_change=[15.0, 40.0], burnable=burn, cell_m=30.0,
                      **terrain)
    f.r_head[:] = rng.uniform(0.3, 3.0, f.r_head.shape)
    f.ecc[:] = rng.uniform(0.0, 0.9, f.ecc.shape)
    f.theta[:] = rng.uniform(-np.pi, np.pi, f.theta.shape)
    radius = (1, 2, 8)[seed % 3]
    r0, c0 = n // 2, n // 2
    burn[r0 - 1:r0 + 2, c0 - 1:c0 + 2] = True
    inside = np.zeros((n, n), bool)
    inside[r0 - 1:r0 + 2, c0 - 1:c0 + 2] = True
    _check(f, radius, inside=inside, t_stop=300.0)
    _check(f, radius, points=[(r0, c0, 5.0), (1, 1, 0.0)] if burn[1, 1] else [(r0, c0, 5.0)], t_stop=1e9)


def test_seeded_hybrid_style_run_matches():
    rng = np.random.default_rng(42)
    n = 20
    f = uniform_field((n, n), r_head=1.5, ecc=0.6, theta=0.5, cell_m=30.0)
    seed = np.where(rng.random((n, n)) < 0.3, rng.uniform(10, 300, (n, n)), np.inf)
    inside = np.zeros((n, n), bool)
    inside[9:11, 9:11] = True
    _check(f, 8, inside=inside, seed=seed)


def test_ignition_on_barrier_raises():
    f = uniform_field((4, 4), r_head=1.0, burnable=np.array([[1, 0, 1, 1]] * 4, bool))
    with pytest.raises(ValueError):
        propagate_graph(f, 1, points=[(0, 1, 0.0)])


@pytest.mark.parametrize("seed", range(50))
def test_rust_levelset_bit_identical_to_reference(seed):
    """Rust level-set loop vs the NumPy reference: identical arrivals (both use the same tie rule for
    the extension-velocity source: nearest interface point, ties -> lowest point index)."""
    from firepath.levelset import propagate_levelset

    rng = np.random.default_rng(100 + seed)
    n = int(rng.integers(30, 60))
    burn = rng.random((n, n)) > 0.08
    terrain = {"tan_slope": rng.uniform(0, 0.5, (n, n)), "upslope": rng.uniform(-3, 3, (n, n))} if seed % 2 else {}
    f = uniform_field((n, n), r_head=1.0, ecc=0.5, theta=0.7, t_change=[30.0, 60.0, 90.0], burnable=burn,
                      cell_m=30.0, **terrain)
    f.r_head[:] = rng.uniform(0.5, 3.0, f.r_head.shape)
    f.ecc[:] = rng.uniform(0.0, 0.85, f.ecc.shape)
    inside = np.zeros((n, n), bool)
    inside[n // 2 - 2:n // 2 + 2, n // 2 - 2:n // 2 + 2] = True
    burn[inside] = True
    a = propagate_levelset(f, inside=inside, t_stop=150.0, order=5)
    b = propagate_levelset(f, inside=inside, t_stop=150.0, order=5, backend="rust")
    assert np.array_equal(a.status, b.status)
    fin = np.isfinite(a.arrival)
    assert np.array_equal(a.arrival[fin], b.arrival[fin])
