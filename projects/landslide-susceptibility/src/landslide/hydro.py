"""Hydrology on a 10 m DEM (PLAN §3-4): D8 flow, contributing area, HAND and distance to channel.

* DEM 10 m = exact 2 x 2 block mean of the 5 m mosaic (strict nodata), on the 10 m UTM lattice.
* pysheds: fill pits -> fill depressions -> resolve flats -> D8 flow direction -> accumulation.
  Grid edges drain off the grid; the 2 km buffer keeps that away from the counties.
* Channels for the predictors: contributing area >= CHANNEL_KM2 (0.1 km^2, the middle slope-unit threshold).
* HAND (m): height above the drainage cell reached along the D8 path (pysheds `compute_hand`, on the
  conditioned DEM); distance to channel (m): straight-line distance to that drainage cell.

Outputs in data/interim/hydro_<region>/: dem_10m.tif, fdir_10m.tif (pysheds dirmap), acc_10m.tif (cells),
and on the 5 m grid (each 10 m value repeated 2 x 2): log_area.tif (log10 m^2), hand.tif, dist_channel.tif.
"""

from __future__ import annotations

import json
import time

import numpy as np
import rasterio
from pysheds.grid import Grid
from pysheds.sview import Raster, ViewFinder

# pysheds 0.5 (latest) still calls np.in1d, removed in NumPy 2.4; np.isin is the documented replacement
# with identical results for the 1-D arrays pysheds passes. Remove when pysheds is updated.
if not hasattr(np, "in1d"):
    np.in1d = np.isin

from . import config as C
from .dem import block_mean

CELL10 = 10
CHANNEL_KM2 = 0.1
ND = np.float32(C.OUT_NODATA)
DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)  # N, NE, E, SE, S, SW, W, NW (pysheds default)
# (drow, dcol) for each D8 code
STEP = {64: (-1, 0), 128: (-1, 1), 1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1)}


def dem10(region: str):
    """10 m block mean of the 5 m mosaic; returns array, transform and the (row, col) offset in 5 m cells."""
    with rasterio.open(C.INTERIM / f"dem_5m_{region}.tif") as s:
        z, tr = s.read(1), s.transform
    # first 5 m row/col whose top/left edge lies on the 10 m lattice
    c0 = 0 if tr.c % CELL10 == 0 else 1
    r0 = 0 if tr.f % CELL10 == 0 else 1
    h, w = (z.shape[0] - r0) // 2 * 2, (z.shape[1] - c0) // 2 * 2
    z10 = block_mean(z[r0 : r0 + h, c0 : c0 + w], C.OUT_NODATA, 2, C.OUT_NODATA)
    tr10 = rasterio.transform.from_origin(tr.c + c0 * C.CELL_M, tr.f - r0 * C.CELL_M, CELL10, CELL10)
    return z10, tr10, (r0, c0), z.shape


def _write(path, a, tr, nodata):
    prof = {"driver": "GTiff", "count": 1, "dtype": a.dtype.name, "nodata": nodata, "crs": C.CRS,
            "transform": tr, "height": a.shape[0], "width": a.shape[1], "compress": "deflate", "tiled": True,
            "blockxsize": 512, "blockysize": 512, "BIGTIFF": "IF_SAFER"}
    with rasterio.open(path, "w", **prof) as d:
        d.write(a, 1)


def to5(a10: np.ndarray, off: tuple[int, int], shape5: tuple[int, int], nodata) -> np.ndarray:
    """Repeat each 10 m cell 2 x 2 onto the 5 m grid (nodata where the 10 m grid does not reach)."""
    out = np.full(shape5, nodata, dtype=a10.dtype)
    rep = np.repeat(np.repeat(a10, 2, axis=0), 2, axis=1)
    r0, c0 = off
    out[r0 : r0 + rep.shape[0], c0 : c0 + rep.shape[1]] = rep
    return out


def run_region(region: str) -> dict:
    t0 = time.time()
    out = C.INTERIM / f"hydro_{region}"
    out.mkdir(parents=True, exist_ok=True)
    z10, tr10, off, shape5 = dem10(region)
    p10 = out / "dem_10m.tif"
    _write(p10, z10, tr10, float(ND))
    grid = Grid.from_raster(str(p10))
    dem = grid.read_raster(str(p10))
    flooded = grid.fill_depressions(grid.fill_pits(dem))
    cond = grid.resolve_flats(flooded)
    fdir = grid.flowdir(cond, dirmap=DIRMAP)
    acc = grid.accumulation(fdir, dirmap=DIRMAP)
    nd = z10 == ND
    fd = np.asarray(fdir).astype(np.int16)
    fd[nd] = 0
    accf = np.asarray(acc, dtype=np.float32)
    accf[nd] = ND
    _write(out / "fdir_10m.tif", fd.astype(np.uint8), tr10, 0)
    _write(out / "acc_10m.tif", accf, tr10, float(ND))
    chan = (accf != ND) & (accf * CELL10 * CELL10 >= CHANNEL_KM2 * 1e6)
    hidx = np.asarray(grid.compute_hand(fdir, cond, Raster(chan, viewfinder=ViewFinder(
        affine=dem.affine, shape=dem.shape, crs=dem.crs, nodata=False)), dirmap=DIRMAP,
                                         return_index=True))
    h, w = z10.shape
    ok = (hidx >= 0) & ~nd
    safe = np.where(ok, hidx, 0)
    rows, cols = np.divmod(safe, w)
    rr, cc = np.mgrid[0:h, 0:w]
    dist = np.where(ok, np.hypot(rows - rr, cols - cc) * CELL10, ND).astype(np.float32)
    zc = np.asarray(cond, dtype=np.float64)
    hand = np.where(ok, zc - zc.ravel()[safe], ND).astype(np.float32)
    log_area = np.where(accf != ND, np.log10(np.maximum(accf, 1) * CELL10 * CELL10), ND).astype(np.float32)
    with rasterio.open(C.INTERIM / f"dem_5m_{region}.tif") as s:
        prof5 = s.profile
    for name, a in (("log_area", log_area), ("hand", hand), ("dist_channel", dist)):
        a5 = to5(a, off, shape5, ND)
        _write(out / f"{name}.tif", a5, prof5["transform"], float(ND))
    rep = {"region": region, "shape_10m": [h, w], "channel_km2": CHANNEL_KM2,
           "channel_cells_share": float(chan.mean()), "acc_min": float(accf[~nd].min()),
           "no_drainage_share": float((~ok & ~nd).mean()), "seconds": round(time.time() - t0, 1)}
    (out / "report.json").write_text(json.dumps(rep, indent=1))
    return rep


if __name__ == "__main__":
    for r in C.REGIONS:
        print(run_region(r), flush=True)
