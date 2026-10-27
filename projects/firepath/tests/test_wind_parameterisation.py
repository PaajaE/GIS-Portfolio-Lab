"""D3: wind-speed multiplier a_u vs v1 a_w; separation from input uncertainty (lambda)."""

import numpy as np
import pytest

from firepath.ellipse import eccentricity
from firepath.reference import propagate, uniform_field
from firepath.rothermel import (MS_TO_FTMIN, head_and_shape, phi_slope, phi_wind, phi_wind_inverse,
                                wind_coefficients)

# illustrative fine-fuel bed (not a specific SB40 model): sigma 2000 1/ft, beta 0.005, beta/beta_op 0.3
SIG, BETA = 2000.0, 0.005
BOP = BETA / 0.3
COMMON = dict(r0_mmin=0.6, sigma=SIG, beta=BETA, beta_op=BOP, waf=0.4, wind_to=0.0, ros_cap="none")


def test_wind_factor_round_trip():
    for u in (10.0, 200.0, 800.0):
        assert phi_wind_inverse(phi_wind(u, SIG, 0.3), SIG, 0.3) == pytest.approx(u, rel=1e-12)


def test_wind_slope_vector_combination_aligned_and_opposed():
    pw = phi_wind(4.0 * 0.4 * MS_TO_FTMIN, SIG, 0.3)
    ps = phi_slope(BETA, 0.4)
    up = head_and_shape(u20_ms=4.0, tan_slope=0.4, upslope=0.0, **COMMON)
    down = head_and_shape(u20_ms=4.0, tan_slope=0.4, upslope=np.pi, **COMMON)
    assert up.r_head == pytest.approx(0.6 * (1 + pw + ps))
    assert down.r_head == pytest.approx(0.6 * (1 + abs(pw - ps)))


def test_a_u_is_exactly_a_wind_speed_scaling():
    """a_u acts through published functions only: identical to scaling the input wind."""
    for lb_model in ("farsite", "behaveplus"):
        a = head_and_shape(u20_ms=5.0, a_u=1.3, lb_model=lb_model, **COMMON)
        b = head_and_shape(u20_ms=6.5, a_u=1.0, lb_model=lb_model, **COMMON)
        assert (a.r_head, a.lb, a.ecc) == pytest.approx((b.r_head, b.lb, b.ecc), rel=1e-12)


def test_v1_a_w_inside_phi_w_distorts_shape():
    """v1: phi_E = a_w phi_w, inverted with the unmodified phi_w -> U_E = a_w^(1/B) U."""
    _, b, _ = wind_coefficients(SIG)
    u = 5.0 * 0.4 * MS_TO_FTMIN
    a_w = 1.3
    u_e_v1 = phi_wind_inverse(a_w * phi_wind(u, SIG, 0.3), SIG, 0.3)
    assert u_e_v1 / u == pytest.approx(a_w ** (1 / b), rel=1e-12)
    # v1 called a_w a ROS multiplier, yet it moved the effective wind (hence LB) by a_w^(1/B).
    # For this fine-fuel bed B = 1.53, so the shape change is a_w^0.65 -- modest, but not zero, and its
    # size depends on the fuel model (B varies with sigma), so a_w had no single interpretation.
    assert 1.15 < a_w ** (1 / b) < 1.2


def test_k_scales_ros_without_changing_shape():
    a = head_and_shape(u20_ms=5.0, k=2.0, **COMMON)
    b = head_and_shape(u20_ms=5.0, k=1.0, **COMMON)
    assert a.r_head == pytest.approx(2 * b.r_head) and a.lb == b.lb


def test_elasticity_of_head_ros_to_a_u():
    """d ln R / d ln a_u = B phi_w / (1 + phi_w) (wind only, no cap): same as for the input wind."""
    _, b, _ = wind_coefficients(SIG)
    base = head_and_shape(u20_ms=5.0, **COMMON)
    h = 1e-6
    up = head_and_shape(u20_ms=5.0, a_u=1 + h, **COMMON)
    num = (np.log(up.r_head) - np.log(base.r_head)) / np.log(1 + h)
    pw = base.r_head / 0.6 - 1
    assert num == pytest.approx(b * pw / (1 + pw), rel=1e-4)


def test_model_parameter_and_input_uncertainty_are_not_separable_by_the_model():
    """lambda * a_u enters as a product: the arrival field cannot tell them apart. Separation must come
    from the design (a_u calibrated and fixed; lambda drawn from independent HRRR-vs-station errors)."""
    def field(a_u, lam):
        s = head_and_shape(u20_ms=5.0, a_u=a_u, wind_factor=lam, **COMMON)
        return uniform_field((31, 31), r_head=s.r_head, ecc=s.ecc, theta=s.theta)
    a = propagate(field(1.2, 1.0), radius=3, points=[(15, 15, 0.0)]).arrival
    b = propagate(field(1.0, 1.2), radius=3, points=[(15, 15, 0.0)]).arrival
    assert np.array_equal(a, b)


def test_andrews_cap_limits_head_ros_to_effective_wind():
    s = head_and_shape(u20_ms=0.5, waf=0.4, r0_mmin=60.0, sigma=SIG, beta=BETA, beta_op=BOP, wind_to=0.0,
                       ros_cap="none")
    c = head_and_shape(u20_ms=0.5, waf=0.4, r0_mmin=60.0, sigma=SIG, beta=BETA, beta_op=BOP, wind_to=0.0,
                       ros_cap="andrews2013")
    assert c.r_head <= s.r_head
    assert float(eccentricity(1.0)) == 0.0
