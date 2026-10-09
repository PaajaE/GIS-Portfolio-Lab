"""Revised M1a: code verification on canonical cases with exact solutions, barriers, and mosaic solution
verification (validation/M1A3_PREREGISTRATION.md).

Run:  uv run python -m firepath.canonical A <scheme>      -> validation/m1a3_A_<scheme>.json
      uv run python -m firepath.canonical B               -> validation/m1a3_B.json
      uv run python -m firepath.canonical C <scheme>      -> validation/m1a3_C_<scheme>.json
Schemes: G8, G16, LS, HY.
"""

from __future__ import annotations

import json
import sys
import time
from math import hypot, inf
from pathlib import Path

import numpy as np

from .ellipse import eccentricity
from .levelset import propagate_hybrid, propagate_levelset
from .reference import propagate, uniform_field

OUT = Path(__file__).resolve().parents[2] / "validation"
L = 1200.0                     # domain side (m)
R0 = 60.0                      # initial disc radius (m)
DELTAS = (30.0, 15.0, 7.5)
MIN_DIST = 300.0               # scored cells: >= this distance (m) beyond the initial-disc edge
_ANG = np.linspace(-np.pi, np.pi, 3601)
_NX, _NY = np.cos(_ANG), np.sin(_ANG)


# ----------------------------------------------------------------------------- exact solutions

def support(nx, ny, r_head, ecc, theta):
    a = r_head / (1 + ecc)
    wx, wy = np.cos(theta), np.sin(theta)
    nw = nx * wx + ny * wy
    npp = -nx * wy + ny * wx
    return a * (ecc * nw + np.sqrt(nw * nw + (1 - ecc * ecc) * npp * npp))


def t_disc(dx, dy, r_head, ecc, theta, r0=R0):
    """Earliest t with (dx, dy) in disc(r0) (+) t E  (vectorised over dx, dy arrays)."""
    dx = np.atleast_1d(dx)[:, None]
    dy = np.atleast_1d(dy)[:, None]
    h = support(_NX, _NY, r_head, ecc, theta)[None, :]
    return np.maximum(np.max((_NX * dx + _NY * dy - r0) / h, axis=1), 0.0)


def t_two_winds(dx, dy, t1, ecc, th1, th2, r_head=1.0, r0=R0):
    dx = np.atleast_1d(dx)[:, None]
    dy = np.atleast_1d(dy)[:, None]
    h1 = support(_NX, _NY, r_head, ecc, th1)[None, :]
    h2 = support(_NX, _NY, r_head, ecc, th2)[None, :]
    proj = _NX * dx + _NY * dy - r0
    first = np.max(proj / h1, axis=1)
    second = t1 + np.max((proj - h1 * t1) / h2, axis=1)
    return np.maximum(np.where(first <= t1, first, second), 0.0)


def ray_speed(dx, dy, r_head, ecc, theta):
    psi = np.arctan2(dy, dx) - theta
    return r_head * (1 - ecc) / (1 - ecc * np.cos(psi))


