"""M1a propagation-scheme bake-off (decision D1; criteria fixed in CRITICAL_REVIEW.md P0-1).

Candidates on identical SpreadFields:
  A  label-setting (time-dependent Dijkstra), stencil radius 8   (`reference.propagate`)
  B  Eulerian level set, local Lax-Friedrichs: ENO2 + Heun ("levelset") and WENO5 + TVD-RK3 ("levelset5";
     added after the ENO2 results were seen -- reported as such in M1A_RESULTS.md)
(and label-setting radius 2, the rejected v1 default, for context).

Criteria: (1) worst forward arrival error <= 5 % for LB <= 4 and <= 10 % at LB 8, wind angles 0-45 deg in
2.5 deg steps; (2) burned-area spread across wind angles <= 3 %; (3) wind-change (Minkowski) fixture
error <= 5 %; (4) barrier / initial-perimeter fixtures pass; (5) measured cost.
Run:  uv run python -m firepath.bakeoff <scheme ...>  -> validation/m1a_bakeoff_<schemes>.json
      uv run python -m firepath.bakeoff combine       -> validation/m1a_bakeoff_summary.json
"""

from __future__ import annotations

import json
import platform
import sys
import time
from math import hypot, inf
from pathlib import Path

import numpy as np

from .ellipse import eccentricity
from .levelset import propagate_levelset
from .reference import propagate, uniform_field

CELL = 30.0
N, SRC = 121, (90, 30)
R0_CELLS = 2.0
ANGLES = [2.5 * i for i in range(19)]
LBS = [2.0, 3.0, 4.0, 8.0]
_ang = np.linspace(-np.pi, np.pi, 3601)
_NX, _NY = np.cos(_ang), np.sin(_ang)


def support(nx, ny, r_head, ecc, theta):
    a = r_head / (1 + ecc)
    wx, wy = np.cos(theta), np.sin(theta)
    nw = nx * wx + ny * wy
    npp = -nx * wy + ny * wx
    return a * (ecc * nw + np.sqrt(nw * nw + (1 - ecc * ecc) * npp * npp))


def t_ref_point(dx, dy, ecc, theta, r_head=1.0):
    psi = np.arctan2(dy, dx) - theta
    return hypot(dx, dy) / (r_head * (1 - ecc) / (1 - ecc * np.cos(psi)))


def t_ref_disc(dx, dy, r0, ecc, theta, r_head=1.0):
    """Earliest time the point is in disc(r0) (+) t*E: max_n (n.d - r0) / h_E(n)."""
    return float(np.max((_NX * dx + _NY * dy - r0) / support(_NX, _NY, r_head, ecc, theta)))


def t_ref_two_winds(dx, dy, r0, t1, ecc, th1, th2, r_head=1.0):
    h1 = support(_NX, _NY, r_head, ecc, th1)
    h2 = support(_NX, _NY, r_head, ecc, th2)
    proj = _NX * dx + _NY * dy - r0
    if np.all(proj <= h1 * t1):
        return float(np.max(proj / h1))
    return float(t1 + np.max((proj - h1 * t1) / h2))


def run(scheme, f, t_stop, **kw):
    t = time.perf_counter()
    if scheme.startswith("levelset"):
        order = 5 if scheme == "levelset5" else 2
        res = propagate_levelset(f, points=[(*SRC, 0.0)], t_stop=t_stop, r0_cells=R0_CELLS, order=order, **kw)
    else:
        res = propagate(f, radius=int(scheme.split("_r")[1]), points=[(*SRC, 0.0)], t_stop=t_stop, **kw)
    return res, time.perf_counter() - t


def forward_errors(res, ecc, theta, scheme, min_cells=25):
    errs = []
    for r in range(0, N, 2):
        for c in range(0, N, 2):
            dx, dy = (c - SRC[1]) * CELL, -(r - SRC[0]) * CELL
            if hypot(dx, dy) < min_cells * CELL or not np.isfinite(res.arrival[r, c]):
                continue
            if abs(np.angle(np.exp(1j * (np.arctan2(dy, dx) - theta)))) > np.pi / 2:
                continue
            tr = (t_ref_disc(dx, dy, R0_CELLS * CELL, ecc, theta) if scheme.startswith("levelset")
                  else t_ref_point(dx, dy, ecc, theta))
            errs.append(res.arrival[r, c] / tr - 1)
    return np.array(errs)


def exact_area(t, ecc, scheme, r_head=1.0):
    a = r_head * t / (1 + ecc)
    b = a * np.sqrt(1 - ecc * ecc)
    area = np.pi * a * b
    if scheme.startswith("levelset"):  # Steiner: disc (+) ellipse
        r0 = R0_CELLS * CELL
        h = ((a - b) / (a + b)) ** 2
        perim = np.pi * (a + b) * (1 + 3 * h / (10 + np.sqrt(4 - 3 * h)))
        area += perim * r0 + np.pi * r0 * r0
    return area


