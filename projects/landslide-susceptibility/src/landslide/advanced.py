"""M5: gradient boosting, 5 m scores aggregated to slope units, and the candidate comparison (PLAN §7, §8;
criteria C1/C2 and the product rule in METHOD §Validation, fixed before the first M5 fit).

Same validation as M4: leave-one-HUC-12-out with a 500 m buffer; rainfall is an adjustment covariate and every
score is the prediction at the reference rainfall (and median unit area). Gradient boosting is tuned only inside
each training fold (inner CV grouped by HUC-12, metric: rainfall-stratified AUC).

Candidates scored on the same units: (a) unit LR, (b) unit GBM, (c) 5 m LR -> units, (d) 5 m GBM -> units, plus
slope p90 alone. Aggregation: unit score = log(mean over the unit's domain cells of exp(cell score)), cells below
the hillslope threshold contributing 0 (per-area intensity). Each 5 m cell is scored by the fold model that did
not see its HUC-12, which also gives out-of-fold 5 m score rasters.

Writes validation/m5_advanced.json, validation/M5_ADVANCED.md, data/out/oof_units_m5.parquet,
data/interim/scores_aoi/oof_{lr,gbm}_5m.tif.
"""

from __future__ import annotations

import json
import os
import pickle
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

from . import config as C
from .aggregate import unit_raster_5m
from .baseline import (NEG_RATIO, PIXEL_CONT, PIXEL_NAMES, PIXEL_PROTECTED, UNIT_A,
                       UNIT_FEATURES, UNIT_PROTECTED, at_reference, cross_val, evaluate, huc_polygons, load_units,
                       paired_delta, per_huc, pixel_matrix, rain_bin, strip)
from .labels import HYDRO_LAYERS, REGION, STACK_FLOAT, STACK_INT, counties, read, roads
from .metrics import Ranked, brier, reliability
from .terrain import LAYERS as TERRAIN_LAYERS

GBM_FIXED = {"learning_rate": 0.05, "l2_regularization": 1.0, "early_stopping": False, "random_state": C.SEED}
GRID_UNITS = [{"max_leaf_nodes": lv, "min_samples_leaf": ms, "max_iter": it}
              for lv in (7, 15, 31) for ms in (20, 100) for it in (100, 300)]
GRID_PIXELS = [{"max_leaf_nodes": lv, "min_samples_leaf": ms, "max_iter": 200} for lv in (15, 31) for ms in (100, 500)]
INNER_FOLDS = {"units": 3, "pixels": 2}
PIXEL_GBM_CAT = ("lc_group", "geology", "hsg")
PIXEL_GBM_NAMES = PIXEL_CONT + list(PIXEL_GBM_CAT) + ["rain_mm"]
WINDOW_ROWS = 256

UNIT_GROUPS = {
    "slope": ["slope_deg_p90", "slope_deg_mean", "slope_deg_sd"],
    "curvature": ["planc_15_mean", "profc_15_mean", "planc_5_mean"],
    "relief / position / roughness": ["tpi_50_mean", "tpi_250_mean", "relief_250_mean", "rough_25_mean"],
    "hydrology": ["log_area_mean", "hand_mean", "dist_channel_mean"],
    "aspect": ["northness_mean", "eastness_mean"],
    "land cover / canopy": ["canopy_mean", "dev_frac", "open_frac"],
    "geology": ["geology_2_frac", "geology_3_frac", "geology_4_frac"],
    "soil": ["bedrock_cm_mean", "hsg_cd_frac"],
}
PIXEL_GROUPS = {
    "slope": ["slope_deg", "tri"],
    "curvature": ["planc_15", "profc_15", "planc_5", "profc_5"],
    "relief / position / roughness": ["tpi_50", "tpi_250", "relief_50", "relief_250", "rough_25"],
    "hydrology": ["log_area", "hand", "dist_channel"],
    "aspect": ["northness", "eastness"],
    "land cover / canopy": ["canopy", "lc_group"],
    "geology": ["geology"],
    "soil": ["bedrock_cm", "bedrock_recorded", "hsg"],
}


