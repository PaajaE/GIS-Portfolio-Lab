"""Benchmark: Rust terrain kernels vs the SciPy/NumPy reference (spec §12 fields).

Input: square crops of the real 5 m AOI DEM (centre of the mosaic) at 1024², 4096² and 8192² cells.
* window_stats (mean, sd, min, max; strict nodata) at r = 1, 5, 10, 50 vs `window_stats_scipy`
  (scipy.ndimage uniform/minimum/maximum filters + nodata count — C implementations, the fair baseline)
* terrain3x3 (6 outputs) vs `terrain3x3_ref_chunked` (vectorised NumPy, float64, in 1024-row bands so the
  reference does not swap: unchunked it needs ~16 GB at 8192^2 and ran 12x slower than chunked)
Both single-threaded. Release build (maturin). Harness: stdlib `timeit.repeat(number=1)`; min and median.
Each benchmark input is also checked for agreement (same tolerances as the tests).
Full-region production runs (Rust only, incl. GeoTIFF I/O) are read from `terrain_<region>/run.json`.
"""

from __future__ import annotations

import json
import platform
import subprocess
import timeit

import numpy as np
import rasterio
import scipy
from rasterio.windows import Window
from terrain_kernels import terrain3x3, window_stats

from . import config as C
from .terrain_ref import terrain3x3_ref_chunked, window_stats_scipy

SIZES = (1024, 4096, 8192)
RADII = (1, 5, 10, 50)
ND = float(C.OUT_NODATA)


def hardware() -> dict:
    def sysctl(k):
        try:
            return subprocess.run(["sysctl", "-n", k], capture_output=True, text=True, check=True).stdout.strip()
        except Exception:
            return None

    mem = sysctl("hw.memsize")
    return {"cpu": sysctl("machdep.cpu.brand_string") or platform.processor(), "logical_cpus": sysctl("hw.ncpu"),
            "ram_gb": round(int(mem) / 2**30, 1) if mem else None, "os": platform.platform(),
            "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
            "rustc": subprocess.run(["rustc", "--version"], capture_output=True, text=True).stdout.strip() or None,
            "threads": "single-threaded (both implementations)"}


def crop(n: int) -> np.ndarray:
    with rasterio.open(C.INTERIM / "dem_5m_aoi.tif") as s:
        r0, c0 = (s.height - n) // 2, (s.width - n) // 2
        return np.ascontiguousarray(s.read(1, window=Window(c0, r0, n, n)), dtype=np.float32)


def agree_ws(got, ref) -> bool:
    ok = True
    for g, (k, r) in zip(got, ref.items()):
        v = r != ND
        ok &= bool(np.array_equal(g == ND, r == ND))
        if k in ("min", "max"):
            ok &= bool(np.array_equal(g[v], r[v]))
        elif k == "mean":
            ok &= bool(np.allclose(g[v], r[v], rtol=1e-6, atol=0))
        else:
            ok &= bool(np.allclose(g[v], r[v], rtol=0, atol=1e-4))
    return ok


def agree_3x3(got, ref) -> bool:
    return all(np.array_equal(g == ND, r == ND) and np.allclose(g[r != ND], r[r != ND], rtol=1e-6, atol=1e-6)
               for g, r in zip(got, ref.values()))


def timed(fn, repeat):
    t = timeit.repeat(fn, number=1, repeat=repeat)
    return round(min(t), 4), round(float(np.median(t)), 4)


def row(kernel, n, r, ref_fn, rs_fn, agree, repeat):
    ok = agree(rs_fn(), ref_fn())
    ref_min, ref_med = timed(ref_fn, repeat)
    rs_min, rs_med = timed(rs_fn, repeat)
    out = {"kernel": kernel, "cells": n * n, "shape": [n, n], "radius_cells": r,
           "window": f"{2 * r + 1}x{2 * r + 1}" if r is not None else "3x3", "agree": ok,
           "reference_min_s": ref_min, "reference_median_s": ref_med, "rust_min_s": rs_min, "rust_median_s": rs_med,
           "speedup_median": round(ref_med / rs_med, 2)}
    print(out, flush=True)
    return out


def main() -> None:
    rows = []
    for n in SIZES:
        z = crop(n)
        rep = 5 if n <= 1024 else 3
        rows.append(row("terrain3x3", n, None, lambda: terrain3x3_ref_chunked(z, C.CELL_M, ND),
                        lambda: terrain3x3(z, float(C.CELL_M), ND), agree_3x3, rep))
        for r in RADII:
            rows.append(row("window_stats", n, r, lambda: window_stats_scipy(z, r, ND),
                            lambda: window_stats(z, r, ND), agree_ws, rep))
    production = {}
    for region in C.REGIONS:
        p = C.INTERIM / f"terrain_{region}" / "run.json"
        if p.exists():
            production[region] = {k: v for k, v in json.loads(p.read_text()).items() if k != "layer_bytes"}
    out = {"algorithms": {
        "window_stats": "sliding sums (f64, mean-centred) for mean/sd + van Herk/Gil-Werman min/max, "
                        "strict nodata via a nodata-count table; reference = scipy.ndimage C filters",
        "terrain3x3": "single 3x3 pass: Horn slope/aspect, Zevenbergen-Thorne curvatures, Riley TRI; "
                      "reference = vectorised NumPy float64 in 1024-row bands"},
        "input": "centre crops of data/interim/dem_5m_aoi.tif (USGS 3DEP 2017, 5 m)",
        "harness": "timeit.repeat(number=1); repeat 5 (1024²) or 3", "hardware": hardware(),
        "rows": rows, "production_runs_rust_only": production}
    p = C.ROOT / "benchmarks" / "terrain_kernels.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
