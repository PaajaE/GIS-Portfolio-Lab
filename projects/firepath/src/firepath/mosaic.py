"""M1a-2 experiment E1: two-fuel mosaic vs a refined-grid reference (validation/M1A2_PREREGISTRATION.md).

Run: uv run python -m firepath.mosaic [case ...] [--candidates a,b]
  cases: iso, lb2, lb4.  Writes validation/m1a2_e1_<case>.json (one file per case).
"""

from __future__ import annotations

import json
import sys
import time
from math import inf
from pathlib import Path

import numpy as np
from shapely import contains_xy
from shapely.geometry import Point

from .ellipse import eccentricity
from .levelset import propagate_hybrid, propagate_levelset
from .reference import propagate, uniform_field

N, CELL, FINE = 61, 30.0, 3
FAST, SLOW = 1.0, 0.25
CENTER = (30, 12)           # coarse cell (row, col)
RADIUS_CELLS = 2.5
T_END = 4000.0               # scoring window: cells with reference arrival <= T_END
T_STOP = 6000.0              # solver horizon (> T_END so candidates are not censored at the window edge)
CASES = {"iso": (1.0, 0.0), "lb2": (2.0, 20.0), "lb4": (4.0, 20.0)}
CANDIDATES = ["levelset5", "dijkstra_r16", "dijkstra_r8", "hybrid"]


def fuel_map(seed: int = 20261009) -> np.ndarray:
    """True = fast fuel. Gaussian-smoothed white noise (sigma 3 cells) thresholded at its median."""
    from scipy.ndimage import gaussian_filter

    noise = np.random.default_rng(seed).standard_normal((N, N))
    field = gaussian_filter(noise, sigma=3.0, mode="reflect")
    return field > np.median(field)


def build(case: str, factor: int):
    lb, wind_deg = CASES[case]
    fast = np.repeat(np.repeat(fuel_map(), factor, 0), factor, 1)
    n = N * factor
    f = uniform_field((n, n), r_head=1.0, ecc=float(eccentricity(lb)) if lb > 1 else 0.0,
                      theta=np.radians(wind_deg), cell_m=CELL / factor)
    f.r_head[0] = np.where(fast, FAST, SLOW)
    disc = Point((CENTER[1] + 0.5) * factor, (CENTER[0] + 0.5) * factor).buffer(RADIUS_CELLS * factor,
                                                                                 quad_segs=64)
    yy, xx = np.mgrid[0:n, 0:n]
    inside = contains_xy(disc, xx + 0.5, yy + 0.5)
    return f, inside


def solve(scheme: str, f, inside):
    t = time.perf_counter()
    if scheme == "levelset5":
        res = propagate_levelset(f, inside=inside, t_stop=T_STOP, order=5)
    elif scheme == "hybrid":
        res = propagate_hybrid(f, inside=inside, t_stop=T_STOP, radius=8)
    else:
        res = propagate(f, radius=int(scheme.split("_r")[1]), inside=inside, t_stop=T_STOP)
    return res.arrival, time.perf_counter() - t


def scored_mask(inside_coarse):
    from scipy.ndimage import distance_transform_edt

    return (~inside_coarse) & (distance_transform_edt(~inside_coarse) >= 5)


def stats(cand, ref, mask):
    m = mask & np.isfinite(ref) & (ref <= T_END)
    rel = (cand[m] - ref[m]) / ref[m]              # +inf if the candidate never arrived by T_STOP
    a = np.abs(rel)
    return {"n": int(m.sum()), "median_abs": float(np.median(a)), "p95_abs": float(np.percentile(a, 95, method="inverted_cdf")),
            "median_signed": float(np.median(rel)), "max_abs": float(a.max()),
            "pass": bool(np.median(a) <= 0.05 and np.percentile(a, 95, method="inverted_cdf") <= 0.10)}


def run_case(case: str, candidates) -> dict:
    out = {"case": case, "lb_wind": CASES[case], "grid": [N, N], "cell_m": CELL, "fine_factor": FINE,
           "fast_slow": [FAST, SLOW], "t_end": T_END, "t_stop": T_STOP, "fast_share": float(fuel_map().mean())}
    ff, fin = build(case, FINE)
    sub = slice(FINE // 2, None, FINE)  # fine cells whose centres coincide with coarse centres
    refs, ref_sec = {}, {}
    for scheme in ("dijkstra_r16", "levelset5"):
        arr, sec = solve(scheme, ff, fin)
        refs[scheme], ref_sec[scheme] = arr[sub, sub], sec
        print(case, "fine", scheme, f"{sec:.0f}s", file=sys.stderr, flush=True)
    cf, cin = build(case, 1)
    mask = scored_mask(cin)
    agree = stats(refs["levelset5"], refs["dijkstra_r16"], mask)
    valid = agree["median_abs"] <= 0.01 and agree["p95_abs"] <= 0.03
    out["reference_agreement"] = agree
    out["reference_valid"] = valid
    out["reference_seconds"] = ref_sec
    ref_mean = 0.5 * (refs["levelset5"] + refs["dijkstra_r16"])
    out["candidates"] = {}
    for scheme in candidates:
        arr, sec = solve(scheme, cf, cin)
        r = {"seconds": sec}
        if valid:
            r["vs_mean"] = stats(arr, ref_mean, mask)
            r["pass"] = r["vs_mean"]["pass"]
        else:
            r["vs_fine_r16"] = stats(arr, refs["dijkstra_r16"], mask)
            r["vs_fine_levelset5"] = stats(arr, refs["levelset5"], mask)
            r["pass"] = r["vs_fine_r16"]["pass"] and r["vs_fine_levelset5"]["pass"]
        out["candidates"][scheme] = r
        print(case, "coarse", scheme, f"{sec:.0f}s", r["pass"], file=sys.stderr, flush=True)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cands = CANDIDATES
    for a in sys.argv[1:]:
        if a.startswith("--candidates="):
            cands = a.split("=", 1)[1].split(",")
    vdir = Path(__file__).resolve().parents[2] / "validation"
    for case in args or list(CASES):
        res = run_case(case, cands)
        (vdir / f"m1a2_e1_{case}.json").write_text(json.dumps(res, indent=1))
        print(json.dumps({k: v for k, v in res.items() if k in ("case", "reference_valid", "reference_agreement")}))


if __name__ == "__main__":
    main()
