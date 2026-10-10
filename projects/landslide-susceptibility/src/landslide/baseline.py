"""M4: logistic-regression baseline and the spatial validation harness (PLAN §7, §8; gates in METHOD §Validation).

Two analytical units, one design:
* **slope units** (A = 0.1 km^2, units >= 50 % in the triggered domain): every unit, no negative sampling;
  label = >= 1 positive source area (representative point). Reporting unit and gate model.
* **5 m cells** on hillslopes: all positive cells vs a 1:10 per-fold subsample of the M3 negative pool.

Validation: leave-one-HUC-12-out; training rows within 500 m of the held-out watershed are dropped. Rainfall
(MRMS 72 h) enters as an adjustment covariate and the susceptibility score is the prediction at the
triggered-domain median rainfall (and, for units, at the median unit area), i.e. terrain ranked under equal
trigger. Metrics: rainfall-stratified AUC (50 mm bins; primary), within-watershed AUC, pooled AUC (contrast),
average precision, capture of mapped initiations in the top k % of area; intervals by HUC-12 block bootstrap.

Contrasts and checks: random 5-fold split, no buffer, leave-one-HUC-10-out, terrain-only model, slope-only and
rainfall-only scores, slope-only positive rule, negative-sample bias (pool vs unrestricted domain sample),
residual correlogram, distance of held-out positives to training positives, county observed/expected.
Writes validation/m4_baseline.json, validation/folds_huc12.csv, validation/M4_BASELINE.md and
data/out/oof_units.parquet.
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from scipy.spatial import cKDTree
from scipy.spatial.distance import pdist
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression

from . import config as C
from .inventory import positive_mask
from .labels import REGION, counties, inventory
from .metrics import Ranked, block_bootstrap, brier, ci, reliability
from .report_m4 import write as write_report

UNIT_A = "0.1"
BUFFER_M = 500
RAIN_BIN_MM = 50
KS = (0.05, 0.10, 0.20)
N_BOOT = 2000
NEG_RATIO = 10
VIF_MAX = 10.0
REPLICATE_MIN_POS = 50  # positive units per HUC-12 for a replicate watershed
PER_HUC_MIN_POS = 10  # below: no per-HUC score ("too few to evaluate")
FOLD_FLAG_POS = 20  # below: fold flagged
GATE_G1 = (0.70, 0.60)  # stratified AUC point, lower bound
GATE_G2 = (0.60, 7)  # within-watershed AUC threshold, replicates that must exceed it

UNIT_FEATURES = [
    "slope_deg_p90", "slope_deg_mean", "slope_deg_sd", "planc_15_mean", "profc_15_mean", "planc_5_mean",
    "tpi_50_mean", "tpi_250_mean", "relief_250_mean", "rough_25_mean", "log_area_mean", "hand_mean",
    "dist_channel_mean", "northness_mean", "eastness_mean", "canopy_mean", "bedrock_cm_mean",
    "dev_frac", "open_frac", "geology_2_frac", "geology_3_frac", "geology_4_frac", "hsg_cd_frac",
    "log_domain_km2", "rain_mm_mean",
]
UNIT_PROTECTED = ("rain_mm_mean", "log_domain_km2")  # adjustment covariates, never VIF-pruned
PIXEL_CONT = ["slope_deg", "planc_15", "profc_15", "planc_5", "profc_5", "tpi_50", "tpi_250", "relief_50",
              "relief_250", "rough_25", "tri", "log_area", "hand", "dist_channel", "northness", "eastness",
              "canopy", "bedrock_cm", "bedrock_recorded"]
PIXEL_CAT = {"lc_group": (2, 3, 4, 5), "geology": (2, 3, 4), "hsg": (0, 3, 4)}  # reference: forest, group 1, A/B
PIXEL_PROTECTED = ("rain_mm",)


# ------------------------------------------------------------------------------------------------- model
def vif_prune(X: np.ndarray, names: list[str], protected) -> list[int]:
    """Forward selection in priority order: protected columns first, then `names` in listed order (the
    physical-rationale order; slope first). A column is kept if every VIF of the kept set stays <= VIF_MAX.
    Greedy backward pruning (drop the largest VIF) was used first and removed slope, the primary predictor,
    because the roughness / relief / curvature terms share its variance (decisions log 2026-10-09)."""
    order = [i for i, n in enumerate(names) if n in protected] + [i for i, n in enumerate(names) if n not in protected]
    keep: list[int] = []
    for i in order:
        if X[:, i].std() == 0:  # constant in this training set (e.g. a class absent from a subdomain)
            continue
        cand = keep + [i]
        if len(cand) > 1 and np.diag(np.linalg.pinv(np.corrcoef(X[:, cand], rowvar=False))).max() > VIF_MAX:
            continue
        keep = cand
    return sorted(keep)


class LR:
    """Standardize -> VIF prune -> L2 logistic regression, all fitted on the training rows only."""

    def __init__(self, names: list[str], protected=()):
        self.names, self.protected = names, protected

    def fit(self, X, y, w=None, groups=None):
        self.mu, self.sd = X.mean(0), X.std(0)
        self.sd[self.sd == 0] = 1
        Z = (X - self.mu) / self.sd
        self.keep = vif_prune(Z, self.names, self.protected)
        self.m = LogisticRegression(C=1.0, max_iter=5000).fit(Z[:, self.keep], y, sample_weight=w)
        return self

    def linear(self, X):
        return ((X - self.mu) / self.sd)[:, self.keep] @ self.m.coef_[0] + self.m.intercept_[0]

    def coefs(self) -> dict:
        return {self.names[i]: float(c) for i, c in zip(self.keep, self.m.coef_[0])}


def at_reference(X: np.ndarray, names: list[str], ref: dict) -> np.ndarray:
    X = X.copy()
    for k, v in ref.items():
        X[:, names.index(k)] = v
    return X


# ------------------------------------------------------------------------------------------------- data
def huc_polygons() -> gpd.GeoDataFrame:
    return gpd.read_parquet(C.RAW / "huc12.parquet").to_crs(C.CRS).set_index("huc12")


def unit_centroids(a_km2: str) -> pd.DataFrame:
    with rasterio.open(C.INTERIM / f"units_{REGION}" / f"units_{a_km2}.tif") as s:
        lab, tr = s.read(1), s.transform
    n = int(lab.max()) + 1
    rr, cc = np.indices(lab.shape)
    cnt = np.maximum(np.bincount(lab.ravel(), minlength=n), 1)
    r = np.bincount(lab.ravel(), rr.ravel(), n) / cnt
    c = np.bincount(lab.ravel(), cc.ravel(), n) / cnt
    x, y = tr * (c + 0.5, r + 0.5)
    return pd.DataFrame({"unit": np.arange(n), "cx": x, "cy": y})


def sources_per_unit(a_km2: str, mask: pd.Series, inv, cty) -> np.ndarray:
    """Number of representative points of `mask` polygons (inside the counties) per unit id."""
    pts = inv[mask].geometry.representative_point()
    pts = pts[pts.within(cty.union_all())]
    with rasterio.open(C.INTERIM / f"units_{REGION}" / f"units_{a_km2}.tif") as s:
        lab, tr = s.read(1), s.transform
    rr, cc = rasterio.transform.rowcol(tr, pts.x.to_numpy(), pts.y.to_numpy())
    rr, cc = np.asarray(rr), np.asarray(cc)
    ok = (rr >= 0) & (rr < lab.shape[0]) & (cc >= 0) & (cc < lab.shape[1])
    return np.bincount(lab[rr[ok], cc[ok]], minlength=int(lab.max()) + 1)


def load_units() -> pd.DataFrame:
    u = pd.read_parquet(C.OUT / f"units_{UNIT_A}.parquet")
    u = u[u["in_model_domain"]].reset_index(drop=True)
    inv, cty = inventory(), counties()
    helene_src = inv["event"].eq("helene") & inv["is_source"]
    n_var = sources_per_unit(UNIT_A, positive_mask(inv, require_natural_runoff=False), inv, cty)
    n_other = sources_per_unit(UNIT_A, helene_src & ~positive_mask(inv, require_natural_runoff=False), inv, cty)
    u["n_sources_variant"] = n_var[u["unit"]]
    u["label_variant"] = (u["n_sources_variant"] > 0).astype(np.int8)
    u["n_other_helene_sources"] = n_other[u["unit"]]
    u["dev_frac"] = u["lc_group_2_frac"] + u["lc_group_3_frac"]
    u["open_frac"] = u["lc_group_4_frac"]
    u["hsg_cd_frac"] = u["hsg_3_frac"] + u["hsg_4_frac"]
    u["log_domain_km2"] = np.log(u["domain_km2"])
    u = u.merge(unit_centroids(UNIT_A), on="unit", how="left")
    return u


def pixel_matrix(df: pd.DataFrame) -> np.ndarray:
    cols = [df[k].to_numpy(np.float64) for k in PIXEL_CONT]
    cols += [(df[k].to_numpy() == c).astype(np.float64) for k, cs in PIXEL_CAT.items() for c in cs]
    return np.column_stack(cols + [df["rain_mm"].to_numpy(np.float64)])


PIXEL_NAMES = PIXEL_CONT + [f"{k}_{c}" for k, cs in PIXEL_CAT.items() for c in cs] + ["rain_mm"]


def buffered_out(xy: np.ndarray, poly, buffer_m: float) -> np.ndarray:
    """True where a point lies inside the held-out watershed grown by buffer_m."""
    return shapely.contains_xy(poly.buffer(buffer_m), xy[:, 0], xy[:, 1])


# ------------------------------------------------------------------------------------------------- CV
def cross_val(X, y, groups, xy, polys, names, protected, ref, *, buffer_m=BUFFER_M, w=None, subsample=None,
              seed=C.SEED, extra=None, make_model=None, perm=None):
    """Leave-one-group-out with a buffer; returns OOF linear scores at reference values and at actual values,
    the OOF probability, the per-fold models, coefficients and fold sizes.

    `extra` = (X_extra, groups_extra) rows that are only scored (never trained on). `subsample(train_idx, rng)`
    may thin the training rows. `make_model()` returns an object with fit(X, y, w, groups) and linear(X)
    (default: LR). `perm` = {name: column indices}: grouped permutation importance, i.e. the OOF reference
    score with those columns shuffled jointly across the held-out rows."""
    make_model = make_model or (lambda: LR(names, protected))
    n = len(y)
    oof_ref, oof_act = np.full(n, np.nan), np.full(n, np.nan)
    ex_ref = None if extra is None else np.full(len(extra[1]), np.nan)
    oof_perm = {k: np.full(n, np.nan) for k in (perm or {})}
    coefs, folds, models = [], [], {}
    rng = np.random.default_rng(seed)
    for g in np.unique(groups):
        test = groups == g
        if polys is not None:
            drop = buffered_out(xy, polys[g], buffer_m) if buffer_m > 0 else test
            train = ~test & ~drop
        else:
            train = ~test
        tr_idx = np.flatnonzero(train)
        if subsample is not None:
            tr_idx = subsample(tr_idx, rng)
        m = make_model().fit(X[tr_idx], y[tr_idx], None if w is None else w[tr_idx], groups[tr_idx])
        Xt = at_reference(X[test], names, ref)
        oof_ref[test] = m.linear(Xt)
        oof_act[test] = m.linear(X[test])
        for k, cols in (perm or {}).items():
            Xp = Xt.copy()
            Xp[:, cols] = Xt[rng.permutation(len(Xt))][:, cols]
            oof_perm[k][test] = m.linear(Xp)
        if extra is not None:
            et = extra[1] == g
            ex_ref[et] = m.linear(at_reference(extra[0][et], names, ref))
        if hasattr(m, "coefs"):
            coefs.append(m.coefs())
        models[g] = m
        folds.append({"group": g, "n_train": int(tr_idx.size), "n_test": int(test.sum()),
                      "pos_test": int(y[test].sum()), "dropped_by_buffer": int((~test & ~train).sum()),
                      **({"params": m.params} if hasattr(m, "params") else {})})
    return {"ref": oof_ref, "act": oof_act, "p": 1 / (1 + np.exp(-oof_act)), "coefs": coefs, "folds": folds,
            "extra_ref": ex_ref, "models": models, "perm": oof_perm}


def random_groups(n: int, k: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).permutation(np.arange(n) % k)


# ------------------------------------------------------------------------------------------------- evaluation
def rain_bin(rain: np.ndarray) -> np.ndarray:
    return (np.floor(rain / RAIN_BIN_MM) * RAIN_BIN_MM).astype(np.int64)


def evaluate(score, y, rain, huc, hits, area, w=None, boot=True, seed=C.SEED) -> dict:
    """Point metrics and HUC-12 block-bootstrap intervals for one score."""
    r_rain, r_huc = Ranked(score, y, rain_bin(rain)), Ranked(score, y, huc)
    w0 = np.ones(len(y)) if w is None else w

    def stat(b):
        ww = w0 * b
        return np.r_[r_rain.stratified_auc(ww), r_huc.stratified_auc(ww), r_rain.auc(ww),
                     r_rain.average_precision(ww), r_rain.capture(hits, area, KS, ww)]

    point = stat(np.ones(len(y)))
    keys = ["auc_rain_stratified", "auc_within_huc", "auc_pooled", "average_precision"] + \
           [f"capture_top{int(k * 100)}" for k in KS]
    out = {k: {"value": float(v)} for k, v in zip(keys, point)}
    prev = float(np.average(y, weights=w0))
    out["average_precision"]["prevalence_baseline"] = prev
    if boot:
        reps = block_bootstrap(huc, stat, N_BOOT, seed)
        for k, (lo, hi) in zip(keys, ci(reps)):
            out[k]["ci95"] = [float(lo), float(hi)]
        out["_reps"] = reps
    return out


def paired_delta(a: dict, b: dict, key: str) -> dict:
    """Difference a - b with the interval from the same bootstrap resamples (same seed -> same draws)."""
    i = ["auc_rain_stratified", "auc_within_huc", "auc_pooled", "average_precision"].index(key)
    d = a["_reps"][:, i] - b["_reps"][:, i]
    return {"value": a[key]["value"] - b[key]["value"], "ci95": [float(x) for x in np.nanquantile(d, [.025, .975])]}


def per_huc(score, y, huc, hits, area) -> pd.DataFrame:
    rows = []
    for g in np.unique(huc):
        m = huc == g
        npos = int(y[m].sum())
        r = Ranked(score[m], y[m])
        ok = npos >= PER_HUC_MIN_POS and (y[m] == 0).any()
        rows.append({"huc12": g, "units": int(m.sum()), "positive_units": npos, "sources": int(hits[m].sum()),
                     "auc": r.auc() if ok else np.nan,
                     "capture_top10": float(r.capture(hits[m], area[m], [0.10])[0]) if ok else np.nan})
    return pd.DataFrame(rows)


def strip(d):
    if isinstance(d, dict):
        return {k: strip(v) for k, v in d.items() if not str(k).startswith("_")}
    return d


def correlogram(xy, resid, seed, n=6000, edges_km=(0, 0.25, 0.5, 1, 2, 4, 8, 16)) -> list[dict]:
    """Correlation of OOF Pearson residuals between unit pairs by distance class (random subset of units)."""
    rng = np.random.default_rng(seed)
    i = rng.choice(len(resid), size=min(n, len(resid)), replace=False)
    z = (resid[i] - resid[i].mean()) / resid[i].std()
    d = pdist(xy[i]) / 1000
    iu = np.triu_indices(len(i), 1)
    prod = z[iu[0]] * z[iu[1]]
    out = []
    for lo, hi in zip(edges_km[:-1], edges_km[1:]):
        m = (d >= lo) & (d < hi)
        out.append({"km": [lo, hi], "pairs": int(m.sum()), "r": float(prod[m].mean()) if m.any() else None})
    return out


# ------------------------------------------------------------------------------------------------- units
def run_units(rain_ref: float) -> tuple[dict, pd.DataFrame]:
    u = load_units()
    X = u[UNIT_FEATURES].to_numpy(np.float64)
    huc = u["huc12"].to_numpy()
    xy = u[["cx", "cy"]].to_numpy()
    polys = huc_polygons().geometry
    rain = u["rain_mm_mean"].to_numpy()
    area = u["domain_km2"].to_numpy()
    area_ref = float(np.exp(np.median(u["log_domain_km2"])))
    ref = {"rain_mm_mean": rain_ref, "log_domain_km2": np.log(area_ref)}
    res: dict = {"n_units": len(u), "reference_values": {"rain_mm": rain_ref, "unit_domain_km2": area_ref}}

    terrain_names = [k for k in UNIT_FEATURES if k != "rain_mm_mean"]
    Xt = u[terrain_names].to_numpy(np.float64)
    runs = {}
    for rule, ycol, hcol in (("primary", "label", "n_sources"), ("slope_only_variant", "label_variant",
                                                                 "n_sources_variant")):
        y = u[ycol].to_numpy()
        hits = u[hcol].to_numpy(np.float64)
        cv = cross_val(X, y, huc, xy, polys, UNIT_FEATURES, UNIT_PROTECTED, ref)
        runs[rule] = cv
        ev = {"lr_at_reference_rain": evaluate(cv["ref"], y, rain, huc, hits, area),
              "lr_actual_rain": evaluate(cv["act"], y, rain, huc, hits, area),
              "slope_p90_only": evaluate(u["slope_deg_p90"].to_numpy(), y, rain, huc, hits, area),
              "rain_only": evaluate(rain, y, rain, huc, hits, area)}
        if rule == "primary":
            tcv = cross_val(Xt, y, huc, xy, polys, terrain_names, ("log_domain_km2",),
                            {"log_domain_km2": np.log(area_ref)})
            ev["terrain_only_model"] = evaluate(tcv["ref"], y, rain, huc, hits, area)
        out = {"positive_units": int(y.sum()), "sources": int(hits.sum()), "scores": ev,
               "delta_lr_minus_slope": {k: paired_delta(ev["lr_at_reference_rain"], ev["slope_p90_only"], k)
                                        for k in ("auc_rain_stratified", "auc_within_huc")}}
        if rule == "primary":
            out["delta_lr_minus_terrain_only"] = {k: paired_delta(ev["lr_at_reference_rain"],
                                                                  ev["terrain_only_model"], k)
                                                  for k in ("auc_rain_stratified", "auc_within_huc")}
            p = cv["p"]
            out["calibration_diagnostic"] = {"brier": brier(p, y), "brier_climatology": brier(np.full(len(y), y.mean()), y),
                                             "reliability": reliability(p, y)}
            out["calibration_diagnostic"]["brier_skill"] = 1 - out["calibration_diagnostic"]["brier"] / \
                out["calibration_diagnostic"]["brier_climatology"]
            # contrasts of the validation design (point values only)
            nb = cross_val(X, y, huc, xy, polys, UNIT_FEATURES, UNIT_PROTECTED, ref, buffer_m=0)
            rg = random_groups(len(y), 5, C.SEED)
            rs = cross_val(X, y, rg, xy, None, UNIT_FEATURES, UNIT_PROTECTED, ref)
            h10 = np.array([h[:10] for h in huc])
            p10 = gpd.GeoSeries(polys).groupby(polys.index.str[:10]).agg(lambda s: shapely.union_all(s.values))
            l10 = cross_val(X, y, h10, xy, p10, UNIT_FEATURES, UNIT_PROTECTED, ref)
            out["design_contrasts"] = {
                "loho_huc12_no_buffer": strip(evaluate(nb["ref"], y, rain, huc, hits, area, boot=False)),
                "random_5fold": strip(evaluate(rs["ref"], y, rain, huc, hits, area, boot=False)),
                "leave_one_huc10_out": strip(evaluate(l10["ref"], y, rain, huc, hits, area, boot=False)),
                "huc10_groups": int(len(np.unique(h10))),
            }
            # units whose only Helene sources are non-primary (road-related etc.) are label 0: sensitivity
            amb = (u["n_other_helene_sources"].to_numpy() > 0) & (y == 0)
            out["units_with_only_nonprimary_sources"] = {
                "n": int(amb.sum()),
                "auc_rain_stratified_without_them": Ranked(cv["ref"][~amb], y[~amb],
                                                           rain_bin(rain[~amb])).stratified_auc()}
            ph = per_huc(cv["ref"], y, huc, hits, area)
            out["per_huc"] = ph.to_dict("records")
            rep = ph[ph["positive_units"] >= REPLICATE_MIN_POS]
            out["replicates"] = {"n": int(len(rep)), "auc_median": float(rep["auc"].median()),
                                 "auc_min": float(rep["auc"].min()), "auc_max": float(rep["auc"].max()),
                                 "capture_top10_median": float(rep["capture_top10"].median())}
            # residual correlogram and held-out-to-training distance
            resid = (y - p) / np.sqrt(p * (1 - p))
            out["residual_correlogram"] = correlogram(xy, resid, C.SEED)
            pos = y == 1
            dist = []
            for g in np.unique(huc[pos]):
                a, b = pos & (huc == g), pos & (huc != g)
                dist.append(cKDTree(xy[b]).query(xy[a])[0])
            dist = np.concatenate(dist)
            out["heldout_positive_to_nearest_training_positive_m"] = {
                "median": float(np.median(dist)), "p10": float(np.percentile(dist, 10)),
                "share_lt_1km": float((dist < 1000).mean())}
            # county observed / expected (mapping-effort check, conditioned on terrain + rainfall)
            out["county_observed_over_expected"] = {
                int(c): float(y[u["county"] == c].sum() / p[u["county"] == c].sum()) for c in np.unique(u["county"])}
            # coefficients: final all-data model + LOHO fold range
            fin = LR(UNIT_FEATURES, UNIT_PROTECTED).fit(X, y)
            fc = pd.DataFrame(cv["coefs"])
            out["coefficients_standardized"] = {
                k: {"final": v, "fold_min": float(fc[k].min()), "fold_max": float(fc[k].max()),
                    "folds_kept": int(fc[k].notna().sum())} for k, v in fin.coefs().items()}
            out["vif_pruned_in_final"] = [k for k in UNIT_FEATURES if k not in fin.coefs()]
            u["final_ref"] = fin.linear(at_reference(X, UNIT_FEATURES, ref))
            out["folds"] = cv["folds"]
        res[rule] = out
    # variant vs primary: same terrain ranking? cross-scored on primary labels
    yp = u["label"].to_numpy()
    hp = u["n_sources"].to_numpy(np.float64)
    e_var_on_prim = evaluate(runs["slope_only_variant"]["ref"], yp, rain, huc, hp, area)
    res["variant_comparison"] = {
        "spearman_oof_scores": float(spearmanr(runs["primary"]["ref"], runs["slope_only_variant"]["ref"])[0]),
        "variant_model_scored_on_primary_labels": strip(e_var_on_prim),
        "delta_primary_model_minus_variant_model_on_primary_labels": {
            k: paired_delta(res["primary"]["scores"]["lr_at_reference_rain"], e_var_on_prim, k)
            for k in ("auc_rain_stratified", "auc_within_huc")},
    }
    u["oof_ref"] = runs["primary"]["ref"]
    u["oof_ref_variant"] = runs["slope_only_variant"]["ref"]
    u["oof_p_actual"] = runs["primary"]["p"]
    return res, u


# ------------------------------------------------------------------------------------------------- pixels
def run_pixels(rain_ref: float) -> dict:
    d = C.INTERIM / f"labels_{REGION}"
    rep = json.loads((d / "report.json").read_text())
    pos = pd.read_parquet(d / "positives.parquet")
    neg = pd.read_parquet(d / "negatives.parquet")
    run = pd.read_parquet(d / "positives_runoff.parquet")
    dom = pd.read_parquet(d / "domain_sample.parquet")
    pos, neg, run, dom = (t[(t["hillslope"] == 1) & t["huc12"].notna()].reset_index(drop=True)
                          for t in (pos, neg, run, dom))
    neg_w = rep["domain"]["eligible_negative_hillslope_cells"] / len(neg)
    polys = huc_polygons().geometry
    ref = {"rain_mm": rain_ref}
    res = {"hillslope_positive_cells": len(pos), "hillslope_pool_negatives": len(neg),
           "negative_weight": neg_w, "hillslope_domain_sample": len(dom)}
    for rule, P in (("primary", pos), ("slope_only_variant", pd.concat([pos, run], ignore_index=True))):
        df = pd.concat([P, neg], ignore_index=True)
        X, y = pixel_matrix(df), df["label"].to_numpy()
        huc, xy = df["huc12"].to_numpy(), df[["x", "y"]].to_numpy()
        is_pos = np.flatnonzero(y == 1)

        def thin(idx, rng, y=y):
            p_ = idx[y[idx] == 1]
            n_ = idx[y[idx] == 0]
            return np.r_[p_, rng.choice(n_, size=min(len(n_), NEG_RATIO * len(p_)), replace=False)]

        Xd = pixel_matrix(dom)
        cv = cross_val(X, y, huc, xy, polys, PIXEL_NAMES, PIXEL_PROTECTED, ref, subsample=thin,
                       extra=(Xd, dom["huc12"].to_numpy()))
        w = np.where(y == 1, 1.0, neg_w)
        rain = df["rain_mm"].to_numpy()
        # AUC etc. vs the exclusion-filtered negative pool (prevalence-weighted)
        ev = evaluate(cv["ref"], y, rain, huc, y.astype(np.float64), np.zeros(len(y)), w=w)
        # capture: area from the unrestricted domain sample (positives carry hits, the sample carries area)
        dneg = dom["positive"].to_numpy() == 0
        sc = np.r_[cv["ref"][is_pos], cv["extra_ref"][dneg]]
        hits = np.r_[np.ones(len(is_pos)), np.zeros(dneg.sum())]
        ar = 1 - hits
        cap = Ranked(sc, hits).capture(hits, ar, KS)
        for k, v in zip(KS, cap):
            ev[f"capture_top{int(k * 100)}"] = {"value": float(v)}
        out = {"positive_cells": int(y.sum()), "scores": {"lr_at_reference_rain": strip(ev)}}
        if rule == "primary":
            ev_s = evaluate(df["slope_deg"].to_numpy(), y, rain, huc, y.astype(np.float64), np.zeros(len(y)), w=w)
            out["scores"]["slope_only"] = strip({k: v for k, v in ev_s.items() if not k.startswith("capture")})
            out["delta_lr_minus_slope"] = {k: paired_delta(ev, ev_s, k) for k in ("auc_rain_stratified", "auc_within_huc")}
            # negative-sample bias: positives vs unrestricted domain cells (incl. excluded), same OOF models
            hd = dom["huc12"].to_numpy()
            rd = dom["rain_mm"].to_numpy()
            yb = np.r_[np.ones(len(is_pos)), np.zeros(dneg.sum())]
            rb = np.r_[rain[is_pos], rd[dneg]]
            hb = np.r_[huc[is_pos], hd[dneg]]
            excl = dom["exclusion"].to_numpy()[dneg] == 1
            out["negative_sample_bias"] = {
                "auc_rain_stratified_vs_pool": ev["auc_rain_stratified"]["value"],
                "auc_rain_stratified_vs_unrestricted_domain": Ranked(sc, yb, rain_bin(rb)).stratified_auc(),
                "auc_within_huc_vs_unrestricted_domain": Ranked(sc, yb, hb).stratified_auc(),
                "excluded_share_of_domain_sample": float(excl.mean()),
                "excluded_vs_eligible_auc": Ranked(cv["extra_ref"][dneg], excl.astype(int),
                                                   rain_bin(rd[dneg])).stratified_auc(),
            }
            rg = random_groups(len(y), 5, C.SEED)
            rs = cross_val(X, y, rg, xy, None, PIXEL_NAMES, PIXEL_PROTECTED, ref, subsample=thin)
            out["design_contrasts"] = {"random_5fold": {
                k: v for k, v in strip(evaluate(rs["ref"], y, rain, huc, y.astype(np.float64), np.zeros(len(y)),
                                                w=w, boot=False)).items() if not k.startswith("capture")}}
            fin = LR(PIXEL_NAMES, PIXEL_PROTECTED).fit(*(lambda i: (X[i], y[i]))(thin(np.arange(len(y)),
                                                                                    np.random.default_rng(C.SEED))))
            fc = pd.DataFrame(cv["coefs"])
            out["coefficients_standardized"] = {
                k: {"final": v, "fold_min": float(fc[k].min()), "fold_max": float(fc[k].max()),
                    "folds_kept": int(fc[k].notna().sum())} for k, v in fin.coefs().items()}
            out["vif_pruned_in_final"] = [k for k in PIXEL_NAMES if k not in fin.coefs()]
            out["folds"] = cv["folds"]
        res[rule] = out
    return res


# ------------------------------------------------------------------------------------------------- report
def gates(units: dict) -> dict:
    s = units["primary"]["scores"]["lr_at_reference_rain"]["auc_rain_stratified"]
    g1 = s["value"] >= GATE_G1[0] and s["ci95"][0] >= GATE_G1[1]
    ph = pd.DataFrame(units["primary"]["per_huc"])
    rep = ph[ph["positive_units"] >= REPLICATE_MIN_POS]
    n_ok = int((rep["auc"] > GATE_G2[0]).sum())
    g2 = n_ok >= GATE_G2[1]
    return {"G1": {"pass": bool(g1), "auc": s["value"], "ci95": s["ci95"], "rule": f">= {GATE_G1[0]}, lower >= {GATE_G1[1]}"},
            "G2": {"pass": bool(g2), "replicates_above": n_ok, "replicates": int(len(rep)),
                   "rule": f"AUC > {GATE_G2[0]} in >= {GATE_G2[1]} of the replicates"},
            "proceed_to_M5": bool(g1 and g2)}


def folds_table(u: pd.DataFrame, pix_folds: list[dict]) -> pd.DataFrame:
    names = huc_polygons()["name"]
    g = u.groupby("huc12").agg(units=("unit", "size"), positive_units=("label", "sum"), sources=("n_sources", "sum"),
                               domain_km2=("domain_km2", "sum"), rain_mm=("rain_mm_mean", "mean"))
    g["name"] = names.reindex(g.index).to_numpy()
    pc = pd.DataFrame(pix_folds).set_index("group")["pos_test"].rename("positive_hillslope_cells")
    g = g.join(pc)
    g["replicate"] = g["positive_units"] >= REPLICATE_MIN_POS
    g["per_huc_score"] = g["positive_units"] >= PER_HUC_MIN_POS
    g["fold_flag_lt20_positive_units"] = g["positive_units"] < FOLD_FLAG_POS
    return g.sort_values("positive_units", ascending=False)


def run() -> dict:
    dom = pd.read_parquet(C.INTERIM / f"labels_{REGION}" / "domain_sample.parquet", columns=["rain_mm"])
    rain_ref = float(np.median(dom["rain_mm"]))
    units, u = run_units(rain_ref)
    pixels = run_pixels(rain_ref)
    res = {"rain_reference_mm": rain_ref, "units": strip(units), "pixels": pixels, "gates": gates(units),
           "settings": {"unit_A_km2": UNIT_A, "buffer_m": BUFFER_M, "rain_bin_mm": RAIN_BIN_MM, "n_boot": N_BOOT,
                        "neg_ratio": NEG_RATIO, "vif_max": VIF_MAX, "seed": C.SEED,
                        "replicate_min_positive_units": REPLICATE_MIN_POS}}
    C.VALIDATION.mkdir(exist_ok=True)
    (C.VALIDATION / "m4_baseline.json").write_text(json.dumps(res, indent=1, default=float))
    folds_table(u, pixels["primary"]["folds"]).to_csv(C.VALIDATION / "folds_huc12.csv", float_format="%.3f")
    u[["unit", "huc12", "county", "label", "label_variant", "n_sources", "domain_km2", "rain_mm_mean",
       "oof_ref", "oof_ref_variant", "oof_p_actual", "final_ref"]].to_parquet(C.OUT / "oof_units.parquet", index=False)
    write_report(res)
    print(json.dumps(res["gates"], indent=1), flush=True)
    return res


if __name__ == "__main__":
    run()
