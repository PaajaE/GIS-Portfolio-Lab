"""Exact traversal tables and the transition (barrier) rule."""

from fractions import Fraction as F

import numpy as np
import pytest

from firepath.stencil import edge_valid, stencil, stencil_error, traversal


def test_stencil_sizes():
    assert len(stencil(1)) == 8
    assert len(stencil(2)) == 16
    assert len(stencil(3)) == 32


def test_straight_move():
    t = traversal(0, 1)
    assert t.pieces == ((0, 0, F(1, 2)), (0, 1, F(1, 2)))
    assert t.vertex_sides == ()


def test_diagonal_move_passes_through_vertex():
    t = traversal(1, 1)
    assert t.pieces == ((0, 0, F(1, 2)), (1, 1, F(1, 2)))
    assert t.vertex_sides == (((0, 1), (1, 0)),)


def test_knight_move_crosses_two_intermediate_cells_no_vertex():
    t = traversal(1, 2)
    assert t.pieces == ((0, 0, F(1, 4)), (0, 1, F(1, 4)), (1, 1, F(1, 4)), (1, 2, F(1, 4)))
    assert t.vertex_sides == ()


def test_three_one_move_has_a_vertex():
    t = traversal(1, 3)
    assert t.pieces == ((0, 0, F(1, 6)), (0, 1, F(1, 3)), (1, 2, F(1, 3)), (1, 3, F(1, 6)))
    assert t.vertex_sides == (((0, 2), (1, 1)),)


@pytest.mark.parametrize("radius", [1, 2, 3, 4])
def test_traversal_invariants(radius):
    for dr, dc in stencil(radius):
        t = traversal(dr, dc)
        assert sum(p[2] for p in t.pieces) == 1
        assert all(p[2] > 0 for p in t.pieces)
        assert t.pieces[0][:2] == (0, 0) and t.pieces[-1][:2] == (dr, dc)
        # a vertex is crossed iff both offsets are odd
        assert (len(t.vertex_sides) > 0) == (dr % 2 != 0 and dc % 2 != 0)
        for a, b in zip(t.pieces[:-1], t.pieces[1:]):
            step = (abs(b[0] - a[0]), abs(b[1] - a[1]))
            assert step in {(0, 1), (1, 0), (1, 1)}  # (1, 1) only through a vertex
        crossed = {(p[0], p[1]) for p in t.pieces}
        for s1, s2 in t.vertex_sides:
            assert s1 not in crossed and s2 not in crossed


def test_rule_blocks_diagonal_wall_but_not_single_corner():
    b = np.zeros((3, 3), bool)
    b[0, 1] = True  # one side cell only: a corner, passable
    assert edge_valid(b, 0, 0, traversal(1, 1))
    b[1, 0] = True  # both side cells: one-cell-thick diagonal wall
    assert not edge_valid(b, 0, 0, traversal(1, 1))


def test_rule_blocks_knight_through_intermediate_barrier():
    b = np.zeros((3, 3), bool)
    b[0, 1] = True
    assert not edge_valid(b, 0, 0, traversal(1, 2))
    b[:] = False
    b[1, 1] = True
    assert not edge_valid(b, 0, 0, traversal(1, 2))


def test_rule_rejects_edges_leaving_grid():
    b = np.zeros((2, 2), bool)
    assert not edge_valid(b, 1, 1, traversal(1, 0))


def test_stencil_angular_error_isotropic_matches_closed_form():
    # worst gap 45 deg (8) / 26.57 deg (16) / 18.43 deg (32): 1/cos(gap/2) - 1
    for radius, expected in [(1, 0.0824), (2, 0.0275), (3, 0.0131)]:
        assert stencil_error(radius, 1.0, 0.0)["forward_max"] == pytest.approx(expected, abs=5e-4)


def test_stencil_angular_error_grows_with_elongation():
    """CRITICAL_REVIEW P0-1: a 16-neighbour stencil cannot represent elongated ellipses."""
    worst = max(stencil_error(2, 4.0, np.radians(a))["head"] for a in range(0, 46, 1))
    assert worst > 0.5
    worst_r8 = max(stencil_error(8, 4.0, np.radians(a))["head"] for a in range(0, 46, 1))
    assert worst_r8 < 0.07