def cols_of(groups: dict, names: list[str]) -> dict:
    """Column indices per predictor group; a categorical name also matches its one-hot columns (`hsg_3`)."""
    out = {}
    for g, members in groups.items():
        out[g] = [i for i, n in enumerate(names) if n in members or any(n.startswith(m + "_") and n[len(m) + 1:].isdigit()
                                                                         for m in members)]
    return out


class GBM:
    """HistGradientBoosting with the hyper-parameters chosen by inner grouped CV on the training rows only."""

    def __init__(self, names, grid, inner_folds, ref, categorical=(), rain="rain_mm"):
        self.names, self.grid, self.inner, self.ref = names, grid, inner_folds, ref
        self.cat = np.array([n in categorical for n in names])
        self.rain_i = names.index(rain)

    def _model(self, params):
        return HistGradientBoostingClassifier(categorical_features=self.cat if self.cat.any() else None,
                                              **GBM_FIXED, **params)

    def fit(self, X, y, w=None, groups=None):
        if len(self.grid) > 1:
            scores = []
            gkf = GroupKFold(n_splits=self.inner)
            splits = list(gkf.split(X, y, groups))
            for params in self.grid:
                s = np.full(len(y), np.nan)
                for tr, te in splits:
                    m = self._model(params).fit(X[tr], y[tr], sample_weight=None if w is None else w[tr])
                    s[te] = self._logit(m, at_reference(X[te], self.names, self.ref))
                ok = np.isfinite(s)
                scores.append(Ranked(s[ok], y[ok], rain_bin(X[ok, self.rain_i])).stratified_auc())
            self.params = self.grid[int(np.nanargmax(scores))]
            self.inner_scores = scores
        else:
            self.params = self.grid[0]
        self.m = self._model(self.params).fit(X, y, sample_weight=w)
        return self

    @staticmethod
    def _logit(m, X):
        p = np.clip(m.predict_proba(X)[:, 1], 1e-12, 1 - 1e-12)
        return np.log(p / (1 - p))

    def linear(self, X):
        return self._logit(self.m, X)


def pixel_gbm_matrix(df) -> np.ndarray:
    return np.column_stack([df[k].to_numpy(np.float64) for k in PIXEL_GBM_NAMES])