def t_half_plane(xs, ys, cx, cy, xb, r_left, r_right, ecc, theta, y_lo, y_hi):
    """Exact arrival for two homogeneous half-planes (x < xb: r_left, x >= xb: r_right), same ellipse
    shape and direction, initial disc at (cx, cy) wholly in one half. Optimal paths: direct, or via the
    interface (refraction and interface-guided 'head-wave' paths). Interface sampled at 1 m, then refined
    to 0.05 m around each target's minimum."""
    src_left = cx < xb
    r_src, r_oth = (r_left, r_right) if src_left else (r_right, r_left)

    def tau_eff(s):
        tau = np.concatenate([t_disc(np.full(len(c), xb - cx), c - cy, r_src, ecc, theta)
                              for c in np.array_split(s, max(1, len(s) // 2000))])
        # along the interface: travel between interface points at the faster side's ray speed
        up = max(ray_speed(0.0, 1.0, r_left, ecc, theta), ray_speed(0.0, 1.0, r_right, ecc, theta))
        dn = max(ray_speed(0.0, -1.0, r_left, ecc, theta), ray_speed(0.0, -1.0, r_right, ecc, theta))
        ds = s[1] - s[0]
        out = tau.copy()
        for i in range(1, len(s)):
            out[i] = min(out[i], out[i - 1] + ds / up)
        for i in range(len(s) - 2, -1, -1):
            out[i] = min(out[i], out[i + 1] + ds / dn)
        return out

    s_fine = np.arange(y_lo, y_hi + 1e-9, 0.05)
    te_fine = np.concatenate([tau_eff_chunk for tau_eff_chunk in [tau_eff(s_fine)]])
    s_coarse, te_coarse = s_fine[::20], te_fine[::20]
    res = np.empty(len(xs))
    for k, (x, y) in enumerate(zip(xs, ys)):
        in_src = (x < xb) == src_left
        r_here = r_src if in_src else r_oth
        dxs, dys = x - xb, y - s_coarse
        tot = te_coarse + np.hypot(dxs, dys) / ray_speed(dxs, dys, r_here, ecc, theta)
        j = int(np.argmin(tot)) * 20
        w = slice(max(j - 100, 0), min(j + 101, len(s_fine)))
        dxs, dys = x - xb, y - s_fine[w]
        via = float(np.min(te_fine[w] + np.hypot(dxs, dys) / ray_speed(dxs, dys, r_here, ecc, theta)))
        direct = float(t_disc(x - cx, y - cy, r_src, ecc, theta)[0]) if in_src else inf
        res[k] = min(direct, via)
    return res


# ----------------------------------------------------------------------------- grids and schemes

def grid(delta):
    n = int(round(L / delta))
    rr, cc = np.mgrid[0:n, 0:n]
    x = (cc + 0.5) * delta
    y = (n - rr - 0.5) * delta          # y north, row 0 at the top
    return n, x, y


def disc_mask(x, y, cx, cy, r0=R0):
    return np.hypot(x - cx, y - cy) <= r0


def solve(scheme, f, inside, t_stop):
    t = time.perf_counter()
    if scheme == "LS":
        res = propagate_levelset(f, inside=inside, t_stop=t_stop, order=5)
    elif scheme == "HY":
        res = propagate_hybrid(f, inside=inside, t_stop=t_stop, radius=8)
    else:
        res = propagate(f, radius=int(scheme[1:]), inside=inside, t_stop=t_stop)
    return res.arrival, time.perf_counter() - t


def cases():
    """name -> builder(delta) returning (field, inside, x, y, exact_fn(xs, ys) -> T, score_mask, t_stop)."""
    out = {}

    def mk(name, r_fn, ecc, theta, sources, exact, t_stop, t_change=(), forward=None):
        def build(delta):
            n, x, y = grid(delta)
            f = uniform_field((n, n), r_head=1.0, ecc=ecc, theta=theta, t_change=t_change, cell_m=delta)
            f.r_head[:] = r_fn(x, y)[None]
            inside = np.zeros((n, n), bool)
            dist = np.full((n, n), np.inf)
            for cx, cy in sources:
                inside |= disc_mask(x, y, cx, cy)
                dist = np.minimum(dist, np.hypot(x - cx, y - cy) - R0)
            score = (dist >= MIN_DIST) & ~inside
            if forward is not None:
                score &= forward(x, y)
            return f, inside, x, y, exact, score, t_stop
        out[name] = build

    one = lambda x, y: np.ones_like(x)  # noqa: E731
    c0 = (600.0, 600.0)
    mk("A1_circle", one, 0.0, 0.0, [c0], lambda xs, ys: t_disc(xs - c0[0], ys - c0[1], 1.0, 0.0, 0.0), 700)
    cs = (240.0, 240.0)
    for lb in (2.0, 4.0, 8.0):
        e = float(eccentricity(lb))
        for ang in (0.0, 22.5, 45.0):
            th = np.radians(ang)
            fwd = (lambda th_: (lambda x, y: np.cos(np.arctan2(y - cs[1], x - cs[0]) - th_) >= 0))(th)
            mk(f"A2_ellipse_LB{lb:g}_{ang:g}", one, e, th, [cs],
               (lambda e_, th_: (lambda xs, ys: t_disc(xs - cs[0], ys - cs[1], 1.0, e_, th_)))(e, th),
               1000, forward=fwd)
    cw = (300.0, 300.0)
    for lb in (2.0, 4.0):
        e = float(eccentricity(lb))
        th1, th2 = np.radians(10.0), np.radians(100.0)
        mk(f"A3_windchange_LB{lb:g}", one, e, [th1, th2], [cw],
           (lambda e_: (lambda xs, ys: t_two_winds(xs - cw[0], ys - cw[1], 300.0, e_, th1, th2)))(e),
           1200, t_change=[300.0])
    xb = 600.0
    for lb in (1.0, 2.0):
        e = float(eccentricity(lb)) if lb > 1 else 0.0
        for src, label in (((300.0, 600.0), "fastsrc"), ((300.0, 600.0), "slowsrc")):
            rl, rr_ = (1.0, 0.25) if label == "fastsrc" else (0.25, 1.0)
            rfn = (lambda rl_, rr2: (lambda x, y: np.where(x < xb, rl_, rr2)))(rl, rr_)
            ex = (lambda rl_, rr2, e_: (lambda xs, ys: t_half_plane(xs, ys, src[0], src[1], xb, rl_, rr2, e_,
                                                                     0.0, 0.0, L)))(rl, rr_, e)
            mk(f"A4_halfplane_LB{lb:g}_{label}", rfn, e, 0.0, [src], ex, 2500 if label == "fastsrc" else 4000)
    s1, s2 = (400.0, 600.0), (800.0, 600.0)
    mk("A5_merging", one, 0.0, 0.0, [s1, s2],
       lambda xs, ys: np.minimum(t_disc(xs - s1[0], ys - s1[1], 1.0, 0.0, 0.0),
                                 t_disc(xs - s2[0], ys - s2[1], 1.0, 0.0, 0.0)), 700)
    return out


def errors(arr, x, y, exact, score, t_stop):
    m = score
    xs, ys = x[m], y[m]
    te = exact(xs, ys)
    ok = te <= 0.8 * t_stop
    te, a = te[ok], arr[m][ok]
    rel = np.abs(a - te) / te
    signed = (a - te) / te
    return {"n": int(rel.size), "median": float(np.median(rel)),
            "p95": float(np.percentile(rel, 95, method="inverted_cdf")),
            "max": float(rel.max()), "median_signed": float(np.median(signed))}


def run_A(scheme):
    res = {}
    for name, build in cases().items():
        res[name] = {}
        for d in DELTAS:
            f, inside, x, y, exact, score, t_stop = build(d)
            arr, sec = solve(scheme, f, inside, t_stop)
            e = errors(arr, x, y, exact, score, t_stop)
            e["seconds"] = sec
            res[name][str(d)] = e
            print(scheme, name, d, f"med {100 * e['median']:.2f}% p95 {100 * e['p95']:.2f}% {sec:.0f}s",
                  file=sys.stderr, flush=True)
        m = [res[name][str(d)]["median"] for d in DELTAS]
        res[name]["observed_order_median"] = [float(np.log2(m[i] / m[i + 1])) if m[i + 1] > 0 else None
                                              for i in range(2)]
        e30 = res[name]["30.0"]
        res[name]["pass_30m"] = bool(e30["median"] <= 0.05 and e30["p95"] <= 0.10)
    res["_summary"] = {"all_pass_30m": all(v["pass_30m"] for k, v in res.items() if not k.startswith("_"))}
    return res


# ----------------------------------------------------------------------------- B: barriers

def _geodesic_from_region(region, target, walls, corners):
    """Shortest obstacle-avoiding distance (cell units) from a polygon region to a target point:
    visibility graph over the gap corners, leaving the region from its nearest point to each waypoint."""
    from shapely.geometry import LineString, Point
    from shapely.ops import nearest_points

    interiors = [w.buffer(-1e-7, join_style="mitre") for w in walls]

    def visible(a, b):
        seg = LineString([a, b])
        return all(seg.intersection(w).length < 1e-9 for w in interiors)

    nodes = [tuple(target)] + list(corners)
    best = {}
    for i, nd in enumerate(nodes):
        p = nearest_points(region, Point(nd))[0]
        if visible((p.x, p.y), nd):
            best[i] = Point(nd).distance(region)
    todo = {i: best.get(i, inf) for i in range(len(nodes))}
    while todo:
        i = min(todo, key=todo.get)
        d = todo.pop(i)
        if i == 0:
            return d
        for j in list(todo):
            if visible(nodes[i], nodes[j]):
                todo[j] = min(todo[j], d + hypot(nodes[i][0] - nodes[j][0], nodes[i][1] - nodes[j][1]))
    return inf


def run_B():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
    from shapely.geometry import box
    from shapely.ops import unary_union

    import test_propagation_fixtures as T  # independent geodesic helper (visibility graph)

    cell = 30.0
    out = {}
    for scheme in ("G8", "G16", "LS", "HY"):
        r = {}
        n, col, gap = 25, 12, 18
        burn = np.ones((n, n), bool)
        burn[:, col] = False
        burn[gap, col] = True
        f = uniform_field((n, n), r_head=1.0, burnable=burn)
        inside = np.zeros((n, n), bool)
        rr, cc = np.mgrid[0:n, 0:n]
        inside[np.hypot(rr - 5, cc - 4) <= 2.0] = True
        arr, sec = solve(scheme, f, inside, 5000)
        walls = [box(col, 0, col + 1, gap), box(col, gap + 1, col + 1, n)]
        corners = [(col, gap), (col + 1, gap), (col, gap + 1), (col + 1, gap + 1)]
        region = unary_union([box(c, r_, c + 1, r_ + 1) for r_, c in zip(*np.nonzero(inside))])
        for ref_name, geo_fn in (
            ("disc", lambda tgt: (T._geodesic((4.5, 5.5), tgt, walls, corners) - 2.0) * cell),
            ("raster", lambda tgt: _geodesic_from_region(region, tgt, walls, corners) * cell),
        ):
            lo_ok, hi_ok, worst, best = True, True, 0.0, inf
            for rw in range(0, n, 2):
                for c in range(col + 1, n):
                    geo = geo_fn((c + 0.5, rw + 0.5))
                    lo_ok &= arr[rw, c] >= 0.99 * geo
                    hi_ok &= arr[rw, c] <= geo * 1.0276 + 2 * cell
                    worst = max(worst, arr[rw, c] / geo - 1)
                    best = min(best, arr[rw, c] / geo - 1)
            r[f"gap_ref_{ref_name}"] = {"no_early": bool(lo_ok), "within_upper": bool(hi_ok),
                                        "worst_rel_late": float(worst), "most_early": float(best),
                                        "seconds": sec}
        r["gap"] = r["gap_ref_raster"]   # decisive: reference from the region the schemes start from
        n = 61
        inside = np.zeros((n, n), bool)
        inside[:, :21] = True
        burn = np.ones((n, n), bool)
        burn[20:41, 18:25] = False
        arr, sec = solve(scheme, uniform_field((n, n), r_head=1.5, burnable=burn), inside, 3000)
        geo = (4 + hypot(0.5, 10.5)) * cell / 1.5
        r["lake"] = {"value_min": float(arr[30, 25]), "geodesic_min": geo,
                     "pass": bool(0.99 * geo <= arr[30, 25] <= geo * 1.0276 + 2 * cell / 1.5)}
        leaks = 0
        for wall in ("straight", "diagonal"):
            n = 41
            burn = np.ones((n, n), bool)
            if wall == "straight":
                burn[:, 20] = False
                far = np.zeros((n, n), bool)
                far[:, 21:] = True
            else:
                for i in range(n):
                    burn[i, n - 1 - i] = False
                far = np.add.outer(np.arange(n), np.arange(n)) > n - 1
            inside = np.zeros((n, n), bool)
            rr, cc = np.mgrid[0:n, 0:n]
            inside[np.hypot(rr - 20, cc - 8) <= 2.0] = True
            f = uniform_field((n, n), r_head=1.0, ecc=0.8, theta=0.3, burnable=burn)
            arr, _ = solve(scheme, f, inside & burn, 6000)
            leaks += int(np.isfinite(arr[far & burn]).sum())
        r["thin_wall_leaks"] = leaks
        r["pass"] = bool(lo_ok and hi_ok and r["lake"]["pass"] and leaks == 0)
        out[scheme] = r
        print(scheme, r, file=sys.stderr, flush=True)
    return out


# ----------------------------------------------------------------------------- C: mosaic GCI

def run_C(scheme):
    from .mosaic import CASES, CENTER, RADIUS_CELLS, T_END, T_STOP, build

    out = {}
    for case in CASES:
        vals, secs = {}, {}
        for factor in (1, 2, 4):
            f, inside = build(case, factor)
            arr, sec = solve(scheme, f, inside, T_STOP)
            secs[factor] = sec
            n0 = arr.shape[0] // factor
            if factor == 1:
                vals[factor] = arr
            else:   # mean of the factor x factor block around each coarse centre
                vals[factor] = arr.reshape(n0, factor, n0, factor).mean(axis=(1, 3))
            print(scheme, case, factor, f"{sec:.0f}s", file=sys.stderr, flush=True)
        f1, inside1 = build(case, 1)
        n = f1.shape[0]
        rr, cc = np.mgrid[0:n, 0:n]
        dist = (np.hypot(rr - CENTER[0], cc - CENTER[1]) - RADIUS_CELLS)
        lower = raster_lower_bound(inside1, f1.cell_m, float(f1.r_head.max()))
        violations = int((np.isfinite(vals[1]) & ~inside1 & (vals[1] < 0.98 * lower)).sum())
        a, b, c = vals[1], vals[2], vals[4]
        score = (~inside1) & (dist >= 5) & np.isfinite(a) & np.isfinite(b) & np.isfinite(c) & (c <= T_END)
        d1, d2 = a - b, b - c
        with np.errstate(divide="ignore", invalid="ignore"):
            p = np.log2(np.abs(d1) / np.abs(d2))
            mono = (np.sign(d1) == np.sign(d2)) & (np.abs(d2) < np.abs(d1)) & (p >= 0.5) & (p <= 3.0)
            ext = c + (c - b) / (2.0 ** p - 1.0)
            err30 = np.abs(a - ext) / ext
        app = mono & score
        share = float(app.sum() / max(score.sum(), 1))
        raw = np.abs(a - c)[score] / c[score]
        r = {"seconds": secs, "scored": int(score.sum()), "richardson_share": share,
             "lower_bound_violations": violations,
             "raw_30_vs_7p5_median": float(np.median(raw)),
             "raw_30_vs_7p5_p95": float(np.percentile(raw, 95, method="inverted_cdf"))}
        if app.any():
            r["est_err30_median"] = float(np.median(err30[app]))
            r["est_err30_p95"] = float(np.percentile(err30[app], 95, method="inverted_cdf"))
            r["observed_p_median"] = float(np.median(p[app]))
        r["richardson_applicable"] = share >= 0.8
        r["pass"] = bool(r["richardson_applicable"] and r.get("est_err30_median", 1) <= 0.05
                         and r.get("est_err30_p95", 1) <= 0.10 and violations == 0)
        out[case] = r
    return out


def raster_lower_bound(inside, cell_m, vmax):
    """Hard lower bound on arrival: Euclidean distance from each cell centre to the union of the initial
    raster cells (unit squares, the region both schemes actually start from) divided by the max speed."""
    from shapely import distance as shp_distance
    from shapely import points
    from shapely.geometry import box
    from shapely.ops import unary_union

    region = unary_union([box(c, r, c + 1, r + 1) for r, c in zip(*np.nonzero(inside))])
    n0, n1 = inside.shape
    rr, cc = np.mgrid[0:n0, 0:n1]
    d = shp_distance(region, points(cc.ravel() + 0.5, rr.ravel() + 0.5)).reshape(n0, n1)
    return d * cell_m / vmax


def main():
    what = sys.argv[1]
    OUT.mkdir(exist_ok=True)
    if what == "A":
        scheme = sys.argv[2]
        (OUT / f"m1a3_A_{scheme}.json").write_text(json.dumps(run_A(scheme), indent=1))
    elif what == "B":
        (OUT / "m1a3_B.json").write_text(json.dumps(run_B(), indent=1))
    elif what == "C":
        scheme = sys.argv[2]
        (OUT / f"m1a3_C_{scheme}.json").write_text(json.dumps(run_C(scheme), indent=1))


if __name__ == "__main__":
    main()
