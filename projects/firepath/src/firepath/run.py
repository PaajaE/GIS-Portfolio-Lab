"""M1b run: Mode A from the first usable perimeter on the prepared inputs, model and baselines,
interval-censored metrics (METHOD "Observations and validation metrics", PLAN §6–9).

  uv run python -m firepath.run <fire> [--cell 90] [--scheme HY] [--models model,B0,B1] [--mode A|step]

Mode A: one run from the first usable perimeter. Mode step (one-step-ahead): for each scan pair k -> k+1,
start from perimeter k at t_k and stop at t_{k+1}; scored on the growth between the two perimeters.

Parameters are HAND-SET placeholders (M1b), not calibrated: model k = a_u = a_s = 1; B0 c = 1 m/min;
B1 c = 0.5 m/min, b = 0.05 (U10 in m/s). Results are a pipeline check, not a skill estimate.
Writes data/out/<fire>/run_<tag>.npz and validation/m1b_<tag>.json, tag = <fire>_<cell>m_<scheme>_<models>
(Mode A) or <fire>_<cell>m_<scheme>_step_<models>.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

import numpy as np

from .ellipse import lb_anderson_ms
from .field import Params, Static, hour
from .harvest import INTERIM, PROJECT, fire_perimeters
from .moisture import from_gridmet
from .observed import CONSISTENT, NEVER, audit_sequence, interval_error
from .prepare import grid_profile, horn_slope_aspect
from .reference import SpreadField, propagate
from .levelset import propagate_hybrid, propagate_levelset

CAP_MIN = 48 * 60.0
STOP_AFTER_MIN = 48 * 60.0
WINDOW_DAYS = 7.0
B0_C, B1_C, B1_B = 1.0, 0.5, 0.05


def coarsen(fire: str, factor: int):
    """Fuels by mode, canopy and DEM by mean (PLAN §5); terrain recomputed at the coarse cell."""
    z = np.load(INTERIM / fire / "inputs.npz")
    fuel, cc, ch, dem = z["fuel"], z["cc"].astype(float), z["ch"].astype(float), z["dem"].astype(float)
    nr, nc = (fuel.shape[0] // factor) * factor, (fuel.shape[1] // factor) * factor
    blk = lambda a: a[:nr, :nc].reshape(nr // factor, factor, nc // factor, factor)  # noqa: E731
    if factor == 1:
        f_mode = fuel
    else:
        b = blk(fuel).transpose(0, 2, 1, 3).reshape(nr // factor, nc // factor, -1)
        s = np.sort(b, axis=2)
        # mode per block: longest run in the sorted block values (ties -> smallest code)
        runs = np.concatenate([np.ones(s.shape[:2] + (1,), bool), s[:, :, 1:] != s[:, :, :-1]], axis=2)
        idx = np.cumsum(runs, axis=2)
        counts = np.stack([(idx == k).sum(2) for k in range(1, idx.max() + 1)], axis=2)
        best = counts.argmax(2) + 1
        f_mode = np.take_along_axis(s, (idx == best[:, :, None]).argmax(2)[:, :, None], axis=2)[:, :, 0]
    mean = lambda a: blk(a).mean(axis=(1, 3)) if factor > 1 else a  # noqa: E731
    dem_c = mean(dem)
    cell = 30.0 * factor
    tan_s, up = horn_slope_aspect(dem_c, cell)
    return f_mode.astype(np.int16), mean(cc), mean(ch), dem_c, tan_s, up, cell


def coarse_profile(fire: str, factor: int):
    from rasterio.transform import from_origin

    prof = grid_profile(fire)
    g = prof["grid"]
    prof = dict(prof)
    prof["transform"] = from_origin(g["x0"], g["y1"], g["cell"] * factor, g["cell"] * factor)
    prof["width"], prof["height"] = g["width"] // factor, g["height"] // factor
    return prof


def observed(fire: str, prof: dict):
    from pyproj import Transformer
    from rasterio.features import rasterize
    import shapely
    from shapely.geometry import shape

    feats = fire_perimeters(fire)
    tr = Transformer.from_crs(4326, prof["crs"].to_epsg(), always_xy=True)
    to_utm = lambda c: np.column_stack(tr.transform(c[:, 0], c[:, 1]))  # noqa: E731
    t_u, m_u = [], []
    for f in feats:
        t = datetime.fromisoformat(f["properties"]["UTC"]).replace(tzinfo=timezone.utc).timestamp()
        m = rasterize([(shapely.transform(shape(f["geometry"]), to_utm), 1)], out_shape=(prof["height"], prof["width"]),
                      transform=prof["transform"], dtype="uint8").astype(bool)
        if t_u and t == t_u[-1]:
            m_u[-1] |= m
        else:
            t_u.append(t)
            m_u.append(m)
    return np.array(t_u), m_u


def wind_at_cells(fire: str, prof: dict):
    w = np.load(INTERIM / fire / "wind.npz")
    tr = prof["transform"]
    xs = tr.c + (np.arange(prof["width"]) + 0.5) * tr.a
    ys = tr.f + (np.arange(prof["height"]) + 0.5) * tr.e
    ci = np.clip(np.round((xs - w["x"][0]) / float(w["cell"])).astype(int), 0, len(w["x"]) - 1)
    ri = np.clip(np.round((w["y"][0] - ys) / float(w["cell"])).astype(int), 0, len(w["y"]) - 1)
    return w["u"][:, ri][:, :, ci], w["v"][:, ri][:, :, ci], w["valid_unix"]


def fields(kind, st, u, v, hrs_idx, cell):
    """Per-hour (r_head, ecc, theta) for the model or a baseline."""
    H = len(hrs_idx)
    shp = st.burnable.shape
    r, e, th = (np.zeros((H, *shp), "f8") for _ in range(3))
    for j, h in enumerate(hrs_idx):
        if kind == "model":
            r[j], e[j], th[j] = hour(st, u[h], v[h], Params())
        elif kind == "B0":
            r[j] = np.where(st.burnable, B0_C, 0.0)
        elif kind == "B1":
            s10 = np.hypot(u[h], v[h])
            r[j] = np.where(st.burnable, B1_C * (1 + B1_B * s10 ** 1.5), 0.0)
            # ellipse from U10 via the FARSITE LB relation at a fixed WAF 0.4 (hand-set placeholder)
            e[j] = np.where(st.burnable, np.sqrt(1 - 1 / lb_anderson_ms(s10 / 1.15 * 0.4) ** 2), 0.0)
            th[j] = np.arctan2(v[h], u[h])
    return r, e, th


def metrics(arr_min, lo, hi, flag, t_scans_rel, masks):
    """O2/O3 on the evaluation window: cells observed to burn in it (CONSISTENT) or burned by the model
    by the last scan although never observed (NEVER); INITIAL and INCONSISTENT excluded. No masked days
    yet (ICS-209 lists pending)."""
    err = np.clip(interval_error(arr_min, lo, hi), -CAP_MIN, CAP_MIN)
    burned_mod = np.isfinite(arr_min) & (arr_min <= t_scans_rel[-1])
    scored = (flag == CONSISTENT) | ((flag == NEVER) & burned_mod)
    e = err[scored]
    steps = []
    for k in range(1, len(t_scans_rel)):
        mod = np.isfinite(arr_min) & (arr_min <= t_scans_rel[k])
        obs = masks[k]
        inter = (mod & obs).sum()
        steps.append({"k": k, "area_ratio": float(mod.sum() / max(obs.sum(), 1)),
                      "dice": float(2 * inter / max(mod.sum() + obs.sum(), 1)),
                      "iou": float(inter / max((mod | obs).sum(), 1))})
    return {"n_scored": int(e.size), "mean_abs_h": float(np.mean(np.abs(e)) / 60),
            "mean_signed_h": float(np.mean(e) / 60),
            "share_early": float((e < 0).mean()), "share_inside": float((e == 0).mean()),
            "share_late": float((e > 0).mean()),
            "median_early_h": float(np.median(e[e < 0]) / 60) if (e < 0).any() else None,
            "median_late_h": float(np.median(e[e > 0]) / 60) if (e > 0).any() else None,
            "steps": steps}


def step_metrics(arr_min, t_k, t_next, mask_k, mask_next, burnable):
    """One-step-ahead scores on the growth k -> k+1 (burnable cells outside perimeter k): observed growth
    = in perimeter k+1; modelled growth = reached by t_{k+1}. Recall/precision/Dice of the growth and the
    interval error of observed-growth cells against (t_k, t_{k+1}] (unreached capped at 48 h late)."""
    out = burnable & ~mask_k
    obs = mask_next & out
    mod = np.isfinite(arr_min) & (arr_min <= t_next) & out
    inter = int((obs & mod).sum())
    err = np.clip(interval_error(arr_min[obs], t_k, t_next), -CAP_MIN, CAP_MIN)
    return {"obs_growth": int(obs.sum()), "model_growth": int(mod.sum()),
            "growth_ratio": float(mod.sum() / max(obs.sum(), 1)),
            "recall": float(inter / max(obs.sum(), 1)), "precision": float(inter / max(mod.sum(), 1)),
            "dice": float(2 * inter / max(obs.sum() + mod.sum(), 1)),
            "share_late": float((err > 0).mean()) if err.size else None,
            "median_late_h": float(np.median(err[err > 0]) / 60) if (err > 0).any() else None}


def run_scheme(scheme, f, inside, t0, t_stop):
    if scheme == "HY":
        return propagate_hybrid(f, inside=inside, t0=t0, t_stop=t_stop)
    if scheme == "LS":
        return propagate_levelset(f, inside=inside, t0=t0, t_stop=t_stop, order=5)
    return propagate(f, radius=8, inside=inside, t0=t0, t_stop=t_stop)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("fire")
    ap.add_argument("--cell", type=int, default=90)
    ap.add_argument("--scheme", default="HY", choices=["HY", "LS", "G8"])
    ap.add_argument("--models", default="model,B0,B1")
    ap.add_argument("--mode", default="A", choices=["A", "step"])
    a = ap.parse_args(argv)
    factor = a.cell // 30
    prof = coarse_profile(a.fire, factor)
    fuel, cc, ch, dem, tan_s, up, cell = coarsen(a.fire, factor)
    fuel = fuel[:prof["height"], :prof["width"]]
    times, masks = observed(a.fire, prof)
    t_end_window = times[0] + WINDOW_DAYS * 86400
    k_last = int(np.searchsorted(times, t_end_window + 3600, side="right") - 1)     # last scan within 7 d (+1 h)
    final_cells = masks[-1].sum()
    k90 = next(k for k, m in enumerate(masks) if m.sum() >= 0.9 * final_cells)
    k_last = min(k_last, k90)
    times_w, masks_w = times[:k_last + 1], masks[:k_last + 1]
    audit = audit_sequence(times_w, masks_w, jitter_cells=1)
    t0 = times_w[0]
    rel = (times_w - t0) / 60.0
    lo = np.where(np.isfinite(audit["lo"]), (audit["lo"] - t0) / 60.0, audit["lo"])
    hi = np.where(np.isfinite(audit["hi"]), (audit["hi"] - t0) / 60.0, audit["hi"])

    pz = json.loads((PROJECT / "provenance" / f"prepare_{a.fire}.json").read_text())
    m = from_gridmet(pz["moisture"]["fm100_median_pct"], "L1")
    st = Static.build(fuel, cc, ch, tan_s, up, m)
    u, v, valid = wind_at_cells(a.fire, prof)
    t_stop = rel[-1] + STOP_AFTER_MIN
    h0 = int(np.searchsorted(valid, t0, side="right") - 1)
    h1 = int(np.searchsorted(valid, t0 + t_stop * 60, side="right"))
    hrs = list(range(h0, min(h1, len(valid))))
    t_change = (valid[hrs[1:]] - t0) / 60.0
    inside = masks_w[0] & st.burnable

    report = {"fire": a.fire, "cell_m": cell, "scheme": a.scheme, "grid_shape": list(fuel.shape),
              "window": {"t0_utc": datetime.fromtimestamp(t0, timezone.utc).isoformat(),
                         "t_end_utc": datetime.fromtimestamp(times_w[-1], timezone.utc).isoformat(),
                         "scans": len(times_w), "hours": len(hrs)},
              "moisture": {"fm100": pz["moisture"]["fm100_median_pct"], "scenario": m.__dict__},
              "audit": {"steps": audit["steps"]},
              "parameters": {"model": Params().__dict__, "B0": {"c": B0_C}, "B1": {"c": B1_C, "b": B1_B}},
              "note": "hand-set parameters; pipeline check, not a skill estimate", "results": {}}
    out_arr = {}
    for kind in a.models.split(","):
        r, e, th = fields(kind, st, u, v, hrs, cell)
        terrain = {"tan_slope": tan_s, "upslope": up} if kind == "model" else {}
        f = SpreadField(t_change, r, e, th, st.burnable, cell, **terrain)
        t = time.perf_counter()
        if a.mode == "step":
            steps, arrs = [], []
            for k in range(len(rel) - 1):
                ins = masks_w[k] & st.burnable
                res = run_scheme(a.scheme, f, ins, rel[k], rel[k + 1])
                sm = step_metrics(res.arrival, rel[k], rel[k + 1], masks_w[k], masks_w[k + 1], st.burnable)
                steps.append({"k": k, **sm})
                arrs.append(np.where(res.arrival <= rel[k + 1], res.arrival, np.inf).astype("f4"))
                print(kind, k, {x: sm[x] for x in ("obs_growth", "growth_ratio", "recall", "precision")},
                      flush=True)
            sec = time.perf_counter() - t
            report["results"][kind] = {"steps": steps, "seconds": sec}
            out_arr[kind] = np.stack(arrs)
            continue
        res = run_scheme(a.scheme, f, inside, 0.0, t_stop)
        sec = time.perf_counter() - t
        mt = metrics(res.arrival, lo, hi, audit["flag"], rel, masks_w)
        mt["seconds"] = sec
        report["results"][kind] = mt
        out_arr[kind] = res.arrival.astype("f4")
        print(kind, f"{sec:.0f}s", {k: mt[k] for k in ("mean_abs_h", "share_early", "share_inside", "share_late")},
              flush=True)
    mode = "_step" if a.mode == "step" else ""
    tag = f"{a.fire}_{a.cell}m_{a.scheme}{mode}_{a.models.replace(',', '-')}"
    od = PROJECT / "data" / "out" / a.fire
    od.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(od / f"run_{tag}.npz", **out_arr, lo=lo, hi=hi, flag=audit["flag"],
                        fuel=fuel, burnable=st.burnable, rel_scans_min=rel)
    (PROJECT / "validation" / f"m1b_{tag}.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