# ------------------------------------------------------------------------------------------------- 5 m scoring
def score_rasters(models: dict, rain_ref: float, n_units: int) -> dict:
    """Score every hillslope domain cell with its HUC-12 fold model; write OOF rasters and per-unit sums."""
    lab = C.INTERIM / f"labels_{REGION}"
    dom = read(lab / "domain.tif").astype(bool)
    hill = read(lab / "hillslope.tif").astype(bool)
    shape = dom.shape
    with rasterio.open(C.INTERIM / f"dem_5m_{REGION}.tif") as d:
        tr5, crs = d.transform, d.crs
    u5, _ = unit_raster_5m(UNIT_A, shape)
    huc = huc_polygons().reset_index()
    huc_r = rasterize(((g, i + 1) for i, g in enumerate(huc.geometry)), out_shape=shape, transform=tr5, fill=0,
                      dtype=np.uint16)
    code = {i + 1: h for i, h in enumerate(huc["huc12"])}
    paths = {k: C.INTERIM / f"terrain_{REGION}" / f"{k}.tif" for k in TERRAIN_LAYERS}
    paths |= {k: C.INTERIM / f"hydro_{REGION}" / f"{k}.tif" for k in HYDRO_LAYERS}
    paths |= {k: C.INTERIM / f"stack_{REGION}" / f"{k}.tif" for k in STACK_FLOAT + STACK_INT}
    srcs = {k: rasterio.open(p) for k, p in paths.items()}
    out_dir = C.INTERIM / f"scores_{REGION}"
    out_dir.mkdir(parents=True, exist_ok=True)
    prof = {"driver": "GTiff", "count": 1, "dtype": "float32", "nodata": np.nan, "crs": crs, "transform": tr5,
            "height": shape[0], "width": shape[1], "compress": "deflate", "predictor": 3, "tiled": True,
            "blockxsize": 256, "blockysize": 256}
    sums = {k: np.zeros(n_units) for k in models}
    den = np.zeros(n_units)
    dsts = {k: rasterio.open(out_dir / f"oof_{k}_5m.tif", "w", **prof) for k in models}
    try:
        for r0 in range(0, shape[0], WINDOW_ROWS):
            nr = min(WINDOW_ROWS, shape[0] - r0)
            win = Window(0, r0, shape[1], nr)
            d, h, hc, uu = dom[r0:r0 + nr], hill[r0:r0 + nr], huc_r[r0:r0 + nr], u5[r0:r0 + nr]
            has = np.isin(hc, [c for c, g in code.items() if g in next(iter(models.values()))])
            cnt = d & (~h | has)
            den += np.bincount(uu[cnt], minlength=n_units)
            sel = d & h & has
            if not sel.any():
                for k in models:
                    dsts[k].write(np.full((nr, shape[1]), np.nan, np.float32), 1, window=win)
                continue
            df = pd.DataFrame({k: s.read(1, window=win)[sel] for k, s in srcs.items()})
            df["rain_mm"] = rain_ref
            hs = hc[sel]
            us = uu[sel]
            X = {"lr": pixel_matrix(df), "gbm": pixel_gbm_matrix(df)}
            for k, by_huc in models.items():
                score = np.full(sel.sum(), np.nan)
                for c in np.unique(hs):
                    m = hs == c
                    score[m] = by_huc[code[int(c)]].linear(X[k][m])
                sums[k] += np.bincount(us, weights=np.exp(score), minlength=n_units)
                tile = np.full((nr, shape[1]), np.nan, np.float32)
                tile[sel] = score
                dsts[k].write(tile, 1, window=win)
    finally:
        for s in list(srcs.values()) + list(dsts.values()):
            s.close()
    with np.errstate(divide="ignore", invalid="ignore"):
        agg = {k: np.where(den > 0, np.log(v / np.maximum(den, 1)), np.nan) for k, v in sums.items()}
    return agg


# ------------------------------------------------------------------------------------------------- audit
def recalibrated_residual(score, y, rain):
    """y minus a 1-D logistic recalibration of the score (+ rainfall-bin intercepts): calibrates any score."""
    rb = pd.get_dummies(rain_bin(rain)).to_numpy(np.float64)
    X = np.column_stack([score, rb])
    m = LogisticRegression(C=1e6, max_iter=5000).fit(X, y)
    return y - m.predict_proba(X)[:, 1]


def artefact_audit(u: pd.DataFrame, score_cols: list[str]) -> dict:
    """Do out-of-fold residuals follow things that should not matter (excluded predictors, mapping effort)?"""
    pts = gpd.GeoSeries(gpd.points_from_xy(u["cx"], u["cy"]), crs=C.CRS)
    rd = roads()
    d_road = gpd.GeoDataFrame(geometry=pts).sjoin_nearest(rd[["geometry"]], distance_col="d").groupby(level=0)["d"].first()
    border = counties().union_all().boundary
    d_county = pts.distance(border)
    with rasterio.open(C.INTERIM / f"labels_{REGION}" / "density_100m.tif") as s:
        dens = np.array([v[0] for v in s.sample(zip(u["cx"], u["cy"]))])
    covs = {"distance_to_road_m": d_road.reindex(range(len(u))).to_numpy(), "distance_to_county_line_m": d_county.to_numpy(),
            "training_data_density": dens}
    out = {}
    y = u["label"].to_numpy()
    rain = u["rain_mm_mean"].to_numpy()
    for sc in score_cols:
        res = recalibrated_residual(u[sc].to_numpy(), y, rain)
        out[sc] = {}
        for k, v in covs.items():
            q = pd.qcut(v, 5, labels=False, duplicates="drop")
            oe = [float(y[q == i].sum() / (y[q == i] - res[q == i]).sum()) for i in range(int(q.max()) + 1)]
            out[sc][k] = {"spearman_residual": float(spearmanr(res, v)[0]), "observed_over_expected_by_quintile": oe}
    return out


