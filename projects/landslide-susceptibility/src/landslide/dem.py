"""Exact block-mean aggregation of 1 m DEM tiles onto the 5 m UTM lattice, and first-valid mosaicking.

The 3DEP 1 m tiles are already in EPSG:26917 with integer-metre pixel edges (to within 4e-5 m), so the
5 m grid is an exact 5 x 5 block mean — no reprojection or resampling kernel is involved. A 5 m cell is
nodata if any of its 25 source pixels is nodata (strict, PLAN §5).
"""

from __future__ import annotations

import math

import numpy as np


def lattice_window(left: float, top: float, width: int, height: int, cell: int):
    """Source-pixel offsets (col0, row0), block counts (nx, ny) and the output origin (x0, y0).

    Source pixels are 1 m with edges at round(left) + i and round(top) - j. The output lattice has
    edges at multiples of `cell` metres.
    """
    xl, yt = round(left), round(top)
    if abs(left - xl) > 1e-3 or abs(top - yt) > 1e-3:
        raise ValueError(f"tile origin not on an integer-metre grid: {left}, {top}")
    x0 = math.ceil(xl / cell) * cell
    y0 = math.floor(yt / cell) * cell
    col0, row0 = x0 - xl, yt - y0
    nx, ny = (width - col0) // cell, (height - row0) // cell
    return col0, row0, nx, ny, x0, y0


def block_mean(a: np.ndarray, nodata: float, cell: int, out_nodata: float) -> np.ndarray:
    """Mean of non-overlapping cell x cell blocks; any nodata (or NaN) in a block -> out_nodata.

    `a` must already be cropped to a multiple of `cell` in both dimensions. Accumulates in float64.
    """
    ny, nx = a.shape[0] // cell, a.shape[1] // cell
    if a.shape != (ny * cell, nx * cell):
        raise ValueError("array not cropped to the block lattice")
    blocks = a.reshape(ny, cell, nx, cell).astype(np.float64)
    bad = (blocks == nodata) | ~np.isfinite(blocks)
    out = blocks.mean(axis=(1, 3))
    out[bad.any(axis=(1, 3))] = out_nodata
    return out.astype(np.float32)


def paste_first_valid(target: np.ndarray, src: np.ndarray, row: int, col: int, nodata: float):
    """Write src into target at (row, col) only where target is nodata. Clips to target.

    Returns seam statistics where both are valid: (max |difference|, number of overlapping cells).
    Use `seam_stats` for the full distribution."""
    s, t = _overlap(target, src, row, col)
    if s is None:
        return 0.0, 0
    sv, tv = s != nodata, t != nodata
    both = sv & tv
    diff = float(np.abs(s[both].astype(np.float64) - t[both]).max()) if both.any() else 0.0
    fill = sv & ~tv
    t[fill] = s[fill]
    return diff, int(both.sum())


def _overlap(target, src, row, col):
    r0, c0 = max(row, 0), max(col, 0)
    r1, c1 = min(row + src.shape[0], target.shape[0]), min(col + src.shape[1], target.shape[1])
    if r0 >= r1 or c0 >= c1:
        return None, None
    return src[r0 - row : r1 - row, c0 - col : c1 - col], target[r0:r1, c0:c1]


def seam_stats(target: np.ndarray, src: np.ndarray, row: int, col: int, nodata: float) -> dict:
    """Distribution of src - target where both are valid (call before paste_first_valid)."""
    s, t = _overlap(target, src, row, col)
    if s is None:
        return {"overlap_cells": 0}
    both = (s != nodata) & (t != nodata)
    if not both.any():
        return {"overlap_cells": 0}
    d = s[both].astype(np.float64) - t[both]
    return {"overlap_cells": int(both.sum()), "median_m": float(np.median(d)),
            "p99_abs_m": float(np.percentile(np.abs(d), 99)), "share_gt_1m": float((np.abs(d) > 1).mean()),
            "max_abs_diff_m": float(np.abs(d).max())}
