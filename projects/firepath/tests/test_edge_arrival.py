"""Edge-arrival function A_e(t): exact interval handling, FIFO, independent numerical check."""

import numpy as np
import pytest

from firepath.reference import SpreadField, edge_arrival, uniform_field
from firepath.stencil import stencil, traversal


def _random_field(rng, shape=(5, 5), h=6):
    t_change = np.cumsum(rng.uniform(1.0, 8.0, h - 1))
    r_head = rng.uniform(0.2, 5.0, (h, *shape))
    ecc = rng.uniform(0.0, 0.95, (h, *shape))
    theta = rng.uniform(-np.pi, np.pi, (h, *shape))
    return SpreadField(t_change, r_head, ecc, theta, np.ones(shape, bool), 30.0)


def _euler(f, r, c, tr, t_u, dt=1e-4):
    """Independent check: march along the segment with a tiny time step (no interval logic)."""
    seg = tr.length * f.cell_m
    bounds = np.cumsum([0.0] + [float(p[2]) * seg for p in tr.pieces])
    pos, t = 0.0, t_u
    while pos < seg:
        j = min(np.searchsorted(bounds, pos, side="right") - 1, len(tr.pieces) - 1)
        dr, dc, _ = tr.pieces[j]
        h, _ = f.interval(t)
        pos += f.speed(h, r + dr, c + dc, tr.phi) * dt
        t += dt
    return t


def test_matches_independent_time_marching():
    rng = np.random.default_rng(20261009)
    f = _random_field(rng)
    for dr, dc in [(0, 1), (1, 1), (1, 2), (2, -1)]:
        tr = traversal(dr, dc)
        for t_u in rng.uniform(0.0, 30.0, 3):
            exact = edge_arrival(f, 1, 1, tr, t_u)
            approx = _euler(f, 1, 1, tr, t_u)
            assert exact == pytest.approx(approx, abs=2e-3)


def test_fifo_on_random_fields():
    """A_e is strictly increasing in the departure time (no overtaking)."""
    rng = np.random.default_rng(7)
    for _ in range(20):
        f = _random_field(rng)
        for dr, dc in stencil(2):
            tr = traversal(dr, dc)
            ts = np.linspace(0.0, 45.0, 400)
            a = np.array([edge_arrival(f, 2, 2, tr, t) for t in ts])
            assert np.all(np.diff(a) > 0)
            assert np.all(a > ts)


def test_departure_exactly_on_a_boundary_uses_the_new_interval():
    f = uniform_field((1, 3), r_head=[1.0, 2.0], t_change=[10.0])
    tr = traversal(0, 1)
    assert edge_arrival(f, 0, 0, tr, 10.0) == pytest.approx(10.0 + 30.0 / 2.0)
    assert edge_arrival(f, 0, 0, tr, 0.0) == pytest.approx(10.0 + 20.0 / 2.0)  # 10 m, then 20 m at 2
