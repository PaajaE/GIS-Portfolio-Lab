"""Slope-plane geometry (METHOD "Slope-plane geometry"): kernel formulas against a brute-force
construction of the horizontal spread set P(E) from sampled points of the slope-plane ellipse E."""

import numpy as np
import pytest

from firepath.ellipse import eccentricity
from firepath.levelset import _Ham
from firepath.reference import uniform_field
from firepath.slopeplane import frame, vec_to_horizontal


def _boundary_PE(r_head, e, w_angle_slope, tan_s, up, n=200001):
    """Points of P(E): E = focal ellipse (focus at origin) in slope coordinates (e1 upslope, e2 contour)."""
    psi = np.linspace(-np.pi, np.pi, n)
    rho = r_head * (1 - e) / (1 - e * np.cos(psi))
    a1, a2 = rho * np.cos(psi + w_angle_slope), rho * np.sin(psi + w_angle_slope)
    cs, ux, uy = frame(tan_s, up)
    return vec_to_horizontal(a1, a2, cs, ux, uy)


@pytest.mark.parametrize("lb,tan_s,up,w_slope", [(1.0, 0.6, 1.2, 0.0), (2.0, 0.3, np.pi / 2, 0.4),
                                                 (4.0, 0.6, -0.7, 2.5), (3.0, 1.0, 0.0, 0.0)])
def test_graph_speed_and_support_match_brute_force(lb, tan_s, up, w_slope):
    e = float(eccentricity(lb)) if lb > 1 else 0.0
    x, y = _boundary_PE(1.0, e, w_slope, tan_s, up)
    # horizontal image of the slope-plane max-spread direction
    cs, ux, uy = frame(tan_s, up)
    tx, ty = vec_to_horizontal(np.cos(w_slope), np.sin(w_slope), cs, ux, uy)
    theta = np.arctan2(ty, tx)
    f = uniform_field((1, 1), r_head=1.0, ecc=e, theta=theta, tan_slope=tan_s, upslope=up)
    ang, rad = np.arctan2(y, x), np.hypot(x, y)
    for phi in np.linspace(-np.pi, np.pi, 37):
        k = np.argmin(np.abs(np.angle(np.exp(1j * (ang - phi)))))
        assert abs(f.speed(0, 0, 0, phi) - rad[k]) < 1e-3          # radial function of P(E)
    ham = _Ham(np.array([1.0 / (1 + e)]), np.array([e]), np.array([np.cos(theta)]), np.array([np.sin(theta)]),
               tuple(np.array([v]) for v in frame(tan_s, up)))
    for phi in np.linspace(-np.pi, np.pi, 37):
        px, py = np.cos(phi), np.sin(phi)
        assert abs(ham(np.array([px]), np.array([py]))[0] - np.max(px * x + py * y)) < 1e-6   # support of P(E)


def test_flat_slope_equals_planar():
    e = float(eccentricity(3.0))
    a = uniform_field((1, 1), r_head=2.0, ecc=e, theta=0.7)
    b = uniform_field((1, 1), r_head=2.0, ecc=e, theta=0.7, tan_slope=0.0, upslope=1.0)
    for phi in np.linspace(-3, 3, 13):
        assert abs(a.speed(0, 0, 0, phi) - b.speed(0, 0, 0, phi)) < 1e-12
