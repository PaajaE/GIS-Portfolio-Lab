"""The exact references used for code verification (firepath.canonical) are themselves checked."""

import numpy as np
import pytest

from firepath.canonical import R0, t_disc, t_half_plane, t_two_winds


def test_half_plane_reduces_to_disc_for_equal_fuels():
    xs = np.array([700.0, 900.0, 650.0, 1100.0])
    ys = np.array([600.0, 300.0, 1000.0, 900.0])
    a = t_half_plane(xs, ys, 300.0, 600.0, 600.0, 1.0, 1.0, 0.6, 0.3, 0.0, 1200.0)
    b = t_disc(xs - 300.0, ys - 600.0, 1.0, 0.6, 0.3)
    assert a == pytest.approx(b, rel=1e-6)


@pytest.mark.parametrize("r1, r2", [(1.0, 0.25), (0.25, 1.0)])
def test_half_plane_on_axis_matches_1d(r1, r2):
    x = np.array([900.0])
    t = t_half_plane(x, np.array([600.0]), 300.0, 600.0, 600.0, r1, r2, 0.0, 0.0, 0.0, 1200.0)[0]
    assert t == pytest.approx((600.0 - 300.0 - R0) / r1 + (900.0 - 600.0) / r2, rel=1e-6)


def test_head_wave_beats_direct_path_near_interface():
    """Slow source half, fast other half: a far point in the source half close to the interface is
    reached faster via the interface than directly."""
    xs, ys = np.array([590.0]), np.array([100.0])
    t = t_half_plane(xs, ys, 300.0, 600.0, 600.0, 0.25, 1.0, 0.0, 0.0, 0.0, 1200.0)[0]
    direct = float(t_disc(590.0 - 300.0, 100.0 - 600.0, 0.25, 0.0, 0.0)[0])
    assert t < direct


def test_two_winds_reduces_to_one_wind_before_switch():
    a = t_two_winds(np.array([200.0]), np.array([50.0]), 1e9, 0.7, 0.2, 1.7)
    b = t_disc(200.0, 50.0, 1.0, 0.7, 0.2)
    assert a == pytest.approx(b, rel=1e-9)
