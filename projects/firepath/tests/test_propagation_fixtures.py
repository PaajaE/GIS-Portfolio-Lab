"""Full-propagation fixtures with independently computed answers (METHOD.md, "Fixtures")."""

from math import cos, gcd, hypot, sin, sqrt

import numpy as np
import pytest
from shapely.geometry import LineString, box

from firepath.ellipse import eccentricity
from firepath.reference import BARRIER, NOT_REACHED, REACHED, propagate, uniform_field
from firepath.stencil import stencil, stencil_error, traversal

CELL = 30.0


# ---------------------------------------------------------------- 1-D strip: fuels + interval change

STRIP_CASES = [
    # t_change, expected arrival (min) at cells 0..6, hand-computed in the comment of each case
    # A: cells 0-4 (1 m/min, then 3), B: cells 5-9 (2 m/min, then 0.5); fuel face at 135 m.
    # change at 45: X(45)=45; then 3 m/min in A -> 135 at 75; then 0.5 in B.
    (45.0, [0.0, 30.0, 50.0, 60.0, 70.0, 105.0, 165.0]),
    # change at 125: A at 1 m/min to X=125 (t=125), A at 3 to 135 (t=128.333), B at 0.5 to 150.
    # The 4->5 edge contains both the interval change and the fuel change.
    (125.0, [0.0, 30.0, 60.0, 90.0, 120.0, 125.0 + 10.0 / 3.0 + 30.0, 125.0 + 10.0 / 3.0 + 90.0]),
]


@pytest.mark.parametrize("t_change, expected", STRIP_CASES)
def test_strip_two_fuels_wind_change_during_traversal(t_change, expected):
    shape = (1, 10)
    r = np.zeros((2, *shape))
    r[0, :, :5], r[1, :, :5] = 1.0, 3.0
    r[0, :, 5:], r[1, :, 5:] = 2.0, 0.5
    f = uniform_field(shape, r_head=1.0, t_change=[t_change])
    f.r_head[:] = r
    res = propagate(f, radius=2, points=[(0, 0, 0.0)])
    assert res.arrival[0, :7] == pytest.approx(expected, abs=1e-9)


# ---------------------------------------------------------------- homogeneous point source

def _gauge_isotropic(dr, dc, radius):
    """Lattice distance in a homogeneous isotropic medium: the stencil gauge, computed from the two
    Farey-adjacent stencil vectors that bracket the target (they form a unimodular basis)."""
    if (dr, dc) == (0, 0):
        return 0.0
    vecs = [(a, b) for a, b in stencil(radius)]
    best = np.inf
    for i, (a1, b1) in enumerate(vecs):
        for a2, b2 in vecs[i + 1:]:
            det = a1 * b2 - a2 * b1
            if det == 0:
                continue
            x = (dr * b2 - dc * a2) / det
            y = (a1 * dc - b1 * dr) / det
            if x >= -1e-12 and y >= -1e-12 and abs(x - round(x)) < 1e-9 and abs(y - round(y)) < 1e-9:
                best = min(best, x * hypot(a1, b1) + y * hypot(a2, b2))
    return best


def test_isotropic_point_source_equals_stencil_gauge_and_bounds():
    n = 31
    f = uniform_field((n, n), r_head=2.0)
    res = propagate(f, radius=2, points=[(15, 15, 0.0)])
    for r in range(n):
        for c in range(n):
            d = _gauge_isotropic(r - 15, c - 15, 2) * CELL / 2.0
            assert res.arrival[r, c] == pytest.approx(d, rel=1e-12, abs=1e-12)
            eu = hypot(r - 15, c - 15) * CELL / 2.0
            assert eu - 1e-9 <= res.arrival[r, c] <= eu * 1.0276 + 1e-9


def test_symmetry_and_determinism():
    n = 21
    f = uniform_field((n, n), r_head=1.3)
    a = propagate(f, radius=3, points=[(10, 10, 0.0)]).arrival
    b = propagate(f, radius=3, points=[(10, 10, 0.0)]).arrival
    assert np.array_equal(a, b)
    assert np.array_equal(a, a[::-1, :]) and np.array_equal(a, a[:, ::-1]) and np.array_equal(a, a.T)


