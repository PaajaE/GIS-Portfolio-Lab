"""Perimeter-sequence audit, interval error, ellipse relations and moisture mapping."""

import numpy as np
import pytest

from firepath.ellipse import (MS_TO_MPH, eccentricity, lb_anderson_mph, lb_anderson_ms,
                              lb_rothermel1991_mph, ray_factor)
from firepath.moisture import DEAD_SCENARIOS, cured_fraction, from_gridmet
from firepath.observed import CONSISTENT, INCONSISTENT, INITIAL, NEVER, audit_sequence, interval_error


def _sq(n, r0, r1, c0, c1):
    m = np.zeros((n, n), bool)
    m[r0:r1, c0:c1] = True
    return m


def test_nested_sequence_intervals():
    n = 10
    masks = [_sq(n, 4, 6, 4, 6), _sq(n, 3, 7, 3, 7), _sq(n, 2, 8, 2, 8)]
    out = audit_sequence([0.0, 10.0, 24.0], masks)
    assert out["flag"][5, 5] == INITIAL and out["hi"][5, 5] == 0.0
    assert out["flag"][3, 3] == CONSISTENT and (out["lo"][3, 3], out["hi"][3, 3]) == (0.0, 10.0)
    assert (out["lo"][2, 2], out["hi"][2, 2]) == (10.0, 24.0)
    assert out["flag"][0, 0] == NEVER and out["lo"][0, 0] == 24.0 and np.isinf(out["hi"][0, 0])
    assert all(s["removed_jitter"] == s["removed_retraction"] == 0 for s in out["steps"])


def test_jitter_and_retraction_are_reported_not_forced():
    n = 20
    m0 = _sq(n, 5, 10, 5, 10)
    m1 = _sq(n, 5, 10, 6, 12)           # drops column 5 (adjacent to new perimeter: jitter)
    m1 |= _sq(n, 15, 17, 15, 17)        # an unrelated new patch
    m0b = m0 | _sq(n, 0, 2, 0, 2)       # earlier patch far away, absent later: retraction
    out = audit_sequence([0.0, 12.0], [m0b, m1])
    s = out["steps"][0]
    assert s["removed_jitter"] == 5 and s["removed_retraction"] == 4
    assert out["flag"][7, 5] == INCONSISTENT and out["flag"][0, 0] == INCONSISTENT
    assert out["flag"][16, 16] == CONSISTENT


def test_times_must_increase():
    m = _sq(4, 0, 1, 0, 1)
    with pytest.raises(ValueError):
        audit_sequence([5.0, 5.0], [m, m])


def test_interval_error_sign_convention():
    lo, hi = np.array([10.0, 10.0, 10.0]), np.array([20.0, 20.0, 20.0])
    e = interval_error(np.array([4.0, 15.0, 26.0]), lo, hi)
    assert list(e) == [-6.0, 0.0, 6.0]       # early negative, inside zero, late positive
    assert interval_error(np.array([np.inf]), lo[:1], hi[:1])[0] == np.inf


def test_anderson_units_mph_vs_ms_forms_agree():
    u = np.linspace(0, 12, 50)  # m/s
    assert lb_anderson_mph(u * MS_TO_MPH) == pytest.approx(lb_anderson_ms(u), rel=5e-3)


def test_plan_v1_unit_error_is_large():
    """PLAN v1 used the m/s coefficients with mi/h input: LB 8 (cap) at 10 mi/h instead of ~2.8."""
    assert float(lb_anderson_ms(10.0)) == 8.0
    assert float(lb_anderson_mph(10.0)) == pytest.approx(2.78, abs=0.01)


def test_ellipse_basics():
    assert float(lb_anderson_mph(0.0)) == pytest.approx(1.0, abs=1e-12)
    assert float(lb_rothermel1991_mph(0.0)) == 1.0
    e = float(eccentricity(3.0))
    assert ray_factor(0.0, e) == pytest.approx(1.0)
    assert ray_factor(np.pi, e) == pytest.approx((1 - e) / (1 + e))


@pytest.mark.parametrize("name", ["D1", "D2", "D3", "D4"])
def test_gridmet_mapping_reproduces_scott_burgan_scenarios(name):
    d1, d10, d100 = DEAD_SCENARIOS[name]
    m = from_gridmet(float(d100))
    assert (m.d1, m.d10, m.d100) == (d1, d10, d100)


def test_moisture_multiplier_scales_dead_only_and_floor():
    m = from_gridmet(8.0, live="L2", m=1.2)
    assert (m.d1, m.d10, m.d100) == pytest.approx((7.2, 8.4, 9.6))
    assert (m.live_herb, m.live_woody) == (60.0, 90.0)
    assert from_gridmet(3.0).d1 == 2.0


@pytest.mark.parametrize("herb, cured", [(30, 1.0), (20, 1.0), (60, 2 / 3), (75, 0.5), (90, 1 / 3), (120, 0.0), (150, 0.0)])
def test_dynamic_fuel_curing(herb, cured):
    assert cured_fraction(herb) == pytest.approx(cured)


def test_lb_relations_at_reference_speeds():
    """D2: FARSITE form (Finney 1998: effective midflame wind, m/s, cap 8) vs BehavePlus (1 + 0.25 U mi/h)."""
    u_ms = 10.0 / MS_TO_MPH
    assert float(lb_anderson_ms(u_ms)) == pytest.approx(2.78, abs=0.01)
    assert float(lb_rothermel1991_mph(10.0)) == pytest.approx(3.5)
    assert float(lb_anderson_ms(20.0 / MS_TO_MPH)) == 8.0          # cap reached near 20 mi/h
    assert float(lb_rothermel1991_mph(20.0)) == pytest.approx(6.0)
