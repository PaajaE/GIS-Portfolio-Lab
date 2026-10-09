"""Block-mean aggregation and mosaicking on small hand-computable fixtures."""

import numpy as np
import pytest

from landslide.dem import block_mean, lattice_window, paste_first_valid

ND = -999999.0


def test_lattice_window_3dep_tile():
    # real tile header: left 359993.99996, top 3960006.00000, 10012 x 10012 px
    col0, row0, nx, ny, x0, y0 = lattice_window(359993.999963557, 3960006.0000024308, 10012, 10012, 5)
    assert (x0, y0) == (359995, 3960005)
    assert (col0, row0) == (1, 1)
    assert (nx, ny) == (2002, 2002)
    assert x0 % 5 == 0 and y0 % 5 == 0


def test_lattice_window_rejects_fractional_origin():
    with pytest.raises(ValueError):
        lattice_window(100.5, 200.0, 10, 10, 5)


def test_block_mean_exact_and_strict_nodata():
    a = np.arange(100, dtype=np.float32).reshape(10, 10)
    out = block_mean(a, ND, 5, -9999.0)
    # mean of a 5x5 block of a linear ramp = value at its centre
    assert out.tolist() == [[22.0, 27.0], [72.0, 77.0]]
    a[0, 0] = ND
    a[9, 9] = np.nan
    out = block_mean(a, ND, 5, -9999.0)
    assert out[0, 0] == -9999.0 and out[1, 1] == -9999.0
    assert out[0, 1] == 27.0 and out[1, 0] == 72.0


def test_block_mean_float64_accumulation():
    a = np.full((5, 5), 1234.567, dtype=np.float32)
    assert block_mean(a, ND, 5, -9999.0)[0, 0] == np.float32(1234.567)


def test_block_mean_requires_cropped_input():
    with pytest.raises(ValueError):
        block_mean(np.zeros((6, 5), np.float32), ND, 5, -9999.0)


def test_paste_first_valid_priority_and_seam():
    t = np.full((4, 4), -9999.0, np.float32)
    a = np.ones((2, 3), np.float32)
    assert paste_first_valid(t, a, 0, 0, -9999.0) == (0.0, 0)
    b = np.full((2, 3), 3.0, np.float32)
    diff, n = paste_first_valid(t, b, 1, 1, -9999.0)  # overlaps a on row 1, cols 1-2
    assert n == 2 and diff == 2.0
    assert t[1, 1] == 1.0 and t[2, 1] == 3.0  # first-valid wins; new cells filled
    # clipping at the target edge
    diff, n = paste_first_valid(t, np.full((3, 3), 5.0, np.float32), 3, 3, -9999.0)
    assert t[3, 3] == 5.0


def test_seam_stats():
    from landslide.dem import seam_stats

    t = np.full((3, 3), -9999.0, np.float32)
    t[:2, :2] = 10.0
    s = np.full((3, 3), 10.0, np.float32)
    s[0, 0] = 12.0
    st = seam_stats(t, s, 0, 0, -9999.0)
    assert st["overlap_cells"] == 4 and st["max_abs_diff_m"] == 2.0 and st["share_gt_1m"] == 0.25
    assert seam_stats(t, s, 10, 10, -9999.0) == {"overlap_cells": 0}