def _continuum_point_ellipse(dx, dy, r_head, ecc, theta):
    if dx == 0 and dy == 0:
        return 0.0
    psi = np.arctan2(dy, dx) - theta
    return hypot(dx, dy) / (r_head * (1 - ecc) / (1 - ecc * cos(psi)))


@pytest.mark.parametrize("radius, lb, wind_deg", [(2, 2.0, 0.0), (2, 2.0, 13.0), (4, 2.0, 13.0)])
def test_uniform_wind_ellipse_vs_independent_graph_and_continuum(radius, lb, wind_deg):
    scipy_sparse = pytest.importorskip("scipy.sparse")
    from scipy.sparse.csgraph import dijkstra

    n, src = 41, (20, 8)
    ecc, theta = float(eccentricity(lb)), np.radians(wind_deg)
    f = uniform_field((n, n), r_head=1.0, ecc=ecc, theta=theta)
    res = propagate(f, radius=radius, points=[(*src, 0.0)])

    # (a) independent static graph oracle: same edges, weights from the closed-form ray speed
    rows, cols, w = [], [], []
    for r in range(n):
        for c in range(n):
            for dr, dc in stencil(radius):
                rv, cv = r + dr, c + dc
                if 0 <= rv < n and 0 <= cv < n:
                    phi = np.arctan2(-dr, dc)
                    s = (1 - ecc) / (1 - ecc * cos(phi - theta))
                    rows.append(r * n + c)
                    cols.append(rv * n + cv)
                    w.append(hypot(dr, dc) * CELL / s)
    g = scipy_sparse.csr_matrix((w, (rows, cols)), shape=(n * n, n * n))
    oracle = dijkstra(g, indices=src[0] * n + src[1]).reshape(n, n)
    assert res.arrival == pytest.approx(oracle, rel=1e-9)

    # (b) continuum ellipse: graph >= continuum (graph paths are physical paths), and the excess is
    # bounded by the asymptotic stencil error predicted geometrically
    pred = stencil_error(radius, lb, theta)["forward_max"]
    worst = 0.0
    for r in range(n):
        for c in range(n):
            dx, dy = (c - src[1]) * CELL, -(r - src[0]) * CELL
            tc = _continuum_point_ellipse(dx, dy, 1.0, ecc, theta)
            assert res.arrival[r, c] >= tc * (1 - 1e-9)
            psi = np.angle(np.exp(1j * (np.arctan2(dy, dx) - theta)))
            if hypot(dx, dy) >= 8 * CELL and abs(psi) <= np.pi / 2:
                worst = max(worst, res.arrival[r, c] / tc - 1)
    assert worst <= pred + 0.01


# ---------------------------------------------------------------- wind direction change (Minkowski)

def _support_focus_ellipse(nx, ny, r_head, ecc, theta):
    a = r_head / (1 + ecc)
    b = a * sqrt(1 - ecc * ecc)
    wx, wy = cos(theta), sin(theta)
    nw = nx * wx + ny * wy
    nperp = -nx * wy + ny * wx
    return a * ecc * nw + np.sqrt((a * nw) ** 2 + (b * nperp) ** 2)


def _continuum_two_winds(dx, dy, t1, ecc, th1, th2, r_head=1.0):
    """Earliest T with (dx, dy) in E1*min(T,t1) (+) E2*max(T-t1,0) (Minkowski sum, support functions)."""
    ang = np.linspace(-np.pi, np.pi, 4001)
    nx, ny = np.cos(ang), np.sin(ang)
    h1 = _support_focus_ellipse(nx, ny, r_head, ecc, th1)
    h2 = _support_focus_ellipse(nx, ny, r_head, ecc, th2)
    proj = nx * dx + ny * dy

    def inside(T):
        return np.all(proj <= h1 * min(T, t1) + h2 * max(T - t1, 0.0) + 1e-12)

    lo, hi = 0.0, 1.0
    while not inside(hi):
        hi *= 2
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (lo, mid) if inside(mid) else (mid, hi)
    return hi


