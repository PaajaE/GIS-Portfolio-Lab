"""M1a-5: HY at 30 m against a bracketing reference (validation/M1A5_PREREGISTRATION.md).

  uv run python -m firepath.bracket run <case> <G8|G16|LS> <factor>   # one solve -> data/interim/m1a5/
  uv run python -m firepath.bracket combine                           # -> validation/m1a5.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from .canonical import OUT, raster_lower_bound, solve
from .confirm import _block_mean, _stats

CACHE = Path(__file__).resolve().parents[2] / "data" / "interim" / "m1a5"
CASES = ("iso", "lb2", "lb4")


def _path(case, scheme, factor):
    return CACHE / f"{case}_{scheme}_f{factor}.npy"


def run(case, scheme, factor):
    from .mosaic import T_STOP, build

    f, inside = build(case, factor)
    arr, sec = solve(scheme, f, inside, T_STOP)
    CACHE.mkdir(parents=True, exist_ok=True)
    np.save(_path(case, scheme, factor), _block_mean(arr, factor) if factor > 1 else arr)
    (CACHE / f"{case}_{scheme}_f{factor}.json").write_text(json.dumps({"seconds": sec, "cells": int(arr.size)}))


def evaluate(case, hy, ls2, ls4, ls8, g8, g16, inside1, lower):
    from .mosaic import CENTER, RADIUS_CELLS, T_END

    n = hy.shape[0]
    rr, cc = np.mgrid[0:n, 0:n]
    dist = np.hypot(rr - CENTER[0], cc - CENTER[1]) - RADIUS_CELLS
    U = np.minimum(g8, g16)
    d1, d2 = ls2 - ls4, ls4 - ls8
    with np.errstate(divide="ignore", invalid="ignore"):
        p = np.log2(np.abs(d1) / np.abs(d2))
        rich = (np.sign(d1) == np.sign(d2)) & (np.abs(d2) < np.abs(d1)) & (p >= 0.5) & (p <= 3.0)
        ext = ls8 + (ls8 - ls4) / (2.0 ** p - 1.0)
    est = rich & (ext <= U)
    R = np.where(est, ext, np.where(rich, U, np.minimum(ls8, U)))
    score = ((~inside1) & (dist >= 5) & np.isfinite(hy) & np.isfinite(R) & np.isfinite(U)
             & np.isfinite(ls2) & np.isfinite(ls4) & (R <= T_END))
    e = np.abs(hy - R)[score] / R[score]
    signed = (hy - R)[score] / R[score]
    spread = (U - R)[score] / R[score]
    late = (hy > U)[score]
    late_amt = ((hy - U) / U)[score][late]
    violations = int((np.isfinite(hy) & ~inside1 & (hy < 0.98 * lower)).sum())
    cat = {"estimate": float(est[score].mean()), "bound": float((rich & ~est)[score].mean()),
           "fallback": float((~rich)[score].mean())}
    r = {"n": int(score.sum()), "error": _stats(e), "signed_median": float(np.median(signed)),
         "reference_categories": cat, "reference_spread": _stats(spread),
         "provably_late_share": float(late.mean()),
         "provably_late": _stats(late_amt) if late.any() else None,
         "lower_bound_violations": violations}
    if r["reference_spread"]["median"] > 0.025 or cat["estimate"] < 0.5:
        r["outcome"] = "INCONCLUSIVE"
    else:
        ok = (r["error"]["median"] <= 0.05 and r["error"]["p95"] <= 0.10 and violations == 0
              and (r["provably_late"] is None or r["provably_late"]["p95"] <= 0.10))
        r["outcome"] = "PASS" if ok else "FAIL"
    return r


def combine():
    from .mosaic import T_STOP, build

    res = {}
    for case in CASES:
        f1, inside1 = build(case, 1)
        hy, t_hy = solve("HY", f1, inside1, T_STOP)
        load = lambda s, k: np.load(_path(case, s, k))  # noqa: E731
        lower = raster_lower_bound(inside1, f1.cell_m, float(f1.r_head.max()))
        r = evaluate(case, hy, load("LS", 2), load("LS", 4), load("LS", 8), load("G8", 8), load("G16", 8),
                     inside1, lower)
        r["seconds"] = {"HY30": t_hy, **{p.stem.split("_", 1)[1]: json.loads(p.read_text())["seconds"]
                                         for p in sorted(CACHE.glob(f"{case}_*.json"))}}
        res[case] = r
    order = ["PASS", "INCONCLUSIVE", "FAIL"]
    res["outcome"] = max((res[c]["outcome"] for c in CASES), key=order.index)
    (OUT / "m1a5.json").write_text(json.dumps(res, indent=1))
    return res


def main():
    if sys.argv[1] == "run":
        run(sys.argv[2], sys.argv[3], int(sys.argv[4]))
    else:
        print(json.dumps(combine(), indent=1))


if __name__ == "__main__":
    main()
