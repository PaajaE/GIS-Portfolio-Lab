"""M1a-2: seeded label-setting, hybrid barrier fixtures (E3), mosaic set-up and scoring (E1)."""

import sys
from math import hypot

import numpy as np
import pytest
from shapely.geometry import box

from firepath.levelset import propagate_hybrid, propagate_levelset
from firepath.mosaic import N, build, fuel_map, stats
from firepath.reference import NOT_REACHED, propagate, uniform_field

sys.path.insert(0, "tests")
import test_propagation_fixtures as T  # noqa: E402

CELL = 30.0


def test_seeded_graph_is_min_of_seed_and_paths():
    f = uniform_field((21, 21), r_head=1.0)
    plain = propagate(f, radius=2, points=[(10, 10, 0.0)]).arrival
    seed = np.full((21, 21), np.inf)
    seed[10, 10] = 0.0
    seed[0, 0] = 5.0                         # an earlier label far away
    s = propagate(f, radius=2, seed=seed).arrival
    assert s[10, 10] == 0.0 and s[0, 0] == 5.0
    assert np.all(s <= plain + 1e-9)
    late = plain + 100.0                     # seeds that are all later than the true solution change nothing
    late[10, 10] = 0.0
    assert np.allclose(propagate(f, radius=2, seed=late).arrival, plain)


def test_hybrid_one_cell_gap_meets_e3():
    n, col, gap = 25, 12, 18
    burn = np.ones((n, n), bool)
    burn[:, col] = False
    burn[gap, col] = True
    res = propagate_hybrid(uniform_field((n, n), r_head=1.0, burnable=burn), points=[(5, 4, 0.0)],
                           t_stop=5000)
    walls = [box(col, 0, col + 1, gap), box(col, gap + 1, col + 1, n)]
    corners = [(col, gap), (col + 1, gap), (col, gap + 1), (col + 1, gap + 1)]
    for r in range(0, n, 2):
        for c in range(col + 1, n):
            geo = (T._geodesic((4.5, 5.5), (c + 0.5, r + 0.5), walls, corners) - 2.0) * CELL
            assert geo * 0.99 <= res.arrival[r, c] <= geo * 1.0276 + 2 * CELL


def test_hybrid_lake_meets_e3():
    n = 61
    inside = np.zeros((n, n), bool)
    inside[:, :21] = True
    burn = np.ones((n, n), bool)
    burn[20:41, 18:25] = False
    res = propagate_hybrid(uniform_field((n, n), r_head=1.5, burnable=burn), inside=inside, t_stop=3000)
    geo = (4 + hypot(0.5, 10.5)) * CELL / 1.5
    assert geo * 0.99 <= res.arrival[30, 25] <= geo * 1.0276 + 2 * CELL / 1.5


@pytest.mark.parametrize("scheme", ["levelset5", "hybrid"])
def test_no_leaks_through_thin_walls(scheme):
    n = 41
    for wall in ("straight", "diagonal"):
        burn = np.ones((n, n), bool)
        if wall == "straight":
            burn[:, 20] = False
            far = np.zeros((n, n), bool)
            far[:, 21:] = True
        else:
            for r in range(n):
                burn[r, n - 1 - r] = False
            far = np.add.outer(np.arange(n), np.arange(n)) > n - 1
        f = uniform_field((n, n), r_head=1.0, ecc=0.8, theta=0.3, burnable=burn)
        prop = propagate_hybrid if scheme == "hybrid" else propagate_levelset
        kw = {} if scheme == "hybrid" else {"order": 5}
        res = prop(f, points=[(20, 8, 0.0)], t_stop=6000, **kw)
        assert np.all(res.status[far & burn] == NOT_REACHED)


def test_mosaic_map_and_refinement_are_consistent():
    m = fuel_map()
    assert m.shape == (N, N) and 0.45 < m.mean() < 0.55
    assert np.array_equal(m, fuel_map())                      # seeded
    fc, ic = build("lb2", 1)
    ff, iff = build("lb2", 3)
    sub = slice(1, None, 3)
    assert np.array_equal(ff.r_head[0][sub, sub], fc.r_head[0])  # identical fuel at coincident centres
    assert ff.cell_m == 10.0 and np.isclose(iff.sum() / ic.sum(), 9, rtol=0.25)


def test_mosaic_scoring_handles_unreached_candidates():
    ref = np.array([[100.0, 200.0, 5000.0]])
    cand = np.array([[105.0, np.inf, 1.0]])
    mask = np.ones_like(ref, bool)
    s = stats(cand, ref, mask)               # ref 5000 > T_END is not scored
    assert s["n"] == 2 and s["max_abs"] == np.inf and not s["pass"]
