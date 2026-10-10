"""Slope units as hydrological half-basins (Carrara et al. 1991), PLAN §3.

On the 10 m D8 grid from `hydro`:
1. Channels: contributing area >= A (A = 0.05 / 0.1 / 0.2 km^2; MAUP sensitivity).
2. Links: channel cells are grouped into segments between junctions (a junction has >= 2 upstream channel
   neighbours); every link is named by its most downstream cell.
3. Each hillslope cell follows D8 to the first channel cell it reaches; it belongs to that cell's link.
4. Side: the sign of the cross product between the channel's flow direction at the entry cell and the vector
   from the entry cell to the last hillslope cell gives left / right bank; collinear entries (the hollow
   above a channel head) form a third "head" unit. Channel cells join their link's left unit.
5. Units smaller than A_MIN (0.01 km^2) are merged into the neighbour sharing the longest boundary (repeated
   until none remain). Cells that leave the grid without reaching a channel get label 0 (grid edge only).

Pointer jumping on the D8 successor array keeps every step vectorised (O(N log L)).
Output: data/interim/units_<region>/units_<A>.tif (uint32, 10 m) and a cell-count table.
"""

from __future__ import annotations

import json

import numpy as np
import rasterio

from . import config as C
from .hydro import CELL10, STEP

THRESHOLDS_KM2 = (0.05, 0.1, 0.2)
A_MIN_KM2 = 0.01


def successor(fdir: np.ndarray) -> np.ndarray:
    """Flat index of the D8 downstream cell; -1 where the flow leaves the grid or fdir is not a D8 code."""
    h, w = fdir.shape
    rr, cc = np.mgrid[0:h, 0:w]
    nxt = np.full(h * w, -1, np.int64)
    for code, (dr, dc) in STEP.items():
        m = fdir == code
        r2, c2 = rr[m] + dr, cc[m] + dc
        inside = (r2 >= 0) & (r2 < h) & (c2 >= 0) & (c2 < w)
        idx = np.flatnonzero(m.ravel())
        nxt[idx[inside]] = r2[inside] * w + c2[inside]
    return nxt


def jump_to_root(ptr: np.ndarray) -> np.ndarray:
    """Follow ptr until a fixed point (ptr[i] == i) by pointer doubling."""
    root = ptr.copy()
    for _ in range(64):
        nxt = root[root]
        if np.array_equal(nxt, root):
            return root
        root = nxt
    raise RuntimeError("pointer jumping did not converge (cycle in flow directions?)")


def half_basins(fdir: np.ndarray, acc: np.ndarray, threshold_cells: float, min_cells: int) -> np.ndarray:
    h, w = fdir.shape
    n = h * w
    nxt = successor(fdir)
    idx = np.arange(n)
    chan = (acc.ravel() >= threshold_cells) & (acc.ravel() > 0)
    # --- links: channel segments between junctions
    up_chan = np.bincount(nxt[chan & (nxt >= 0)], minlength=n)  # channel cells draining into each cell
    junction = up_chan >= 2
    down_is_chan = np.zeros(n, bool)
    v = nxt >= 0
    down_is_chan[v] = chan[nxt[v]]
    cont = chan & down_is_chan & ~np.where(v, junction[np.where(v, nxt, 0)], False)
    ptr = np.where(cont, nxt, idx)
    link = jump_to_root(ptr)  # most downstream cell of the segment
    # --- hillslope cells: last hillslope cell before the channel (or before leaving the grid)
    stop = chan | ~v | np.where(v, chan[np.where(v, nxt, 0)], False)
    ptr = np.where(stop, idx, nxt)
    last = jump_to_root(ptr)
    entry = np.where(chan, idx, nxt[last])  # channel cell reached (-1: left the grid)
    reached = (entry >= 0) & chan[np.where(entry >= 0, entry, 0)]
    # --- side of the channel
    e = np.where(reached, entry, 0)
    er, ec = np.divmod(e, w)
    lr, lc = np.divmod(last, w)
    # channel flow direction at the entry cell, from its D8 code (defined even where the flow leaves the grid)
    dr_lut, dc_lut = np.zeros(256, np.int64), np.zeros(256, np.int64)
    for code, (dr, dc) in STEP.items():
        dr_lut[code], dc_lut[code] = dr, dc
    code = fdir.ravel()[e]
    ur, uc = dr_lut[code], dc_lut[code]
    vr, vc = lr - er, lc - ec  # entry cell -> last hillslope cell
    cross = ur * vc - uc * vr
    side = np.where(cross > 0, 1, np.where(cross < 0, 2, 3))
    side[chan] = 1
    raw = np.where(reached, link[e] * 4 + side, -1)
    # dense labels 1..K; 0 = not reached (-1 sorts first in np.unique)
    uniq, lab = np.unique(raw, return_inverse=True)
    if uniq[0] != -1:
        lab = lab + 1
    lab = lab.reshape(h, w)
    return merge_small(lab, min_cells)


