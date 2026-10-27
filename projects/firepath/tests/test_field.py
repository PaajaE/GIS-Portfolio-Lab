import numpy as np

from firepath.field import Params, Static, hour, waf
from firepath.fuels import fuel_bed
from firepath.moisture import Moisture
from firepath.rothermel import head_and_shape

M = Moisture(4, 5, 6, 60, 90)


def _static(fuel, tan_s=0.0, up=0.0, cc=0, ch=0):
    shp = fuel.shape
    return Static.build(fuel, np.full(shp, cc), np.full(shp, ch), np.full(shp, tan_s), np.full(shp, up), M)


def test_flat_cells_match_scalar_head_and_shape():
    fuel = np.array([[102, 122, 165, 188]])
    st = _static(fuel)
    u10, v10 = np.full(fuel.shape, 6.0), np.full(fuel.shape, -3.0)
    p = Params(k=1.3, a_u=0.9)
    r, e, t = hour(st, u10, v10, p)
    for j, code in enumerate(fuel[0]):
        b = fuel_bed(int(code), M)
        s = head_and_shape(b.r0_mmin, b.sigma, b.beta, b.beta_op, float(np.hypot(6, 3)) / 1.15, st.waf[0, j],
                           float(np.arctan2(-3.0, 6.0)), k=1.3, a_u=0.9)
        assert np.isclose(r[0, j], s.r_head, rtol=1e-9) and np.isclose(e[0, j], s.ecc, rtol=1e-9)
        assert np.isclose(np.angle(np.exp(1j * (t[0, j] - s.theta))), 0.0, atol=1e-9)


def test_upslope_wind_on_incline_points_upslope_and_nonburnable_is_zero():
    fuel = np.array([[122, 99]])
    up = np.radians(70.0)
    st = _static(fuel, tan_s=0.5, up=up)
    r, e, t = hour(st, np.full(fuel.shape, 5 * np.cos(up)), np.full(fuel.shape, 5 * np.sin(up)), Params())
    assert np.isclose(t[0, 0], up) and r[0, 0] > 0
    assert r[0, 1] == 0 and not st.burnable[0, 1]


def test_waf_sheltered_switch_follows_gtr266():
    fuel = np.array([[188, 188, 102]])
    w = waf(fuel, np.array([[10, 60, 0]]), np.array([[20.0, 20.0, 0.0]]))
    # CC 10 % -> f = 0.033 < 0.05 -> unsheltered (TL8 depth 0.3 ft); CC 60 % -> f = 0.2 -> sheltered
    h = 0.3
    assert np.isclose(w[0, 0], 1.83 / np.log((20 + 0.36 * h) / (0.13 * h)))
    hc = 20.0 * 3.280839895
    assert np.isclose(w[0, 1], 0.555 / (np.sqrt(0.2 * hc) * np.log((20 + 0.36 * hc) / (0.13 * hc))))
    assert np.isclose(w[0, 2], 1.83 / np.log((20 + 0.36 * 1.0) / 0.13))


def test_timber_group_multiplier_scales_only_tu_tl():
    fuel = np.array([[102, 122, 165, 188]])          # GR2, SH2, TU5, TL8
    st = _static(fuel)
    z = np.zeros(fuel.shape)
    r1, _, _ = hour(st, z, z, Params(k=0.8))
    r2, _, _ = hour(st, z, z, Params(k=0.8, g=2.5))
    assert np.allclose(r2[0, :2], r1[0, :2]) and np.allclose(r2[0, 2:], 2.5 * r1[0, 2:])
