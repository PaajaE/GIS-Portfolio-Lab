"""Slope-plane geometry shared by the propagation kernels (METHOD.md, "Slope-plane geometry").

The unit-time spread set is a focal ellipse E in the cell's slope plane. Seen from above it is P(E),
where P maps slope-plane coordinates (e1 = upslope surface direction, e2 = contour) to the horizontal
plane: P(a1, a2) = a1 cos(s) u + a2 c, with u the horizontal upslope unit vector, c = u rotated +90 deg
and s the slope angle. P is linear, so P(E) is an ellipse with the ignition point at the origin, and

* support function (level set):  h_{P(E)}(p) = h_E(P^T p),  P^T p = (cos(s) p.u, p.c);
* radial speed (graph):  s_h(d) = rho_E(P^-1 d / |P^-1 d|) / |P^-1 d|,  |P^-1 d| = sqrt(1 + (tan(s) d.u)^2).

`theta` in a SpreadField is the horizontal image P(w) of the slope-plane max-spread direction w, so
w = normalise(P^-1 theta_hat). On flat cells (tan s = 0) every formula reduces to the planar ellipse.
"""

from __future__ import annotations

import numpy as np


def frame(tan_slope, upslope):
    """cos(s) and the horizontal upslope unit vector (ux, uy)."""
    return 1.0 / np.sqrt(1.0 + np.asarray(tan_slope) ** 2), np.cos(upslope), np.sin(upslope)


def cov_to_slope(px, py, cs, ux, uy):
    """P^T p: a horizontal gradient (covector) in slope-plane coordinates."""
    return cs * (px * ux + py * uy), -px * uy + py * ux


def dir_to_slope(dx, dy, cs, ux, uy):
    """P^-1 d (not normalised): a horizontal direction in slope-plane coordinates."""
    return (dx * ux + dy * uy) / cs, -dx * uy + dy * ux


def vec_to_horizontal(a1, a2, cs, ux, uy):
    """P a: a slope-plane vector seen from above."""
    return a1 * cs * ux - a2 * uy, a1 * cs * uy + a2 * ux


def w_in_slope(theta, cs, ux, uy):
    """Unit slope-plane max-spread direction from its horizontal image theta."""
    w1, w2 = dir_to_slope(np.cos(theta), np.sin(theta), cs, ux, uy)
    n = np.hypot(w1, w2)
    return w1 / n, w2 / n
