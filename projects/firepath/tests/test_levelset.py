"""Level-set candidate (D1 option B): analytic accuracy, wind change, barriers, Mode A."""

from math import hypot

import numpy as np
import pytest
from shapely import contains_xy
from shapely.geometry import Point

from firepath.bakeoff import t_ref_disc
from firepath.ellipse import eccentricity
from firepath.levelset import propagate_levelset
from firepath.reference import BARRIER, INITIAL, NOT_REACHED, propagate, uniform_field

CELL = 30.0


def test_isotropic_disc_growth_is_accurate():
    n, src = 61, (30, 30)
    res = propagate_levelset(uniform_field((n, n), r_head=1.0), points=[(*src, 0.0)], t_stop=900)
    for r, c in [(30, 50), (10, 30), (16, 44), (44, 16)]:
        d = hypot(r - src[0], c - src[1])
        exact = (d - 2.0) * CELL
        assert res.arrival[r, c] == pytest.approx(exact, rel=0.03)


@pytest.mark.parametrize("order, tol", [(2, 0.07), (5, 0.02)])
@pytest.mark.parametrize("wind_deg", [0.0, 22.5, 45.0])
def test_elliptical_growth_within_bakeoff_tolerance(wind_deg, order, tol):
    n, src = 81, (60, 20)
    ecc, th = float(eccentricity(4.0)), np.radians(wind_deg)
    res = propagate_levelset(uniform_field((n, n), r_head=1.0, ecc=ecc, theta=th), points=[(*src, 0.0)],
                             t_stop=1800, order=order)
    worst = 0.0
    for r in range(0, n, 3):
        for c in range(0, n, 3):
            dx, dy = (c - src[1]) * CELL, -(r - src[0]) * CELL
            if hypot(dx, dy) < 20 * CELL or not np.isfinite(res.arrival[r, c]):
                continue
            if abs(np.angle(np.exp(1j * (np.arctan2(dy, dx) - th)))) > np.pi / 2:
                continue
            worst = max(worst, abs(res.arrival[r, c] / t_ref_disc(dx, dy, 2 * CELL, ecc, th) - 1))
    assert worst < tol


def test_strip_two_fuels_wind_change():
    """Strip as in the label-setting fixture, ignition disc 2 cells (front at x = 60 m at t = 0).
    Hand-computed: A at 1 m/min to X(45)=105; A at 3 m/min to 135 at t=55; B at 0.5 m/min after."""
    f = uniform_field((1, 30), r_head=1.0, t_change=[45.0])
    f.r_head[0, :, :5], f.r_head[1, :, :5] = 1.0, 3.0
    f.r_head[0, :, 5:], f.r_head[1, :, 5:] = 2.0, 0.5
    res = propagate_levelset(f, points=[(0, 0, 0.0)], r0_cells=2.0, t_stop=400)
    assert res.arrival[0, 3:9] == pytest.approx([30.0, 50.0, 85.0, 145.0, 205.0, 265.0], abs=4.0)


def test_sub_cell_ignition_is_erased_by_numerical_viscosity():
    """Documented limitation: an ignition smaller than ~1 cell vanishes (Lax-Friedrichs viscosity)."""
    f = uniform_field((11, 11), r_head=1.0)
    res = propagate_levelset(f, points=[(5, 5, 0.0)], r0_cells=0.3, t_stop=1000, first_order=True)
    assert np.isinf(res.arrival[5, 7])


@pytest.mark.parametrize("order", [2, 5])
@pytest.mark.parametrize("cell, max_late", [(30.0, 0.15), (15.0, 0.05)])
def test_fuel_contrast_delay_is_first_order(cell, max_late, order):
    """Documented limitation: fast->slow contrast delays the level-set front by ~0.8 cell of slow-fuel
    travel time (exact answer 735 min; label-setting is exact on the cell-face-aligned case)."""
    n = int(600 / cell) + 1
    f = uniform_field((1, n), r_head=1.0, cell_m=cell)
    f.r_head[0, 0, np.arange(n) * cell > 135] = 0.25
    res = propagate_levelset(f, points=[(0, 0, 0.0)], r0_cells=60 / cell, t_stop=2000, order=order)
    late = res.arrival[0, int(round(300 / cell))] / 735.0 - 1
    assert 0.0 < late < max_late


@pytest.mark.parametrize("scheme", ["levelset", "levelset5", "dijkstra"])
def test_thin_walls_do_not_leak(scheme):
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
        f = uniform_field((n, n), r_head=1.0, ecc=float(eccentricity(4.0)), theta=0.3, burnable=burn)
        if scheme.startswith("levelset"):
            res = propagate_levelset(f, points=[(20, 8, 0.0)], t_stop=6000, order=5 if scheme == "levelset5" else 2)
        else:
            res = propagate(f, radius=8, points=[(20, 8, 0.0)], t_stop=6000)
        assert np.all(res.status[far & burn] == NOT_REACHED), (scheme, wall)
        assert np.all(res.status[~burn] == BARRIER)


@pytest.mark.parametrize("order", [2, 5])
def test_levelset_mode_a_disc(order):
    n = 61
    disc = Point(30.0, 30.0).buffer(12.3, quad_segs=64)
    yy, xx = np.mgrid[0:n, 0:n]
    inside = contains_xy(disc, xx + 0.5, yy + 0.5)
    res = propagate_levelset(uniform_field((n, n), r_head=1.5), inside=inside, t_stop=600, order=order)
    assert np.all(res.status[inside] == INITIAL)
    errs = [res.arrival[r, c] * 1.5 / CELL - disc.distance(Point(c + 0.5, r + 0.5))
            for r in range(n) for c in range(n)
            if not inside[r, c] and 4 <= disc.distance(Point(c + 0.5, r + 0.5)) <= 10]
    assert abs(float(np.mean(errs))) < 0.6 and float(np.max(np.abs(errs))) < 1.2


def test_levelset_deterministic():
    f = uniform_field((31, 31), r_head=1.0, ecc=0.7, theta=0.4)
    a = propagate_levelset(f, points=[(15, 15, 0.0)], t_stop=300).arrival
    b = propagate_levelset(f, points=[(15, 15, 0.0)], t_stop=300).arrival
    assert np.array_equal(a, b)


@pytest.mark.parametrize("order", [2, 5])
def test_levelset_passes_one_cell_gap_but_is_late(order):
    """Zero-flux barrier faces let the front through a one-cell gap (it choked without them); the
    remaining lateness behind the gap (~10-25 %) is why the level set fails bake-off criterion 4."""
    import sys
    sys.path.insert(0, "tests")
    from shapely.geometry import box
    import test_propagation_fixtures as T

    n, col, gap = 25, 12, 18
    burn = np.ones((n, n), bool)
    burn[:, col] = False
    burn[gap, col] = True
    res = propagate_levelset(uniform_field((n, n), r_head=1.0, burnable=burn), points=[(5, 4, 0.0)],
                             t_stop=5000, order=order)
    walls = [box(col, 0, col + 1, gap), box(col, gap + 1, col + 1, n)]
    corners = [(col, gap), (col + 1, gap), (col, gap + 1), (col + 1, gap + 1)]
    rel = []
    for r in range(0, n, 2):
        for c in range(col + 1, n):
            geo = (T._geodesic((4.5, 5.5), (c + 0.5, r + 0.5), walls, corners) - 2.0) * CELL
            rel.append(res.arrival[r, c] / geo - 1)
    assert np.all(np.isfinite(rel))
    assert 0.05 < min(rel) and max(rel) < 0.30
