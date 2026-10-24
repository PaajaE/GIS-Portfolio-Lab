"""M6 item 4: does rainfall *intensity* (max 1 h, max running 6 h MRMS) carry meaningfully more information than the
72 h total? One pre-registered check (METHOD §Validation, fixed 2026-10-10), no tuning, product unchanged.

* T1 (units, A = 0.1, model domain): pooled AUC of the trigger alone for "unit has a mapped natural initiation";
  Δ(intensity − 72 h) with a HUC-12 block-bootstrap interval. Pass = lower bound > 0.
* T2 (5 m cells): the M4/M5 logistic regression with the intensity covariate in place of the 72 h total, same
  folds, same 1:10 thinning; within-watershed AUC of the score at the reference value. Pass = lower bound of
  Δ(intensity model − 72 h model) > 0.
"Meaningful benefit" = T1 and T2. Writes validation/m6_trigger.json.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import rasterio

from . import config as C
from .aggregate import unit_raster_5m
from .baseline import (NEG_RATIO, PIXEL_NAMES, PIXEL_PROTECTED, UNIT_A, cross_val, evaluate, huc_polygons,
                       load_units, paired_delta, pixel_matrix)
from .labels import REGION, read
from .metrics import Ranked, block_bootstrap, ci

LAYERS = ("rain_mm", "rain1h_max", "rain6h_max")
N_BOOT = 2000


def unit_means(u: pd.DataFrame) -> pd.DataFrame:
    dom = read(C.INTERIM / f"labels_{REGION}" / "domain.tif").astype(bool)
    u5, _ = unit_raster_5m(UNIT_A, dom.shape)
    idx = np.flatnonzero(dom.ravel())
    ud = u5.ravel()[idx]
    n = int(u5.max()) + 1
    cnt = np.maximum(np.bincount(ud, minlength=n), 1)
    out = {}
    for k in LAYERS:
        v = read(C.INTERIM / f"stack_{REGION}" / f"{k}.tif").ravel()[idx].astype(np.float64)
        out[k] = (np.bincount(ud, weights=v, minlength=n) / cnt)[u["unit"].to_numpy()]
    return pd.DataFrame(out, index=u.index)


def sample(df: pd.DataFrame, layer: str) -> np.ndarray:
    with rasterio.open(C.INTERIM / f"stack_{REGION}" / f"{layer}.tif") as s:
        a = s.read(1)
    return a[df["row"].to_numpy(), df["col"].to_numpy()].astype(np.float64)


def t1() -> dict:
    u = load_units()
    m = unit_means(u)
    y, huc = u["label"].to_numpy(), u["huc12"].to_numpy()
    rk = {k: Ranked(m[k].to_numpy(), y) for k in LAYERS}

    def stat(w):
        return np.array([rk[k].auc(w) for k in LAYERS])

    reps = block_bootstrap(huc, stat, N_BOOT, C.SEED)
    point = stat(np.ones(len(y)))
    out = {k: {"auc": float(p), "ci95": [float(a), float(b)]} for k, p, (a, b) in zip(LAYERS, point, ci(reps))}
    for i, k in enumerate(LAYERS[1:], 1):
        d = reps[:, i] - reps[:, 0]
        out[f"delta_{k}_minus_72h"] = {"value": float(point[i] - point[0]),
                                       "ci95": [float(x) for x in np.nanquantile(d, [0.025, 0.975])]}
    out["spearman_unit_means"] = m.corr("spearman").round(3).to_dict()
    return out


def t2() -> dict:
    lab = C.INTERIM / f"labels_{REGION}"
    pos = pd.read_parquet(lab / "positives.parquet")
    neg = pd.read_parquet(lab / "negatives.parquet")
    pos, neg = (t[(t["hillslope"] == 1) & t["huc12"].notna()] for t in (pos, neg))
    df = pd.concat([pos, neg], ignore_index=True)
    dom = pd.read_parquet(lab / "domain_sample.parquet", columns=["row", "col"])
    rep = json.loads((lab / "report.json").read_text())
    w = np.where(df["label"].to_numpy() == 1, 1.0, rep["domain"]["eligible_negative_hillslope_cells"] / len(neg))
    y, huc, xy = df["label"].to_numpy(), df["huc12"].to_numpy(), df[["x", "y"]].to_numpy()
    polys = huc_polygons().geometry

    def thin(idx, rng):
        p_, n_ = idx[y[idx] == 1], idx[y[idx] == 0]
        return np.r_[p_, rng.choice(n_, size=min(len(n_), NEG_RATIO * len(p_)), replace=False)]

    ev, out = {}, {}
    X0 = pixel_matrix(df)
    rain_col = PIXEL_NAMES.index("rain_mm")
    for k in LAYERS:
        X = X0.copy()
        X[:, rain_col] = sample(df, k)
        ref = {"rain_mm": float(np.median(sample(dom, k)))}
        cv = cross_val(X, y, huc, xy, polys, PIXEL_NAMES, PIXEL_PROTECTED, ref, subsample=thin)
        ev[k] = evaluate(cv["ref"], y, X[:, rain_col], huc, y.astype(float), np.zeros(len(y)), w=w)
        out[k] = {"auc_within_huc": {"value": ev[k]["auc_within_huc"]["value"], "ci95": ev[k]["auc_within_huc"]["ci95"]},
                  "reference_value": ref["rain_mm"],
                  "covariate_coefficient_final_fold_mean": float(np.mean([c["rain_mm"] for c in cv["coefs"]]))}
    for k in LAYERS[1:]:
        out[f"delta_{k}_minus_72h"] = paired_delta(ev[k], ev["rain_mm"], "auc_within_huc")
    return out


def run() -> dict:
    res = {"T1_units_trigger_alone_pooled_auc": t1(), "T2_cells_within_watershed_auc": t2()}
    T1, T2 = res["T1_units_trigger_alone_pooled_auc"], res["T2_cells_within_watershed_auc"]
    res["verdict"] = {}
    for k in LAYERS[1:]:
        p1 = T1[f"delta_{k}_minus_72h"]["ci95"][0] > 0
        p2 = T2[f"delta_{k}_minus_72h"]["ci95"][0] > 0
        res["verdict"][k] = {"T1": p1, "T2": p2, "meaningful_benefit": bool(p1 and p2)}
    (C.VALIDATION / "m6_trigger.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res["verdict"], indent=1), flush=True)
    return res


if __name__ == "__main__":
    run()
