"""M1a-4: HY confirmation at 30 m against the level set at 7.5 m (validation/M1A4_PREREGISTRATION.md).

Run one mosaic case per process:  uv run python -m firepath.confirm <iso|lb2|lb4>
Writes validation/m1a4_C_<case>.json. `combine` merges them into validation/m1a4_C.json.
"""

from __future__ import annotations

import json
import sys

import numpy as np

from .canonical import OUT, raster_lower_bound, solve


def _block_mean(arr, factor):
    n0 = arr.shape[0] // factor
    return arr.reshape(n0, factor, n0, factor).mean(axis=(1, 3))


def _stats(e):
    return {"n": int(e.size), "median": float(np.median(e)),
            "p95": float(np.percentile(e, 95, method="inverted_cdf")), "max": float(e.max())}


def run_case(case: str) -> dict:
    from .mosaic import CENTER, RADIUS_CELLS, T_END, T_STOP, build

    f1, inside1 = build(case, 1)
    hy, t_hy = solve("HY", f1, inside1, T_STOP)
    ls = {}
    secs = {"HY30": t_hy}
    for factor in (2, 4):
        f, inside = build(case, factor)
        arr, sec = solve("LS", f, inside, T_STOP)
        ls[factor] = _block_mean(arr, factor)
        secs[f"LS{30 / factor:g}"] = sec
        print(case, factor, f"{sec:.0f}s", file=sys.stderr, flush=True)
    n = f1.shape[0]
    rr, cc = np.mgrid[0:n, 0:n]
    dist = np.hypot(rr - CENTER[0], cc - CENTER[1]) - RADIUS_CELLS
    ref, ref15 = ls[4], ls[2]
    score = (~inside1) & (dist >= 5) & np.isfinite(hy) & np.isfinite(ref) & np.isfinite(ref15) & (ref <= T_END)
    lower = raster_lower_bound(inside1, f1.cell_m, float(f1.r_head.max()))
    violations = int((np.isfinite(hy) & ~inside1 & (hy < 0.98 * lower)).sum())
    e = np.abs(hy - ref)[score] / ref[score]
    signed = (hy - ref)[score] / ref[score]
    u = np.abs(ref15 - ref)[score] / ref[score]
    r = {"cells": int(n * n), "seconds": secs, "hy_seconds_per_cell": t_hy / (n * n),
         "all": _stats(e), "signed_median": float(np.median(signed)),
         "share_late": float((signed > 0).mean()),
         "reference_uncertainty_u": _stats(u),
         "lower_bound_violations": violations}
    good = u <= 0.02
    r["u_le_2pct"] = _stats(e[good]) if good.any() else None
    r["pass"] = bool(r["all"]["median"] <= 0.05 and r["all"]["p95"] <= 0.10 and violations == 0)
    return r


def main():
    what = sys.argv[1]
    if what == "combine":
        res = {c: json.loads((OUT / f"m1a4_C_{c}.json").read_text()) for c in ("iso", "lb2", "lb4")}
        res["pass_all"] = all(v["pass"] for v in res.values())
        (OUT / "m1a4_C.json").write_text(json.dumps(res, indent=1))
        return
    (OUT / f"m1a4_C_{what}.json").write_text(json.dumps(run_case(what), indent=1))


if __name__ == "__main__":
    main()