def sweep(schemes, t_eval=1500.0):
    out = {}
    for scheme in schemes:
        rows = []
        for lb in LBS:
            ecc = float(eccentricity(lb))
            for ang in ANGLES:
                th = np.radians(ang)
                f = uniform_field((N, N), r_head=1.0, ecc=ecc, theta=th, cell_m=CELL)
                res, sec = run(scheme, f, t_stop=2.0 * t_eval)
                e = forward_errors(res, ecc, th, scheme)
                if e.size == 0:  # front never reached the 25-cell evaluation ring: unbounded error
                    e = np.array([np.inf])
                area = float(np.sum(res.arrival <= t_eval)) * CELL * CELL
                rows.append({"lb": lb, "angle": ang, "n": int(np.isfinite(e).sum()), "fwd_max": float(e.max()),
                             "fwd_min": float(e.min()), "fwd_mean": float(e.mean()),
                             "area_rel_err": area / exact_area(t_eval, ecc, scheme) - 1, "seconds": sec,
                             "burned_cells": int(np.isfinite(res.arrival).sum())})
                print(scheme, lb, ang, f"{100 * e.max():.1f}%", f"{sec:.1f}s", file=sys.stderr, flush=True)
        out[scheme] = rows
    return out


def wind_change(schemes):
    """Wind turns 90 deg at t1; continuum reference = Minkowski sum (support functions)."""
    out = {}
    t1 = 600.0
    for scheme in schemes:
        rows = []
        for lb in (2.0, 4.0):
            ecc = float(eccentricity(lb))
            th1, th2 = np.radians(10.0), np.radians(100.0)
            f = uniform_field((N, N), r_head=1.0, ecc=ecc, theta=[th1, th2], t_change=[t1], cell_m=CELL)
            res, sec = run(scheme, f, t_stop=3000.0)
            r0 = R0_CELLS * CELL if scheme.startswith("levelset") else 0.0
            errs = []
            for r in range(0, N, 3):
                for c in range(0, N, 3):
                    dx, dy = (c - SRC[1]) * CELL, -(r - SRC[0]) * CELL
                    if hypot(dx, dy) < 25 * CELL or not np.isfinite(res.arrival[r, c]):
                        continue
                    tr = t_ref_two_winds(dx, dy, r0, t1, ecc, th1, th2)
                    if tr > 2500.0:
                        continue
                    errs.append(res.arrival[r, c] / tr - 1)
            errs = np.array(errs) if errs else np.array([np.inf])
            rows.append({"lb": lb, "n": int(np.isfinite(errs).sum()), "max_abs": float(np.abs(errs).max()),
                         "min": float(errs.min()), "max": float(errs.max()), "seconds": sec})
        out[scheme] = rows
    return out


def summarize(sw, wc):
    s = {}
    for scheme, rows in sw.items():
        crit1_le4 = max(abs(r["fwd_max"]) for r in rows if r["lb"] <= 4) if rows else None
        crit1_cap = max(abs(r["fwd_max"]) for r in rows if r["lb"] == 8.0)
        spread = {}
        for lb in LBS:
            areas = [r["area_rel_err"] for r in rows if r["lb"] == lb]
            spread[str(lb)] = float((max(areas) - min(areas)) / (1 + np.mean(areas)))
        s[scheme] = {
            "c1_worst_fwd_err_lb_le4": crit1_le4, "c1_worst_fwd_err_lb8": crit1_cap,
            "c1_pass": crit1_le4 <= 0.05 and crit1_cap <= 0.10,
            "c2_area_spread_by_lb": spread, "c2_pass": max(spread.values()) <= 0.03,
            "c3_wind_change_max_abs": max(r["max_abs"] for r in wc[scheme]),
            "c3_pass": max(r["max_abs"] for r in wc[scheme]) <= 0.05,
            "median_seconds_per_run": float(np.median([r["seconds"] for r in rows])),
        }
    return s


def main():
    args = sys.argv[1:]
    out_dir = Path(__file__).resolve().parents[2] / "validation"
    if args == ["combine"]:
        parts = sorted(p for p in out_dir.glob("m1a_bakeoff_*.json") if p.name != "m1a_bakeoff_summary.json")
        sw, wc = {}, {}
        for p in parts:
            d = json.loads(p.read_text())
            sw.update(d["sweep"])
            wc.update(d["wind_change"])
        report = {"grid": [N, N], "cell_m": CELL, "source": SRC, "r0_cells_levelset": R0_CELLS,
                  "angles_deg": ANGLES, "lb": LBS, "min_distance_cells": 25, "t_eval_min": 1500.0,
                  "parts": [p.name for p in parts], "summary": summarize(sw, wc)}
        (out_dir / "m1a_bakeoff_summary.json").write_text(json.dumps(report, indent=1))
        print(json.dumps(report["summary"], indent=1))
        return
    schemes = args or ["levelset", "dijkstra_r8", "dijkstra_r2"]
    sw = sweep(schemes)
    wc = wind_change(schemes)
    report = {"grid": [N, N], "cell_m": CELL, "source": SRC, "r0_cells_levelset": R0_CELLS,
              "angles_deg": ANGLES, "lb": LBS, "min_distance_cells": 25, "t_eval_min": 1500.0,
              "machine": platform.platform(), "python": platform.python_version(),
              "note": "pure-Python/NumPy reference implementations; times are not Rust estimates",
              "summary": summarize(sw, wc), "sweep": sw, "wind_change": wc}
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"m1a_bakeoff_{'_'.join(schemes)}.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report["summary"], indent=1))


if __name__ == "__main__":
    main()
