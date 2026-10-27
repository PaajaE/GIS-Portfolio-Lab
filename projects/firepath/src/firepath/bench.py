"""Benchmark (M2 first rows; M7 repeats it on the build Mac): Rust kernels vs the Python reference.

Input: the real Mangum 90 m model field (hand-set parameters, run.setup), cropped to square windows of
increasing size centred on the first usable perimeter; each run starts from that perimeter and stops
after 24 h. Release build of the Rust extension (maturin via uv). Harness: stdlib timeit.repeat
(number=1); min and median reported. Reference = NumPy level set + Python label-setting graph; Rust =
the same algorithms (bit-identical level set, graph within 1e-9; tests/test_kernels.py).
Scenario rows: 10 independent runs (k scaled 0.6..1.5) through ensemble.run_many at several thread counts.

  uv run python -m firepath.bench [--fire mangum] [--quick]
Writes benchmarks/propagation.json.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import timeit

import numpy as np

from .ensemble import run_many
from .field import Params, hour
from .harvest import PROJECT
from .kernels import propagate_graph
from .levelset import propagate_hybrid, propagate_levelset
from .reference import SpreadField, propagate
from .run import setup

T_RUN = 24 * 60.0


def hardware() -> dict:
    def run(*cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
        except Exception:
            return None

    cpu = run("sysctl", "-n", "machdep.cpu.brand_string")
    if cpu is None and os.path.exists("/proc/cpuinfo"):
        cpu = next((ln.split(":", 1)[1].strip() for ln in open("/proc/cpuinfo") if ln.startswith("model name")),
                   platform.processor())
    mem = run("sysctl", "-n", "hw.memsize")
    if mem is None and os.path.exists("/proc/meminfo"):
        mem = str(int(open("/proc/meminfo").readline().split()[1]) * 1024)
    import scipy
    return {"cpu": cpu, "logical_cpus": os.cpu_count(), "ram_gb": round(int(mem) / 2**30, 1) if mem else None,
            "os": platform.platform(), "python": platform.python_version(), "numpy": np.__version__,
            "scipy": scipy.__version__, "rustc": run("rustc", "--version"),
            "threads": "single-threaded kernels; scenario rows use a thread pool (ensemble.run_many)"}


def crop_field(S, half):
    st, inside = S["st"], S["inside"]
    rr, cc = np.nonzero(inside)
    r0, c0 = int(rr.mean()), int(cc.mean())
    nr, nc = inside.shape
    r_a, r_b = max(0, r0 - half), min(nr, r0 + half)
    c_a, c_b = max(0, c0 - half), min(nc, c0 + half)
    w = (slice(r_a, r_b), slice(c_a, c_b))
    hrs = [h for h, t in zip(S["hrs"], np.r_[-np.inf, S["t_change"]]) if t <= T_RUN]
    rs, es, ts = [], [], []
    for h in hrs:
        r, e, t = hour(st, S["u"][h], S["v"][h], Params())
        rs.append(r[w])
        es.append(e[w])
        ts.append(t[w])
    f = SpreadField(S["t_change"][:len(hrs) - 1], np.stack(rs), np.stack(es), np.stack(ts),
                    np.ascontiguousarray(st.burnable[w]), S["cell"],
                    tan_slope=np.ascontiguousarray(S["tan_s"][w]), upslope=np.ascontiguousarray(S["up"][w]))
    return f, np.ascontiguousarray(inside[w])


def timed(fn, repeat):
    t = timeit.repeat(fn, number=1, repeat=repeat)
    return round(min(t), 3), round(float(np.median(t)), 3)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fire", default="mangum")
    ap.add_argument("--quick", action="store_true", help="smallest size only, no scenario rows")
    a = ap.parse_args(argv)
    S = setup(a.fire, 90)
    halves = (32,) if a.quick else (32, 64, 128)
    rows = []
    for half in halves:
        f, inside = crop_field(S, half)
        kw = dict(inside=inside, t_stop=T_RUN)
        row = {"shape": list(f.shape), "cells": int(f.burnable.size), "hours": int(f.r_head.shape[0])}
        g_ref, g_rs = propagate(f, radius=8, **kw), propagate_graph(f, radius=8, **kw)
        fin = np.isfinite(g_ref.arrival)
        row["graph_r8"] = {"cells_reached": int(fin.sum()),
                           "max_abs_diff_min": float(np.max(np.abs(g_ref.arrival[fin] - g_rs.arrival[fin]),
                                                            initial=0.0))}
        ls_ref = propagate_levelset(f, order=5, **kw)
        ls_rs = propagate_levelset(f, order=5, backend="rust", **kw)
        row["levelset"] = {"identical": bool(np.array_equal(ls_ref.arrival, ls_rs.arrival))}
        hy_ref = propagate_hybrid(f, graph="python", **kw)
        hy_rs = propagate_hybrid(f, **kw)
        row["hybrid"] = {"cells_reached": int(np.isfinite(hy_rs.arrival).sum()),
                         "max_abs_diff_min": float(np.nanmax(np.abs(np.where(np.isfinite(hy_ref.arrival),
                                                                             hy_ref.arrival - hy_rs.arrival, 0))))}
        for name, ref, rs in (("graph_r8", lambda: propagate(f, radius=8, **kw),
                               lambda: propagate_graph(f, radius=8, **kw)),
                              ("levelset", lambda: propagate_levelset(f, order=5, **kw),
                               lambda: propagate_levelset(f, order=5, backend="rust", **kw)),
                              ("hybrid", lambda: propagate_hybrid(f, graph="python", **kw),
                               lambda: propagate_hybrid(f, **kw))):
            (rmin, rmed), (smin, smed) = timed(ref, 1), timed(rs, 3)
            row[name].update(reference_min_s=rmin, reference_median_s=rmed, rust_min_s=smin, rust_median_s=smed,
                             speedup_median=round(rmed / smed, 1))
        rows.append(row)
        print(json.dumps(row), flush=True)

    scen = []
    if not a.quick:
        f, inside = crop_field(S, 64)
        fs = [SpreadField(f.t_change, f.r_head * k, f.ecc, f.theta, f.burnable, f.cell_m, tan_slope=f.tan_slope,
                          upslope=f.upslope) for k in np.linspace(0.6, 1.5, 10)]
        ref = run_many(fs, workers=1, inside=inside, t_stop=T_RUN)
        for w in sorted({1, 2, 4, os.cpu_count() or 1}):
            got = run_many(fs, workers=w, inside=inside, t_stop=T_RUN)
            same = all(np.array_equal(x.arrival, y.arrival) for x, y in zip(ref, got))
            tmin, tmed = timed(lambda: run_many(fs, workers=w, inside=inside, t_stop=T_RUN), 3)
            scen.append({"workers": w, "scenarios": len(fs), "shape": list(f.shape), "identical_to_1": same,
                         "min_s": tmin, "median_s": tmed})
            print(scen[-1], flush=True)
        for s in scen:
            s["speedup_vs_1"] = round(scen[0]["median_s"] / s["median_s"], 2)

    out = {"algorithm": "time-dependent elliptical spread on the Mangum 90 m field (slope-plane, hourly HRRR): "
                        "graph = label-setting on a radius-8 stencil; levelset = WENO5/LLF/TVD-RK3 narrow band; "
                        "hybrid (HY, D1) = level set then graph seeded with its arrivals",
           "input": f"{a.fire} 90 m model field, hand-set parameters, windows centred on the first perimeter, "
                    f"24 h from it",
           "hardware": hardware(),
           "harness": "timeit.repeat(number=1); reference repeat=1, Rust repeat=3; scenario rows repeat=3",
           "sizes": rows, "scenarios": scen}
    p = PROJECT / "benchmarks" / "propagation.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(out, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
