"""Benchmark: per-parcel opening + connected components, Rust vs scipy reference.

Input: the real moderate-scenario feasibility mask for Amherst, cropped to row
bands of increasing size. Release build of the Rust extension (maturin default).
Harness: stdlib timeit.repeat (number=1); min and median reported.
"""

from __future__ import annotations

import json
import platform
import subprocess
import timeit

import numpy as np
import rasterio
import scipy
from parcel_kernels import screen_patches

from . import analyze as A
from . import config as C
from .patches import screen_patches_reference


def hardware() -> dict:
    def sysctl(k):
        try:
            return subprocess.run(["sysctl", "-n", k], capture_output=True, text=True, check=True).stdout.strip()
        except Exception:
            return None

    mem = sysctl("hw.memsize")
    return {
        "cpu": sysctl("machdep.cpu.brand_string") or platform.processor(),
        "logical_cpus": sysctl("hw.ncpu"),
        "ram_gb": round(int(mem) / 2**30, 1) if mem else None,
        "os": platform.platform(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "rustc": subprocess.run(["rustc", "--version"], capture_output=True, text=True).stdout.strip() or None,
        "threads": "single-threaded (both implementations)",
    }


def main() -> None:
    with rasterio.open(C.OUT / "constraints_moderate.tif") as src:
        bits = src.read(1)
    pidx = A.pidx()
    feasible_full = (pidx > 0) & (bits == 0)
    n = A.n_parcels()
    min_cells = int(np.ceil(C.MIN_PATCH_M2 / A.grid()["cell_m"] ** 2))
    h = pidx.shape[0]
    rows = []
    for frac in (0.125, 0.25, 0.5, 1.0):
        r1 = int(round(h * frac))
        p = np.ascontiguousarray(pidx[:r1])
        f = np.ascontiguousarray(feasible_full[:r1])
        args = (p, f, n, C.OPEN_SIZE_CELLS, C.CONNECTIVITY, min_cells)
        ref = screen_patches_reference(*args)
        got = screen_patches(*args)
        same = all(np.array_equal(a, b) for a, b in zip(ref, got))
        t_ref = timeit.repeat(lambda: screen_patches_reference(*args), number=1, repeat=3)
        t_rs = timeit.repeat(lambda: screen_patches(*args), number=1, repeat=7)
        row = {
            "cells": int(p.size),
            "shape": list(p.shape),
            "parcels_present": int(len(np.unique(p)) - 1),
            "identical": bool(same),
            "reference_min_s": round(min(t_ref), 4),
            "reference_median_s": round(float(np.median(t_ref)), 4),
            "rust_min_s": round(min(t_rs), 4),
            "rust_median_s": round(float(np.median(t_rs)), 4),
        }
        row["speedup_median"] = round(row["reference_median_s"] / row["rust_median_s"], 2)
        rows.append(row)
        print(row)
    # scenarios + leave-one-out (all categories except no_data) + one call per sensitivity row
    n_sens = len(json.loads((C.OUT / "sensitivity.json").read_text()))
    calls = len(C.SCENARIO_ORDER) + (len(A.BITS) - 1) + n_sens
    full = rows[-1]
    out = {
        "algorithm": (
            "per-parcel k x k square opening (k=%d, 2 m cells) then 4-connected component labelling "
            "restricted to one parcel; reference = scipy.ndimage per parcel bounding box, "
            "Rust = single raster pass (separable run-length erosion/dilation + union-find)" % C.OPEN_SIZE_CELLS
        ),
        "hardware": hardware(),
        "harness": "timeit.repeat(number=1); reference repeat=3, Rust repeat=7",
        "sizes": rows,
        "pipeline_estimate": {
            "kernel_calls_per_full_run": calls,
            "reference_s": round(calls * full["reference_median_s"], 1),
            "rust_s": round(calls * full["rust_median_s"], 1),
        },
    }
    path = C.ROOT / "benchmarks" / "patch_kernel.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