def test_wind_direction_change_vs_minkowski_reference():
    n, src = 41, (20, 20)
    lb, t1 = 1.5, 150.0
    ecc = float(eccentricity(lb))
    f = uniform_field((n, n), r_head=1.0, ecc=ecc, theta=[0.0, np.pi / 2], t_change=[t1])
    res = propagate(f, radius=4, points=[(*src, 0.0)])
    worst = 0.0
    for r in range(0, n, 3):
        for c in range(0, n, 3):
            dx, dy = (c - src[1]) * CELL, -(r - src[0]) * CELL
            if hypot(dx, dy) < 8 * CELL:
                continue
            tc = _continuum_two_winds(dx, dy, t1, ecc, 0.0, np.pi / 2)
            assert res.arrival[r, c] >= tc * (1 - 1e-6)
            worst = max(worst, res.arrival[r, c] / tc - 1)
    assert worst < 0.05


# ---------------------------------------------------------------- barriers in full propagation

def test_one_cell_diagonal_wall_is_not_crossed():
    n = 21
    burn = np.ones((n, n), bool)
    for r in range(n):
        burn[r, n - 1 - r] = False  # anti-diagonal wall
    for radius in (1, 2, 3):
        f = uniform_field((n, n), r_head=1.0, burnable=burn)
        res = propagate(f, radius=radius, points=[(2, 2, 0.0)])
        far = np.add.outer(np.arange(n), np.arange(n)) > n - 1
        assert np.all(res.status[far] == NOT_REACHED)
        assert np.all(res.status[~burn] == BARRIER)


def _geodesic(p, q, obstacles, corners):
    """Shortest obstacle-avoiding Euclidean path p -> q via the given corner points (visibility graph)."""
    nodes = [p, q, *corners]

    interiors = [o.buffer(-1e-7, join_style="mitre") for o in obstacles]  # moving along an edge is allowed

    def visible(a, b):
        seg = LineString([a, b])
        return all(seg.intersection(o).length < 1e-9 for o in interiors)

    dist = {0: 0.0}
    todo = {i: np.inf for i in range(len(nodes))}
    todo[0] = 0.0
    while todo:
        i = min(todo, key=todo.get)
        d = todo.pop(i)
        if i == 1:
            return d
        for j in list(todo):
            if visible(nodes[i], nodes[j]):
                todo[j] = min(todo[j], d + hypot(nodes[i][0] - nodes[j][0], nodes[i][1] - nodes[j][1]))
    return np.inf


def test_wall_with_gap_lower_bounded_by_geodesic():
    n, col, gap = 25, 12, 18
    burn = np.ones((n, n), bool)
    burn[:, col] = False
    burn[gap, col] = True
    f = uniform_field((n, n), r_head=1.0, burnable=burn)
    src = (5, 4)
    res = propagate(f, radius=2, points=[(*src, 0.0)])
    walls = [box(col, 0, col + 1, gap), box(col, gap + 1, col + 1, n)]  # x, y in cell units
    corners = [(col, gap), (col + 1, gap), (col, gap + 1), (col + 1, gap + 1)]
    p = (src[1] + 0.5, src[0] + 0.5)
    for r in range(0, n, 2):
        for c in range(col + 1, n):
            geo = _geodesic(p, (c + 0.5, r + 0.5), walls, corners) * CELL
            assert res.arrival[r, c] >= geo * (1 - 1e-9)
            assert res.arrival[r, c] <= geo * 1.0276 + 2 * CELL


def test_ignition_on_barrier_is_an_error():
    burn = np.ones((5, 5), bool)
    burn[2, 2] = False
    f = uniform_field((5, 5), r_head=1.0, burnable=burn)
    with pytest.raises(ValueError):
        propagate(f, points=[(2, 2, 0.0)])


def test_empty_sources_reach_nothing():
    f = uniform_field((5, 5), r_head=1.0)
    res = propagate(f)
    assert np.all(res.status == NOT_REACHED) and np.all(np.isinf(res.arrival))


def test_t_stop_marks_late_cells_not_reached():
    f = uniform_field((1, 10), r_head=1.0)
    res = propagate(f, points=[(0, 0, 0.0)], t_stop=100.0)
    assert list(res.status[0]) == [REACHED] * 4 + [NOT_REACHED] * 6
    assert np.isinf(res.arrival[0, 4:]).all()


def test_gcd_helper_consistency():
    assert all(gcd(abs(a), abs(b)) == 1 for a, b in stencil(4))
    assert traversal(2, 1).length == pytest.approx(sqrt(5))
