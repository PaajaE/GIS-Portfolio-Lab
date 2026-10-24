"""Pre-registered test: the 5 m LR without geology predictors (METHOD §Validation, "Test: 5 m LR without geology
predictors", commit 0ae693d). Decision rule: R1 (AOI non-inferiority, lower bounds >= -0.01) and R2 (leave-one-
county-out and Watauga transfer, lower bounds > 0). Everything else is reported without a gate.
Writes validation/nogeo_test.json and validation/NOGEO_TEST.md.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from . import config as C
from .baseline import (LR, NEG_RATIO, PIXEL_NAMES, PIXEL_PROTECTED, cross_val, evaluate, huc_polygons,
                       paired_delta, pixel_matrix)
from .labels import REGION, counties
from .metrics import Ranked
from .product import rain_reference, thin_all, training_cells
from .report_nogeo import write as write_report
from .sensitivity import load
from .uncertainty import N_REFITS, class_edges, to_class
from .watauga import auc_ci, build, frame

GEO = [n for n in PIXEL_NAMES if n.startswith("geology_")]
MODELS = {"current": PIXEL_NAMES, "no_geology": [n for n in PIXEL_NAMES if n not in GEO]}
COLS = {m: [PIXEL_NAMES.index(n) for n in names] for m, names in MODELS.items()}
KEYS = ("auc_rain_stratified", "auc_within_huc")


def X_of(df: pd.DataFrame, model: str) -> np.ndarray:
    return pixel_matrix(df)[:, COLS[model]]


def fit(X, y, model, rows, w=None) -> LR:
    return LR(MODELS[model], PIXEL_PROTECTED).fit(X[rows], y[rows], None if w is None else w[rows])


def loho_or_loco(df, w, rain_ref, groups=None, polys=None) -> dict:
    y = df["label"].to_numpy()

    def thin(idx, rng):
        p_, n_ = idx[y[idx] == 1], idx[y[idx] == 0]
        return np.r_[p_, rng.choice(n_, size=min(len(n_), NEG_RATIO * len(p_)), replace=False)]

    g = df["huc12"].to_numpy() if groups is None else groups
    pol = huc_polygons().geometry if polys is None else polys
    out = {}
    for m in MODELS:
        cv = cross_val(X_of(df, m), y, g, df[["x", "y"]].to_numpy(), pol, MODELS[m], PIXEL_PROTECTED,
                       {"rain_mm": rain_ref}, subsample=thin)
        out[m] = cv["ref"]
    return out


def compare(scores: dict, df, w) -> dict:
    y, rain, huc = df["label"].to_numpy(), df["rain_mm"].to_numpy(), df["huc12"].to_numpy()
    zero = np.zeros(len(y))
    ev = {m: evaluate(s, y, rain, huc, y.astype(float), zero, w=w) for m, s in scores.items()}
    ev["slope"] = evaluate(df["slope_deg"].to_numpy(), y, rain, huc, y.astype(float), zero, w=w)
    out = {m: {k: {"value": e[k]["value"], "ci95": e[k]["ci95"]} for k in KEYS} for m, e in ev.items()}
    out["delta_no_geology_minus_current"] = {k: paired_delta(ev["no_geology"], ev["current"], k) for k in KEYS}
    for m in MODELS:
        out[f"delta_{m}_minus_slope"] = {k: paired_delta(ev[m], ev["slope"], k) for k in KEYS}
    return out


def watauga_part(rain_ref) -> dict:
    B = build()
    shape = B["shape"]
    pos, neg_test, neg_train, pos_old = B["pos_test"], B["neg_test"], B["neg_train"], B["pos_old"]
    idx = np.r_[pos, neg_test]
    y = np.r_[np.ones(len(pos)), np.zeros(len(neg_test))].astype(int)
    groups = np.r_[B["own_test"].astype(np.int64), -1 - np.arange(len(neg_test))]
    rt = B["rain"][idx]
    aoi = training_cells()
    ya = aoi["label"].to_numpy()
    rows = thin_all(ya)
    ft = frame(idx, shape, smooth=False).assign(rain_mm=rain_ref)
    fs = frame(idx, shape, smooth=True).assign(rain_mm=rain_ref)
    rng = np.random.default_rng(C.SEED + 60)
    tr_idx = np.r_[pos_old, neg_train]
    ytr = np.r_[np.ones(len(pos_old)), np.zeros(len(neg_train))].astype(int)
    keep = np.r_[np.arange(len(pos_old)), len(pos_old) + rng.choice(len(neg_train),
                                                                     size=min(len(neg_train), NEG_RATIO * len(pos_old)),
                                                                     replace=False)]
    fr = frame(tr_idx[keep], shape, smooth=True).assign(rain_mm=B["rain"][tr_idx[keep]])
    res, reps = {}, {}
    for m in MODELS:
        fin = fit(X_of(aoi, m), ya, m, rows)
        r = auc_ci(fin.linear(X_of(ft, m)), y, groups, rt)
        reps[m] = r.pop("_reps")
        res[f"transfer_{m}"] = r
        m40 = fit(X_of(fr, m), ytr[keep], m, np.arange(len(keep)))
        r40 = auc_ci(m40.linear(X_of(fs, m)), y, groups, rt)
        r40.pop("_reps")
        res[f"temporal_1940_{m}"] = r40
    rs = auc_ci(ft["slope_deg"].to_numpy(), y, groups, rt)
    reps["slope"] = rs.pop("_reps")
    res["slope_alone"] = rs
    d = reps["no_geology"][:, 0] - reps["current"][:, 0]
    res["delta_transfer_no_geology_minus_current"] = {
        "value": res["transfer_no_geology"]["auc"] - res["transfer_current"]["auc"],
        "ci95": [float(x) for x in np.nanquantile(d, [0.025, 0.975])]}
    d = reps["no_geology"][:, 0] - reps["slope"][:, 0]
    res["delta_transfer_no_geology_minus_slope"] = {
        "value": res["transfer_no_geology"]["auc"] - rs["auc"],
        "ci95": [float(x) for x in np.nanquantile(d, [0.025, 0.975])]}
    res["test_outlines"], res["test_cells"] = B["info"]["helene_test_outlines_with_cells"], int(len(pos))
    return res


def ranking_and_stability(rain_ref) -> dict:
    aoi = training_cells()
    ya, huc = aoi["label"].to_numpy(), aoi["huc12"].to_numpy()
    ds = pd.read_parquet(C.INTERIM / f"labels_{REGION}" / "domain_sample.parquet")
    ds = ds[ds["hillslope"] == 1].assign(rain_mm=rain_ref).reset_index(drop=True)
    rows = thin_all(ya)
    fin = {m: fit(X_of(aoi, m), ya, m, rows) for m in MODELS}
    sc = {m: fin[m].linear(X_of(ds, m)) for m in MODELS}
    top = {m: sc[m] >= np.quantile(sc[m], 0.90) for m in MODELS}
    inter = (top["current"] & top["no_geology"]).sum()
    out = {"sample_cells": int(len(ds)),
           "spearman_final_scores": float(spearmanr(sc["current"], sc["no_geology"])[0]),
           "top10_overlap_share": float(inter / top["current"].sum()),
           "top10_share_by_geology": {m: ds.loc[top[m], "geology"].value_counts(normalize=True).round(4)
                                      .sort_index().to_dict() for m in MODELS},
           "hillslope_share_by_geology": ds["geology"].value_counts(normalize=True).round(4).sort_index().to_dict()}
    # stability: 30 HUC-12 bootstrap refits, identical resamples for both models
    ug, gi = np.unique(huc, return_inverse=True)
    stab = {}
    for m in MODELS:
        X = X_of(aoi, m)
        Xs = X_of(ds, m)
        rng = np.random.default_rng(C.SEED + 30)
        e_fin = class_edges(fin[m], Xs)
        c_fin = to_class(fin[m].linear(Xs), e_fin)
        cls = []
        for _ in range(N_REFITS):
            mult = np.bincount(rng.integers(0, len(ug), len(ug)), minlength=len(ug))[gi]
            r_ = np.flatnonzero(mult > 0)
            p_, n_ = r_[ya[r_] == 1], r_[ya[r_] == 0]
            n_ = rng.choice(n_, size=min(len(n_), NEG_RATIO * len(p_)), replace=False)
            sel = np.r_[p_, n_]
            mod = LR(MODELS[m], PIXEL_PROTECTED).fit(X[sel], ya[sel], mult[sel].astype(float))
            cls.append(to_class(mod.linear(Xs), class_edges(mod, Xs)))
        hi = np.percentile(np.stack(cls), 90, axis=0, method="nearest")
        in10 = c_fin <= 10
        stab[m] = {"top10_stays_in_top10_in_90pct_of_refits": float((hi[in10] <= 10).mean()),
                   "top10_p90_class_beyond_20": float((hi[in10] > 20).mean())}
    out["stability"] = stab
    return out


def run() -> dict:
    df, w, rain_ref = load()
    res = {"aoi_loho": compare(loho_or_loco(df, w, rain_ref), df, w)}
    print("aoi", json.dumps(res["aoi_loho"]["delta_no_geology_minus_current"], default=float), flush=True)
    cty = counties().reset_index(drop=True)
    cpolys = pd.Series(list(cty.geometry), index=range(1, len(cty) + 1))
    res["leave_one_county_out"] = compare(
        loho_or_loco(df, w, rain_ref, groups=df["county"].to_numpy().astype(int), polys=cpolys), df, w)
    print("loco", json.dumps(res["leave_one_county_out"]["delta_no_geology_minus_current"], default=float), flush=True)
    res["watauga"] = watauga_part(rain_ref)
    res["ranking_and_stability"] = ranking_and_stability(rain_ref)
    A, L, W = res["aoi_loho"]["delta_no_geology_minus_current"], \
        res["leave_one_county_out"]["delta_no_geology_minus_current"], res["watauga"]["delta_transfer_no_geology_minus_current"]
    r1 = all(A[k]["ci95"][0] >= -0.01 for k in KEYS)
    r2a = L["auc_rain_stratified"]["ci95"][0] > 0
    r2b = W["ci95"][0] > 0
    res["decision"] = {"R1_aoi_non_inferior": bool(r1), "R2a_leave_one_county_out": bool(r2a),
                       "R2b_watauga": bool(r2b), "replace_current_model": bool(r1 and r2a and r2b)}
    (C.VALIDATION / "nogeo_test.json").write_text(json.dumps(res, indent=1, default=float))
    write_report()
    print(json.dumps(res["decision"], indent=1), flush=True)
    return res


if __name__ == "__main__":
    run()
