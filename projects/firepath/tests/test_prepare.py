import numpy as np

from firepath.prepare import horn_slope_aspect, north_angle, rotate_to_grid


def test_horn_on_a_plane():
    cell = 30.0
    rows, cols = np.mgrid[0:20, 0:20]
    x, y = cols * cell, -rows * cell              # row 0 is north
    z = 0.2 * x + 0.1 * y
    t, up = horn_slope_aspect(z, cell)
    assert np.allclose(t[2:-2, 2:-2], np.hypot(0.2, 0.1))
    assert np.allclose(up[2:-2, 2:-2], np.arctan2(0.1, 0.2))


def test_north_angle_utm_and_hrrr_lambert():
    # UTM 12N at its central meridian (-111): true north is grid north (90 deg)
    from pyproj import Transformer
    x, y = Transformer.from_crs(4326, 26912, always_xy=True).transform(-111.0, 36.5)
    assert abs(np.degrees(north_angle(26912, np.array([x]), np.array([y])))[0] - 90.0) < 1e-3
    # HRRR Lambert (lat_1 = lat_2 = 38.5, lon_0 = -97.5): rotation n (lon - lon_0), n = sin(38.5 deg)
    hrrr = "+proj=lcc +lat_0=38.5 +lon_0=-97.5 +lat_1=38.5 +lat_2=38.5 +R=6371229 +units=m +no_defs"
    hx, hy = Transformer.from_crs(4326, hrrr, always_xy=True).transform(-112.2, 36.7)
    got = 90.0 - np.degrees(north_angle(hrrr, np.array([hx]), np.array([hy])))[0]
    assert abs(got - np.sin(np.radians(38.5)) * (-97.5 + 112.2)) < 0.01


def test_rotation_preserves_speed_and_direction_change():
    u, v = np.array([3.0]), np.array([4.0])
    ru, rv = rotate_to_grid(u, v, np.radians(80.0), np.radians(90.0))
    assert np.allclose(np.hypot(ru, rv), 5.0)
    assert np.isclose(np.degrees(np.arctan2(rv, ru) - np.arctan2(v, u))[0], 10.0)
