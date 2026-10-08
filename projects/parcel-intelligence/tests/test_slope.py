import numpy as np

from parcel_intel.prepare import NODATA, horn_slope_pct


def test_plane_slope_is_exact():
    # z rises 0.2 m per 2 m cell eastwards and 0.3 m per cell southwards
    yy, xx = np.mgrid[0:6, 0:7].astype(np.float32)
    dem = (0.2 * xx + 0.3 * yy).astype(np.float32)
    s = horn_slope_pct(dem, cell=2.0)
    expected = 100 * np.hypot(0.1, 0.15)
    np.testing.assert_allclose(s[1:-1, 1:-1], expected, rtol=1e-5)


def test_border_and_nodata_propagate():
    dem = np.zeros((5, 5), dtype=np.float32)
    dem[2, 2] = NODATA
    s = horn_slope_pct(dem, cell=2.0)
    assert (s[0, :] == NODATA).all() and (s[:, -1] == NODATA).all()
    assert (s[1:4, 1:4] == NODATA).all()  # every cell whose 3x3 window touches nodata


def test_flat_is_zero():
    s = horn_slope_pct(np.full((4, 4), 100.0, dtype=np.float32), cell=2.0)
    assert (s[1:-1, 1:-1] == 0).all()
