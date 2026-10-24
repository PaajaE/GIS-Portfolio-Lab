"""Terrain predictors from the 5 m DEM mosaics with the Rust kernels (PLAN §4, §10).

Processed in 4096 x 4096 tiles with a halo wider than the largest window, so every output cell sees its
full window; cells whose window crosses the mosaic edge or nodata are nodata (strict). The mosaic extends
2 km beyond the counties, so the analysis domain is never affected by the edge.

Outputs (float32 GeoTIFF, EPSG:26917, 5 m) in data/interim/terrain_<region>/:
  slope_deg, northness, eastness, tri          3 x 3 on the DEM
  profc_5, planc_5                             3 x 3 curvature on the DEM (1/m)
  profc_15, planc_15                           3 x 3 curvature on the DEM smoothed by a 15 m box mean
  relief_50, tpi_50                            max - min and z - mean, 105 m square (r = 10 cells)
  relief_250, tpi_250                          same, 505 m square (r = 50 cells)
  rough_25                                     sd of slope, 55 m square (r = 5 cells)
Window "r" is the half-width; the names give the nominal radius in metres.
"""

from __future__ import annotations

import json
import time

import numpy as np
import rasterio
from rasterio.windows import Window
from terrain_kernels import terrain3x3, window_stats

from . import config as C

TILE = 4096
R_SMOOTH, R_50, R_250, R_ROUGH = 1, 10, 50, 5
HALO = R_250 + 4  # largest window + the 3x3 and smoothing passes
LAYERS = ("slope_deg", "northness", "eastness", "tri", "profc_5", "planc_5", "profc_15", "planc_15",
          "relief_50", "tpi_50", "relief_250", "tpi_250", "rough_25")
ND = np.float32(C.OUT_NODATA)


def _diff(a, b):
    """a - b with strict nodata."""
    out = np.where((a == ND) | (b == ND), ND, a - b)
    return out.astype(np.float32)


def compute_tile(z: np.ndarray, cell: float = C.CELL_M) -> tuple[dict[str, np.ndarray], int]:
    """All predictor layers for one (haloed) DEM tile; returns the layers and the number of kernel calls."""
    nd = float(ND)
    out = {}
    s, n, e, pc, plc, tri = terrain3x3(z, cell, nd)
    out.update(slope_deg=s, northness=n, eastness=e, tri=tri, profc_5=pc, planc_5=plc)
    zs = window_stats(z, R_SMOOTH, nd)[0]
    _, _, _, pc15, plc15, _ = terrain3x3(np.ascontiguousarray(zs), cell, nd)
    out.update(profc_15=pc15, planc_15=plc15)
    for r, tag in ((R_50, "50"), (R_250, "250")):
        m, _, mn, mx = window_stats(z, r, nd)
        out[f"relief_{tag}"] = _diff(mx, mn)
        out[f"tpi_{tag}"] = _diff(z, m)
    out["rough_25"] = window_stats(s, R_ROUGH, nd)[1]
    return out, 6  # 2 x terrain3x3 + 4 x window_stats


def run_region(region: str) -> dict:
    src_path = C.INTERIM / f"dem_5m_{region}.tif"
    out_dir = C.INTERIM / f"terrain_{region}"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    calls = kernel_s = 0.0
    with rasterio.open(src_path) as src:
        prof = src.profile | {"dtype": "float32", "nodata": float(ND), "compress": "deflate", "predictor": 3,
                              "tiled": True, "blockxsize": 512, "blockysize": 512, "BIGTIFF": "IF_SAFER"}
        dsts = {k: rasterio.open(out_dir / f"{k}.tif", "w", **prof) for k in LAYERS}
        try:
            for r0 in range(0, src.height, TILE):
                for c0 in range(0, src.width, TILE):
                    rr0, cc0 = max(r0 - HALO, 0), max(c0 - HALO, 0)
                    rr1, cc1 = min(r0 + TILE + HALO, src.height), min(c0 + TILE + HALO, src.width)
                    z = src.read(1, window=Window(cc0, rr0, cc1 - cc0, rr1 - rr0))
                    z = np.ascontiguousarray(z, dtype=np.float32)
                    tk = time.perf_counter()
                    layers, nc = compute_tile(z)
                    kernel_s += time.perf_counter() - tk
                    calls += nc
                    h, w = min(TILE, src.height - r0), min(TILE, src.width - c0)
                    sl = (slice(r0 - rr0, r0 - rr0 + h), slice(c0 - cc0, c0 - cc0 + w))
                    for k in LAYERS:
                        dsts[k].write(layers[k][sl], 1, window=Window(c0, r0, w, h))
                    print(f"  {region} tile r{r0} c{c0}", flush=True)
        finally:
            for d in dsts.values():
                d.close()
        cells = src.height * src.width
    rec = {"region": region, "cells": int(cells), "kernel_calls": int(calls), "kernel_seconds": round(kernel_s, 1),
           "wall_seconds": round(time.time() - t0, 1), "tile": TILE, "halo": HALO,
           "layer_bytes": {k: (out_dir / f"{k}.tif").stat().st_size for k in LAYERS}}
    (out_dir / "run.json").write_text(json.dumps(rec, indent=1))
    return rec


if __name__ == "__main__":
    for r in C.REGIONS:
        print(run_region(r), flush=True)