def merge_small(lab: np.ndarray, min_cells: int, max_iter: int = 50) -> np.ndarray:
    """Merge units below min_cells into the 4-neighbour unit with the longest shared boundary."""
    lab = lab.copy()
    for _ in range(max_iter):
        cnt = np.bincount(lab.ravel())
        small = (cnt < min_cells) & (cnt > 0)
        small[0] = False
        if not small.any():
            break
        a = np.concatenate([lab[:, :-1].ravel(), lab[:-1, :].ravel(), lab[:, 1:].ravel(), lab[1:, :].ravel()])
        b = np.concatenate([lab[:, 1:].ravel(), lab[1:, :].ravel(), lab[:, :-1].ravel(), lab[:-1, :].ravel()])
        m = (a != b) & small[a] & (b > 0)
        if not m.any():
            break
        key = a[m] * (lab.max() + 1) + b[m]
        k, n = np.unique(key, return_counts=True)
        src, dst = np.divmod(k, lab.max() + 1)
        order = np.lexsort((-dst, -n, src))  # per source: longest boundary first, ties -> larger id
        src, dst = src[order], dst[order]
        first = np.r_[True, src[1:] != src[:-1]]
        target = np.arange(lab.max() + 1)
        target[src[first]] = dst[first]
        # avoid swaps (a->b and b->a in the same round): keep the merge into the larger unit only
        swap = target[target[src[first]]] == src[first]
        bad = src[first][swap & (cnt[src[first]] >= cnt[dst[first]])]
        target[bad] = bad
        lab = target[lab]
    _, lab2 = np.unique(lab, return_inverse=True)
    lab2 = lab2.reshape(lab.shape)
    return lab2 if lab.min() == 0 else lab2 + 1


def run_region(region: str = "aoi") -> dict:
    d = C.INTERIM / f"hydro_{region}"
    with rasterio.open(d / "fdir_10m.tif") as s:
        fdir, prof = s.read(1), s.profile
    with rasterio.open(d / "acc_10m.tif") as s:
        acc = s.read(1)
    out = C.INTERIM / f"units_{region}"
    out.mkdir(parents=True, exist_ok=True)
    rep = {}
    min_cells = int(round(A_MIN_KM2 * 1e6 / CELL10**2))
    for a_km2 in THRESHOLDS_KM2:
        lab = half_basins(fdir, acc, a_km2 * 1e6 / CELL10**2, min_cells).astype(np.uint32)
        p = prof | {"dtype": "uint32", "nodata": 0, "compress": "deflate"}
        with rasterio.open(out / f"units_{a_km2:g}.tif", "w", **p) as dst:
            dst.write(lab, 1)
        cnt = np.bincount(lab.ravel())[1:]
        cnt = cnt[cnt > 0]
        rep[f"{a_km2:g}"] = {"n_units": int(len(cnt)), "median_km2": float(np.median(cnt) * CELL10**2 / 1e6),
                             "p10_p90_km2": [float(np.percentile(cnt, q) * CELL10**2 / 1e6) for q in (10, 90)],
                             "unlabelled_share": float((lab == 0).mean()),
                             "below_min_after_merge": int((cnt < min_cells).sum())}
        print(a_km2, rep[f"{a_km2:g}"], flush=True)
    (out / "report.json").write_text(json.dumps(rep, indent=1))
    return rep


if __name__ == "__main__":
    run_region("aoi")