def importance(cv: dict, y, rain, huc) -> dict:
    base_s = Ranked(cv["ref"], y, rain_bin(rain)).stratified_auc()
    base_h = Ranked(cv["ref"], y, huc).stratified_auc()
    return {k: {"drop_auc_rain_stratified": base_s - Ranked(v, y, rain_bin(rain)).stratified_auc(),
                "drop_auc_within_huc": base_h - Ranked(v, y, huc).stratified_auc()} for k, v in cv["perm"].items()}


def area_percentile(score, area) -> np.ndarray:
    """Share of area ranked at or above each unit (0-1]; the threshold slider's field."""
    o = np.argsort(-score, kind="stable")
    cum = np.cumsum(area[o]) / area.sum()
    out = np.empty(len(score))
    out[o] = cum
    return out


# ------------------------------------------------------------------------------------------------- run
def cached(name: str, fn):
    """Expensive stage results are pickled; LANDSLIDE_REUSE=1 reloads them (debugging the later stages only)."""
    p = C.INTERIM / f"scores_{REGION}" / f"m5_{name}.pkl"
    if os.environ.get("LANDSLIDE_REUSE") == "1" and p.exists():
        return pickle.loads(p.read_bytes())
    v = fn()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(pickle.dumps(v))
    return v


def run() -> dict:
    t0 = time.time()
    lab = C.INTERIM / f"labels_{REGION}"
    rain_ref = float(np.median(pd.read_parquet(lab / "domain_sample.parquet", columns=["rain_mm"])["rain_mm"]))
    polys = huc_polygons().geometry
    res: dict = {"rain_reference_mm": rain_ref, "grids": {"units": GRID_UNITS, "pixels": GRID_PIXELS},
                 "gbm_fixed": {k: v for k, v in GBM_FIXED.items()}, "inner_folds": INNER_FOLDS}

    # ---- slope units: (a) LR, (b) GBM
    u = load_units()
    X = u[UNIT_FEATURES].to_numpy(np.float64)
    y = u["label"].to_numpy()
    huc = u["huc12"].to_numpy()
    xy = u[["cx", "cy"]].to_numpy()
    rain = u["rain_mm_mean"].to_numpy()
    area = u["domain_km2"].to_numpy()
    hits = u["n_sources"].to_numpy(np.float64)
    area_ref = float(np.exp(np.median(u["log_domain_km2"])))
    uref = {"rain_mm_mean": rain_ref, "log_domain_km2": np.log(area_ref)}
    perm_u = cols_of(UNIT_GROUPS, UNIT_FEATURES)
    cv_a = cached("unit_lr", lambda: cross_val(X, y, huc, xy, polys, UNIT_FEATURES, UNIT_PROTECTED, uref, perm=perm_u))
    cv_b = cached("unit_gbm", lambda: cross_val(
        X, y, huc, xy, polys, UNIT_FEATURES, UNIT_PROTECTED, uref, perm=perm_u,
        make_model=lambda: GBM(UNIT_FEATURES, GRID_UNITS, INNER_FOLDS["units"], uref, rain="rain_mm_mean")))
    print(f"units done {time.time() - t0:.0f}s", flush=True)

    # ---- 5 m cells: LR and GBM (same folds, same 1:10 thinning)
    pos = pd.read_parquet(lab / "positives.parquet")
    neg = pd.read_parquet(lab / "negatives.parquet")
    pos, neg = (t[(t["hillslope"] == 1) & t["huc12"].notna()] for t in (pos, neg))
    df = pd.concat([pos, neg], ignore_index=True)
    rep = json.loads((lab / "report.json").read_text())
    neg_w = rep["domain"]["eligible_negative_hillslope_cells"] / len(neg)
    yp, hp, xyp, rp = df["label"].to_numpy(), df["huc12"].to_numpy(), df[["x", "y"]].to_numpy(), df["rain_mm"].to_numpy()
    wp = np.where(yp == 1, 1.0, neg_w)

    def thin(idx, rng):
        p_, n_ = idx[yp[idx] == 1], idx[yp[idx] == 0]
        return np.r_[p_, rng.choice(n_, size=min(len(n_), NEG_RATIO * len(p_)), replace=False)]

    pref = {"rain_mm": rain_ref}
    cv_pl = cached("cell_lr", lambda: cross_val(pixel_matrix(df), yp, hp, xyp, polys, PIXEL_NAMES, PIXEL_PROTECTED,
                                                pref, subsample=thin, perm=cols_of(PIXEL_GROUPS, PIXEL_NAMES)))
    cv_pg = cached("cell_gbm", lambda: cross_val(
        pixel_gbm_matrix(df), yp, hp, xyp, polys, PIXEL_GBM_NAMES, PIXEL_PROTECTED, pref, subsample=thin,
        perm=cols_of(PIXEL_GROUPS, PIXEL_GBM_NAMES),
        make_model=lambda: GBM(PIXEL_GBM_NAMES, GRID_PIXELS, INNER_FOLDS["pixels"], pref, categorical=PIXEL_GBM_CAT)))
    print(f"pixels done {time.time() - t0:.0f}s", flush=True)
    zero = np.zeros(len(yp))
    pe = {"lr": evaluate(cv_pl["ref"], yp, rp, hp, yp.astype(float), zero, w=wp),
          "gbm": evaluate(cv_pg["ref"], yp, rp, hp, yp.astype(float), zero, w=wp),
          "slope": evaluate(df["slope_deg"].to_numpy(), yp, rp, hp, yp.astype(float), zero, w=wp)}
    res["pixels"] = {
        "scores": {k: {m: v for m, v in strip(e).items() if not m.startswith("capture")} for k, e in pe.items()},
        "C1_delta_gbm_minus_lr": {k: paired_delta(pe["gbm"], pe["lr"], k) for k in ("auc_rain_stratified", "auc_within_huc")},
        "delta_gbm_minus_slope": {k: paired_delta(pe["gbm"], pe["slope"], k) for k in ("auc_rain_stratified", "auc_within_huc")},
        "importance_lr": importance(cv_pl, yp, rp, hp), "importance_gbm": importance(cv_pg, yp, rp, hp),
        "chosen_params": pd.Series([repr(f["params"]) for f in cv_pg["folds"]]).value_counts().to_dict(),
    }

    # ---- 5 m -> units
    with rasterio.open(C.INTERIM / f"units_{REGION}" / f"units_{UNIT_A}.tif") as s:
        n_units = int(s.read(1).max()) + 1
    agg = cached("aggregated", lambda: score_rasters({"lr": cv_pl["models"], "gbm": cv_pg["models"]}, rain_ref, n_units))
    print(f"rasters done {time.time() - t0:.0f}s", flush=True)
    u["a_unit_lr"], u["b_unit_gbm"] = cv_a["ref"], cv_b["ref"]
    u["c_cell_lr_agg"], u["d_cell_gbm_agg"] = agg["lr"][u["unit"]], agg["gbm"][u["unit"]]
    for c in ("c_cell_lr_agg", "d_cell_gbm_agg"):  # units with no scored hillslope cell: lowest intensity
        u[c] = u[c].fillna(np.nanmin(u[c]) - 1).replace(-np.inf, np.nanmin(u[c][np.isfinite(u[c])]) - 1)
    u["slope_p90"] = u["slope_deg_p90"]
    cand = ["a_unit_lr", "b_unit_gbm", "c_cell_lr_agg", "d_cell_gbm_agg", "slope_p90"]
    ue = {c: evaluate(u[c].to_numpy(), y, rain, huc, hits, area) for c in cand}
    res["units"] = {"n_units": len(u), "scores": {c: strip(e) for c, e in ue.items()},
                    "C1_delta_gbm_minus_lr": {k: paired_delta(ue["b_unit_gbm"], ue["a_unit_lr"], k)
                                              for k in ("auc_rain_stratified", "auc_within_huc")},
                    "C2_delta_vs_slope": {c: {k: paired_delta(ue[c], ue["slope_p90"], k)
                                              for k in ("auc_rain_stratified", "auc_within_huc")} for c in cand[:4]},
                    "importance_unit_lr": importance(cv_a, y, rain, huc),
                    "importance_unit_gbm": importance(cv_b, y, rain, huc),
                    "chosen_params": pd.Series([repr(f["params"]) for f in cv_b["folds"]]).value_counts().to_dict(),
                    "per_huc": {c: per_huc(u[c].to_numpy(), y, huc, hits, area).to_dict("records") for c in cand},
                    "spearman_between_candidates": pd.DataFrame({c: u[c] for c in cand}).corr("spearman").round(3).to_dict()}
    pb = 1 / (1 + np.exp(-cv_b["act"]))
    res["units"]["calibration_diagnostic_unit_gbm"] = {"brier": brier(pb, y), "brier_climatology": brier(np.full(len(y), y.mean()), y),
                                                       "reliability": reliability(pb, y)}

    # ---- criteria and product rule
    c1u = res["units"]["C1_delta_gbm_minus_lr"]["auc_rain_stratified"]
    c1p = res["pixels"]["C1_delta_gbm_minus_lr"]["auc_rain_stratified"]
    passing = [c for c in cand[:4] if res["units"]["C2_delta_vs_slope"][c]["auc_rain_stratified"]["ci95"][0] > 0
               and res["units"]["C2_delta_vs_slope"][c]["auc_within_huc"]["value"] > 0]
    product = max(passing, key=lambda c: ue[c]["auc_within_huc"]["value"]) if passing else None
    res["criteria"] = {"C1_units": c1u["ci95"][0] > 0, "C1_pixels": c1p["ci95"][0] > 0, "C2_passing": passing,
                       "product": product, "stop_for_owner_decision": product is None}

    # ---- artefact audit, error classes and outputs
    res["artefact_audit"] = artefact_audit(u, [c for c in cand[:4]])
    keep = ["unit", "huc12", "county", "label", "n_sources", "domain_km2", "rain_mm_mean"] + cand
    out = u[keep].copy()
    if product:
        out["product_area_pct"] = area_percentile(u[product].to_numpy(), area)
        top10 = out["product_area_pct"] <= 0.10
        out["class"] = np.select([top10 & (y == 1), top10 & (y == 0), (out["product_area_pct"] > 0.30) & (y == 1)],
                                 ["mapped, top 10 %", "top 10 %, no mapped initiation", "mapped, below top 30 %"],
                                 "other")
        res["error_classes"] = out["class"].value_counts().to_dict()
    out.to_parquet(C.OUT / "oof_units_m5.parquet", index=False)
    res["runtime_s"] = round(time.time() - t0)
    (C.VALIDATION / "m5_advanced.json").write_text(json.dumps(strip(res), indent=1, default=float))
    from .report_m5 import write
    write()
    print(json.dumps(res["criteria"], indent=1), flush=True)
    return res


if __name__ == "__main__":
    run()
