"""Neighbour stencils and exact segment traversal tables (METHOD.md, "Edge geometry and barriers").

Grid convention: cell (r, c) is the unit square x in [c, c+1), y in [r, r+1) (rows grow downward).
A transition (edge) from cell u = (r, c) by offset (dr, dc) is the straight segment from the centre of u
to the centre of v = (r+dr, c+dc). All crossing parameters are exact rationals (fractions.Fraction), so
"passes through a grid vertex" and "touches a cell with zero length" are decided exactly, not by
floating-point tolerance.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import atan2, gcd, hypot

import numpy as np


def stencil(radius: int) -> list[tuple[int, int]]:
    """All primitive offsets (dr, dc) with Chebyshev norm <= radius.

    radius 1 -> 8 neighbours, 2 -> 16 (adds knight moves), 3 -> 32. Non-primitive offsets such as (0, 2)
    are omitted: they are compositions of shorter collinear moves with identical cost in a homogeneous
    medium and would only duplicate work.
    """
    if radius < 1:
        raise ValueError("radius must be >= 1")
    out = [
        (dr, dc)
        for dr in range(-radius, radius + 1)
        for dc in range(-radius, radius + 1)
        if (dr, dc) != (0, 0) and gcd(abs(dr), abs(dc)) == 1
    ]
    return sorted(out, key=lambda o: atan2(-o[0], o[1]))


@dataclass(frozen=True)
class Traversal:
    """Exact traversal of the centre-to-centre segment for one offset.

    pieces: (dr_j, dc_j, frac_j) in order from u (j = 0) to v (last); frac_j = exact share of the
        segment length inside that cell (> 0); sum(frac_j) == 1.
    vertex_sides: for every grid vertex the segment passes through, the two cells that touch the vertex
        but are not crossed by the segment (they meet the segment in a single point).
    length: segment length in cell units.
    phi: direction of travel, radians counter-clockwise from +x (east), with y pointing north
        (so a move to the row above, dr = -1, has phi = +pi/2).
    """

    dr: int
    dc: int
    pieces: tuple[tuple[int, int, Fraction], ...]
    vertex_sides: tuple[tuple[tuple[int, int], tuple[int, int]], ...]
    length: float
    phi: float


def _floor_frac(x: Fraction) -> int:
    return x.numerator // x.denominator


def traversal(dr: int, dc: int) -> Traversal:
    half = Fraction(1, 2)
    # Segment p(s) = (0.5 + s*dc, 0.5 + s*dr) in (x, y) cell units relative to u's corner, s in [0, 1].
    params: set[Fraction] = {Fraction(0), Fraction(1)}
    sx: set[Fraction] = set()
    sy: set[Fraction] = set()
    for d, store in ((dc, sx), (dr, sy)):
        if d == 0:
            continue
        # grid lines strictly between the two centres: coordinate k for k in (0.5, 0.5 + d)
        lo, hi = sorted((half, half + d))
        k = _floor_frac(lo) + 1
        while k < hi:
            store.add((Fraction(k) - half) / d)
            k += 1
    params |= sx | sy
    ps = sorted(params)
    pieces: list[tuple[int, int, Fraction]] = []
    for a, b in zip(ps[:-1], ps[1:]):
        mid = (a + b) / 2
        x = half + mid * dc
        y = half + mid * dr
        cell = (_floor_frac(y), _floor_frac(x))
        frac = b - a
        if pieces and (pieces[-1][0], pieces[-1][1]) == cell:
            pieces[-1] = (cell[0], cell[1], pieces[-1][2] + frac)
        else:
            pieces.append((cell[0], cell[1], frac))
    sides = []
    for s in sorted(sx & sy):  # the segment passes exactly through a grid vertex
        eps = Fraction(1, 10**9)
        before = (_floor_frac(half + (s - eps) * dr), _floor_frac(half + (s - eps) * dc))
        after = (_floor_frac(half + (s + eps) * dr), _floor_frac(half + (s + eps) * dc))
        sides.append(((before[0], after[1]), (after[0], before[1])))
    assert sum(p[2] for p in pieces) == 1
    return Traversal(dr, dc, tuple(pieces), tuple(sides), hypot(dr, dc), atan2(-dr, dc))


def traversals(radius: int) -> list[Traversal]:
    return [traversal(dr, dc) for dr, dc in stencil(radius)]


def edge_valid(barrier: np.ndarray, r: int, c: int, t: Traversal) -> bool:
    """Transition rule (METHOD.md): invalid iff it leaves the grid, any crossed cell (positive length)
    is a barrier, or it passes through a grid vertex whose two side cells are both barriers
    (a one-cell-thick diagonal wall)."""
    nr, nc = barrier.shape
    for dr, dc, _ in t.pieces:
        rr, cc = r + dr, c + dc
        if not (0 <= rr < nr and 0 <= cc < nc) or barrier[rr, cc]:
            return False
    for (a, b) in t.vertex_sides:
        if barrier[r + a[0], c + a[1]] and barrier[r + b[0], c + b[1]]:
            return False
    return True


# --------------------------------------------------------------------------------------------------
# Stencil angular error for an elliptical (focus-anchored) speed profile in a homogeneous medium.
# --------------------------------------------------------------------------------------------------

def _ray(psi: np.ndarray, ecc: float) -> np.ndarray:
    return (1.0 - ecc) / (1.0 - ecc * np.cos(psi))


def stencil_error(radius: int, lb: float, wind_angle: float, n_dir: int = 7201) -> dict:
    """Asymptotic arrival-time error of label-setting on `stencil(radius)` vs the continuous ellipse.

    In a homogeneous medium the set reachable in unit time on the stencil graph is (asymptotically) the
    convex hull of the points r(phi_k) * unit(phi_k); the true set is the ellipse with the source at its
    rear focus. Relative arrival-time error in direction theta = rho_true / rho_hull - 1 (>= 0).
    Returns the worst error over the forward half-plane (|psi| <= 90 deg) and in the head direction.
    """
    ecc = np.sqrt(lb * lb - 1.0) / lb if lb > 1 else 0.0
    offs = stencil(radius)
    ang = np.array([atan2(-dr, dc) for dr, dc in offs])
    rad = _ray(ang - wind_angle, ecc)
    pts = np.stack([rad * np.cos(ang), rad * np.sin(ang)], 1)
    hull = _convex_hull(pts)
    th = np.linspace(-np.pi, np.pi, n_dir)
    rho_hull = _radial(hull, th)
    rho_true = _ray(th - wind_angle, ecc)
    rel = rho_true / rho_hull - 1.0
    psi = np.angle(np.exp(1j * (th - wind_angle)))
    return {
        "forward_max": float(rel[np.abs(psi) <= np.pi / 2].max()),
        "head": float(rel[np.argmin(np.abs(psi))]),
    }


def _convex_hull(p: np.ndarray) -> np.ndarray:
    pts = sorted(map(tuple, p))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for q in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    for q in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return np.array(lower[:-1] + upper[:-1])  # counter-clockwise


def _radial(hull: np.ndarray, th: np.ndarray) -> np.ndarray:
    """Distance from the origin (inside the hull) to the hull boundary along each direction."""
    a = hull
    b = np.roll(hull, -1, axis=0)
    d = np.stack([np.cos(th), np.sin(th)], 1)
    out = np.full(th.shape, np.inf)
    for p, q in zip(a, b):
        e = q - p
        den = d[:, 0] * e[1] - d[:, 1] * e[0]
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (p[0] * e[1] - p[1] * e[0]) / den          # ray parameter
            u = (p[0] * d[:, 1] - p[1] * d[:, 0]) / den    # edge parameter
        ok = (np.abs(den) > 1e-15) & (t > 0) & (u >= -1e-12) & (u <= 1 + 1e-12)
        out = np.where(ok, np.minimum(out, t), out)
    return out
