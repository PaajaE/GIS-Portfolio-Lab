"""Reference implementations (the oracle) for the Rust terrain kernels.

Same definitions and semantics as `rust/src/lib.rs`, written independently with NumPy/SciPy:
* `terrain3x3_ref`: vectorised slices in float64 (Horn slope/aspect; Zevenbergen-Thorne curvature; Riley TRI)
* `window_stats_loop`: explicit loops — slow, for small fixtures only
* `window_stats_scipy`: SciPy C filters (uniform/minimum/maximum) with a nodata count — the fair
  reference for the benchmark

Strict semantics: a window containing nodata/NaN, or extending past the grid, gives nodata.
Row 0 is north; x east, y north. Curvatures are second derivatives of z (1/m): profile along the
gradient (> 0 concave), plan along the contour (> 0 convergent hollow).
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

FLAT_GRADIENT = 1e-9


def _bad(a: np.ndarray, nodata: float) -> np.ndarray:
    return (a == nodata) | ~np.isfinite(a)


def terrain3x3_ref(z: np.ndarray, cell: float, nodata: float) -> dict[str, np.ndarray]:
    z = np.asarray(z, dtype=np.float32)
    h, w = z.shape
    out = {k: np.full((h, w), nodata, np.float32) for k in
           ("slope_deg", "northness", "eastness", "profile_curv", "plan_curv", "tri")}
    if h < 3 or w < 3:
        return out
    zf = z.astype(np.float64)
    bad = _bad(z, nodata)

    def s(di, dj):  # neighbour (di, dj) in {0,1,2}^2 for every interior cell
        return zf[di : h - 2 + di, dj : w - 2 + dj]

    z1, z2, z3, z4, z5, z6, z7, z8, z9 = (s(a, b) for a in range(3) for b in range(3))
    win_bad = np.zeros((h - 2, w - 2), bool)
    for a in range(3):
        for b in range(3):
            win_bad |= bad[a : h - 2 + a, b : w - 2 + b]
    p = ((z3 + 2 * z6 + z9) - (z1 + 2 * z4 + z7)) / (8 * cell)
    q = ((z1 + 2 * z2 + z3) - (z7 + 2 * z8 + z9)) / (8 * cell)
    g = np.hypot(p, q)
    l2 = cell * cell
    zxx = ((z4 + z6) / 2 - z5) * 2 / l2
    zyy = ((z2 + z8) / 2 - z5) * 2 / l2
    zxy = (-z1 + z3 + z7 - z9) / (4 * l2)
    gx = (z6 - z4) / (2 * cell)
    gy = (z2 - z8) / (2 * cell)
    g2 = gx * gx + gy * gy
    with np.errstate(invalid="ignore", divide="ignore"):
        flat = g <= FLAT_GRADIENT
        east = np.where(flat, 0.0, -p / g)
        north = np.where(flat, 0.0, -q / g)
        cflat = np.sqrt(g2) <= FLAT_GRADIENT
        prof = np.where(cflat, 0.0, (zxx * gx**2 + 2 * zxy * gx * gy + zyy * gy**2) / g2)
        plan = np.where(cflat, 0.0, (zxx * gy**2 - 2 * zxy * gx * gy + zyy * gx**2) / g2)
    tri = np.sqrt(sum((v - z5) ** 2 for v in (z1, z2, z3, z4, z6, z7, z8, z9)))
    vals = {"slope_deg": np.degrees(np.arctan(g)), "northness": north, "eastness": east,
            "profile_curv": prof, "plan_curv": plan, "tri": tri}
    for k, v in vals.items():
        inner = out[k][1:-1, 1:-1]
        inner[:] = np.where(win_bad, nodata, v).astype(np.float32)
    return out


def window_stats_loop(x: np.ndarray, r: int, nodata: float) -> dict[str, np.ndarray]:
    x = np.asarray(x, dtype=np.float32)
    h, w = x.shape
    out = {k: np.full((h, w), nodata, np.float32) for k in ("mean", "sd", "min", "max")}
    for i in range(r, h - r):
        for j in range(r, w - r):
            win = x[i - r : i + r + 1, j - r : j + r + 1]
            if _bad(win, nodata).any():
                continue
            v = win.astype(np.float64)
            out["mean"][i, j], out["sd"][i, j] = v.mean(), v.std()
            out["min"][i, j], out["max"][i, j] = win.min(), win.max()
    return out


def window_stats_scipy(x: np.ndarray, r: int, nodata: float) -> dict[str, np.ndarray]:
    x = np.asarray(x, dtype=np.float32)
    h, w = x.shape
    k = 2 * r + 1
    out = {key: np.full((h, w), nodata, np.float32) for key in ("mean", "sd", "min", "max")}
    if h < k or w < k:
        return out
    bad = _bad(x, nodata)
    xf = np.where(bad, 0.0, x).astype(np.float64)
    off = xf[~bad].mean() if (~bad).any() else 0.0
    d = np.where(bad, 0.0, xf - off)
    nbad = ndimage.uniform_filter(bad.astype(np.float64), k, mode="constant") * k * k
    mean = ndimage.uniform_filter(d, k, mode="constant")
    sq = ndimage.uniform_filter(d * d, k, mode="constant")
    xc = np.where(bad, 0.0, x).astype(np.float32)
    mn = ndimage.minimum_filter(xc, k, mode="constant")
    mx = ndimage.maximum_filter(xc, k, mode="constant")
    valid = nbad < 0.5
    valid[:r, :] = valid[h - r :, :] = False
    valid[:, :r] = valid[:, w - r :] = False
    out["mean"][valid] = (mean + off)[valid]
    out["sd"][valid] = np.sqrt(np.maximum(sq - mean * mean, 0.0))[valid]
    out["min"][valid] = mn[valid]
    out["max"][valid] = mx[valid]
    return out


def terrain3x3_ref_chunked(z: np.ndarray, cell: float, nodata: float, rows: int = 1024) -> dict[str, np.ndarray]:
    """`terrain3x3_ref` applied to row bands (1-row overlap) so large grids do not exhaust RAM.
    Identical results; used as the benchmark reference."""
    h, w = z.shape
    out = {k: np.full((h, w), nodata, np.float32) for k in
           ("slope_deg", "northness", "eastness", "profile_curv", "plan_curv", "tri")}
    for r0 in range(0, h, rows):
        a, b = max(r0 - 1, 0), min(r0 + rows + 1, h)
        part = terrain3x3_ref(z[a:b], cell, nodata)
        for k in out:
            out[k][r0 : min(r0 + rows, h)] = part[k][r0 - a : r0 - a + min(rows, h - r0)]
    # rows at the grid edge stay nodata (strict)
    for k in out:
        out[k][0] = out[k][-1] = nodata
    return out
