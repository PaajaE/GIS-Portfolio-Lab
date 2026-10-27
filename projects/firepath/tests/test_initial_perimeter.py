"""Mode A initial-perimeter semantics (METHOD.md, "Initial perimeter")."""

from math import hypot

import numpy as np
import pytest
from shapely import contains_xy
from shapely.geometry import Point, box
from shapely.ops import unary_union

from firepath.reference import BARRIER, INITIAL, REACHED, propagate, uniform_field

CELL = 30.0
R = 1.5  # m/min


def _inside(poly, n):
    """Cell-centre rule; geometry in cell units with x = column, y = row."""
    yy, xx = np.mgrid[0:n, 0:n]
    return contains_xy(poly, xx + 0.5, yy + 0.5)


def test_large_polygon_vs_independent_distance():
    n = 61
    disc = Point(30.0, 30.0).buffer(15.3, quad_segs=64)
    inside = _inside(disc, n)
    f = uniform_field((n, n), r_head=R)
    res = propagate(f, radius=2, inside=inside, t0=0.0)
    assert np.all(res.status[inside] == INITIAL) and np.all(res.arrival[inside] == 0.0)
    squares = unary_union([box(c, r, c + 1, r + 1) for r, c in zip(*np.nonzero(inside))])
    errs = []
    for r in range(n):
        for c in range(n):
            if inside[r, c]:
                continue
            p = Point(c + 0.5, r + 0.5)
            d_sq = squares.distance(p) * CELL / R
            t = res.arrival[r, c]
            # paths leave from the union of inside squares: never earlier than the distance to it
            assert t >= d_sq * (1 - 1e-9)
            assert t <= d_sq * 1.0276 + 1.0 * CELL / R
            d_true = disc.distance(p)
            if 5 <= d_true <= 12:
                errs.append(t * R / CELL - d_true)  # cells
    bias = float(np.mean(errs))
    # unbiased start at the raster boundary: mean error is the stencil excess (~1 % of 5-12 cells)
    # plus raster boundary noise; a centre-sourced start would add ~ +0.5 cell.
    assert -0.25 < bias < 0.3


def test_boundary_sources_only_is_equivalent():
    n = 41
    poly = Point(20, 20).buffer(9.2).union(box(20, 18.6, 34, 20.4))
    inside = _inside(poly, n)
    burn = np.ones((n, n), bool)
    burn[5:12, 25:28] = False
    f = uniform_field((n, n), r_head=R, burnable=burn)
    a = propagate(f, radius=2, inside=inside).arrival
    b = propagate(f, radius=2, inside=inside, boundary_sources_only=True).arrival
    assert np.array_equal(a, b)


def test_narrow_protrusion_one_cell_wide_is_a_source():
    n = 51
    poly = Point(15, 25).buffer(8.0).union(box(15, 25.0, 38.2, 26.0))  # covers row 25 centres to col 37
    inside = _inside(poly, n)
    assert inside[25, 37] and not inside[25, 38]
    res = propagate(uniform_field((n, n), r_head=R), radius=2, inside=inside)
    assert res.status[25, 37] == INITIAL
    # three cells beyond the tip: raster boundary at x=38, target centre x=40.5 -> 2.5 cells
    assert res.arrival[25, 40] == pytest.approx(2.5 * CELL / R, rel=1e-9)


def test_sub_cell_protrusion_is_lost_by_rasterization():
    n = 51
    finger = box(15, 25.55, 38.2, 25.95)  # 0.4 cell wide, contains no cell centre
    poly = Point(15, 25).buffer(8.0).union(finger)
    inside = _inside(poly, n)
    assert not inside[25, 37]
    res = propagate(uniform_field((n, n), r_head=R), radius=2, inside=inside)
    assert res.status[25, 37] == REACHED and res.arrival[25, 37] > 10 * CELL / R  # documented loss


def test_non_burnable_cells_at_the_initial_boundary_are_not_sources():
    n = 61
    inside = np.zeros((n, n), bool)
    inside[:, :21] = True                     # initial perimeter: columns 0-20
    burn = np.ones((n, n), bool)
    burn[20:41, 18:25] = False                # lake straddling the boundary (cols 18-24)
    res = propagate(uniform_field((n, n), r_head=R, burnable=burn), radius=2, inside=inside)
    assert np.all(res.status[20:41, 18:21] == BARRIER)
    # target just east of the lake centre: geodesic from the burnable inside squares around the lake
    # corner (25, 20) is 4 + hypot(0.5, 10.5) = 14.51 cells; a lake-hopping leak would give ~0.5 cell
    assert res.arrival[30, 25] >= (4 + hypot(0.5, 10.5)) * CELL / R * (1 - 1e-9)


def test_source_next_to_barrier_wall_cannot_jump_it():
    n = 41
    inside = np.zeros((n, n), bool)
    inside[:, :11] = True                     # perimeter edge at column 10
    burn = np.ones((n, n), bool)
    burn[:, 11] = False
    burn[5, 11] = True                        # single gap at row 5
    res = propagate(uniform_field((n, n), r_head=R, burnable=burn), radius=3, inside=inside)
    # through the gap: lower bound = straight distance from the gap exit (x=12, y in [5,6]) to the target
    lower = hypot(13.5 - 12.0, 30.5 - 6.0) * CELL / R
    assert res.arrival[30, 13] >= lower * (1 - 1e-9)
