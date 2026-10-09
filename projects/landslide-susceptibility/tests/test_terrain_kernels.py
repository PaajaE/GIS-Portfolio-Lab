"""Rust terrain kernels vs the NumPy/SciPy oracle, and the oracle vs analytic surfaces.

Tolerances (outputs are float32; both sides compute in float64 and round once):
* min, max (and relief = max - min): exact
* mean (and TPI = z - mean): rtol 1e-6 (~2 float32 ulps)
* sd: atol 1e-4 (in the input's unit)
* terrain3x3 outputs: rtol 1e-6, atol 1e-6
Nodata masks must be identical.
"""

import numpy as np
import pytest
from terrain_kernels import terrain3x3, window_stats

from landslide.terrain_ref import terrain3x3_ref, window_stats_loop, window_stats_scipy

ND = np.float32(-9999.0)
KEYS3 = ("slope_deg", "northness", "eastness", "profile_curv", "plan_curv", "tri")


def dem(h, w, seed, holes=True):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    z = (800 + 3.0 * xx - 2.0 * yy + 40 * np.sin(xx / 7) * np.cos(yy / 5) + rng.normal(0, 0.7, (h, w)))
    z = z.astype(np.float32)
    if holes:
        z[h // 2, w // 3] = ND
        z[1, 1] = np.nan
        z[h - 4 : h - 2, 2:5] = ND
    return z


def assert_masks_and_close(got, ref, rtol=0.0, atol=0.0, exact=False):
    got, ref = np.asarray(got), np.asarray(ref)
    assert np.array_equal(got == ND, ref == ND)
    v = ref != ND
    if exact:
        assert np.array_equal(got[v], ref[v])
    else:
        np.testing.assert_allclose(got[v], ref[v], rtol=rtol, atol=atol)


@pytest.mark.parametrize("shape,seed", [((20, 31), 1), ((64, 48), 2), ((3, 3), 3), ((9, 4), 4)])
def test_terrain3x3_matches_reference(shape, seed):
    z = dem(*shape, seed, holes=min(shape) > 6)
    got = dict(zip(KEYS3, terrain3x3(z, 5.0, float(ND))))
    ref = terrain3x3_ref(z, 5.0, float(ND))
    for k in KEYS3:
        assert_masks_and_close(got[k], ref[k], rtol=1e-6, atol=1e-6)


@pytest.mark.parametrize("r", [0, 1, 2, 5])
@pytest.mark.parametrize("seed", [1, 2])
def test_window_stats_match_loop_reference(r, seed):
    x = dem(23, 29, seed)
    m, sd, mn, mx = window_stats(x, r, float(ND))
    ref = window_stats_loop(x, r, float(ND))
    assert_masks_and_close(mn, ref["min"], exact=True)
    assert_masks_and_close(mx, ref["max"], exact=True)
    assert_masks_and_close(m, ref["mean"], rtol=1e-6)
    assert_masks_and_close(sd, ref["sd"], atol=1e-4)


def test_window_stats_match_scipy_reference_large_window():
    x = dem(120, 140, 7)
    for r in (10, 50):
        m, sd, mn, mx = window_stats(x, r, float(ND))
        ref = window_stats_scipy(x, r, float(ND))
        assert_masks_and_close(mn, ref["min"], exact=True)
        assert_masks_and_close(mx, ref["max"], exact=True)
        assert_masks_and_close(m, ref["mean"], rtol=1e-6)
        assert_masks_and_close(sd, ref["sd"], atol=1e-4)


def test_window_stats_edge_cases():
    # window larger than the grid, all nodata, flat field with ties, empty
    assert (np.stack(window_stats(np.ones((3, 3), np.float32), 2, float(ND))) == ND).all()
    assert (np.stack(window_stats(np.full((6, 6), ND), 1, float(ND))) == ND).all()
    m, sd, mn, mx = window_stats(np.full((6, 6), 7, np.float32), 1, float(ND))
    assert m[2, 2] == 7 and sd[2, 2] == 0 and mn[2, 2] == 7 and mx[2, 2] == 7
    out = window_stats(np.zeros((0, 0), np.float32), 1, float(ND))
    assert all(a.shape == (0, 0) for a in out)


# --- the oracle against analytic surfaces -------------------------------------------------------
def grid(h, w, cell, f):
    yy, xx = np.mgrid[0:h, 0:w]
    x, y = xx * cell, -yy * cell  # row 0 = north
    return f(x, y).astype(np.float32)


def test_reference_plane_slope_aspect():
    z = grid(8, 9, 5.0, lambda x, y: 300 + 0.3 * x - 0.4 * y)
    r = terrain3x3_ref(z, 5.0, float(ND))
    c = (4, 4)
    assert r["slope_deg"][c] == pytest.approx(np.degrees(np.arctan(0.5)), abs=1e-4)
    assert (r["eastness"][c], r["northness"][c]) == (pytest.approx(-0.6, abs=1e-5), pytest.approx(0.8, abs=1e-5))
    assert abs(r["profile_curv"][c]) < 1e-6 and abs(r["plan_curv"][c]) < 1e-6


def test_reference_curvature_paraboloid():
    # z = a x^2 + b y^2 with gradient along x at (x0, 0): profile = 2a, plan = 2b (exact for quadratics)
    a, b, x0 = 0.02, -0.03, 40.0
    z = grid(9, 21, 5.0, lambda x, y: 600 + a * (x - 50 + x0) ** 2 + b * (y + 20) ** 2)
    r = terrain3x3_ref(z, 5.0, float(ND))
    c = (4, 10)  # x = 50, y = -20 -> (x - 50 + x0) = x0, (y + 20) = 0
    assert r["profile_curv"][c] == pytest.approx(2 * a, rel=1e-3)
    assert r["plan_curv"][c] == pytest.approx(2 * b, rel=1e-3)


def test_reference_tri_and_window_relief_on_cone():
    z = grid(11, 11, 5.0, lambda x, y: 1000 - 0.5 * np.hypot(x - 25, y + 25))
    r = terrain3x3_ref(z, 5.0, float(ND))
    c = (5, 5)  # apex: every neighbour lies 2.5 m (edge) or 3.54 m (diagonal) lower
    assert r["tri"][c] == pytest.approx(np.sqrt(4 * 2.5**2 + 4 * (0.5 * 5 * np.sqrt(2)) ** 2), rel=1e-5)
    ws = window_stats_loop(z, 2, float(ND))
    assert ws["max"][c] == z[c] and ws["min"][c] == pytest.approx(1000 - 0.5 * 10 * np.sqrt(2), abs=1e-3)


def test_window_stats_accuracy_on_large_grid():
    # Regression: summed-area tables over a whole 4096^2 grid lost ~1e-3 m in sd (float64 cancellation);
    # sliding sums must stay within 1e-5 of an exact two-pass computation on sampled windows.
    rng = np.random.default_rng(11)
    n = 3000
    yy, xx = np.mgrid[0:n, 0:n]
    z = (400 + 0.25 * xx + 0.15 * yy + rng.normal(0, 0.5, (n, n))).astype(np.float32)  # 400-1600 m
    for r in (1, 5):
        _, sd, _, _ = window_stats(z, r, float(ND))
        idx = rng.integers(r, n - r, (300, 2))
        exact = [z[i - r : i + r + 1, j - r : j + r + 1].astype(np.float64).std() for i, j in idx]
        assert np.abs(sd[idx[:, 0], idx[:, 1]] - exact).max() < 1e-5


def test_chunked_reference_equals_reference():
    from landslide.terrain_ref import terrain3x3_ref_chunked

    z = dem(50, 37, 9)
    a, b = terrain3x3_ref(z, 5.0, float(ND)), terrain3x3_ref_chunked(z, 5.0, float(ND), rows=7)
    for k in KEYS3:
        assert np.array_equal(a[k], b[k])
