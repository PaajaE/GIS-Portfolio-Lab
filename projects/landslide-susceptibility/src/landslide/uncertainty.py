"""M6 items 1-2: prediction uncertainty and area of applicability of the 5 m LR (METHOD §Validation, fixed 2026-10-10).

1. Ensemble: 30 refits, each on a HUC-12 block-bootstrap resample of the training cells (whole watersheds drawn
   with replacement, multiplicity as sample weight, then the usual 1:10 thinning). Every hillslope domain cell gets
   its top-k % class under each refit (class boundaries from the refit's scores on the hillslope part of the
   uniform domain sample); the layer is the p10 and p90 of that class across refits -> ens_rank_p10/p90.tif.
2. Area of applicability (Meyer & Pebesma 2021): dissimilarity index DI = distance to the nearest training cell in
   the predictor space (standardized, weighted by |standardized coefficient| of the final model; rainfall is held
   at the reference and left out) divided by the mean distance between training cells. Threshold = upper whisker
   (Q3 + 1.5 IQR) of the training cells' DI to training cells of *other* HUC-12s. Mapped on a 50 m lattice
   (every 10th cell); training set subsampled to 20,000 cells for the nearest-neighbour search.
Writes validation/m6_uncertainty.json and data/interim/scores_aoi/{ens_rank_p10,ens_rank_p90,aoa_di_50m,aoa_50m}.tif.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import rasterio
from scipy.spatial import cKDTree

from . import config as C
from .baseline import LR, NEG_RATIO, PIXEL_NAMES, PIXEL_PROTECTED, pixel_matrix
from .labels import HYDRO_LAYERS, REGION, STACK_FLOAT, STACK_INT, read
from .product import SCORES, fit_final, float_profile, predictor_windows, rain_reference, training_cells
from .terrain import LAYERS as TERRAIN_LAYERS

N_REFITS = 30
AOA_TRAIN = 20_000
AOA_STEP = 10  # 10 x 5 m = 50 m lattice


def bootstrap_models(df: pd.DataFrame) -> list[LR]:
    X, y, huc = pixel_matrix(df), df["label"].to_numpy(), df["huc12"].to_numpy()
    ug, gi = np.unique(huc, return_inverse=True)
    rng = np.random.default_rng(C.SEED + 30)
    models = []
    for _ in range(N_REFITS):
        mult = np.bincount(rng.integers(0, len(ug), len(ug)), minlength=len(ug))[gi]
        rows = np.flatnonzero(mult > 0)
        p, n = rows[y[rows] == 1], rows[y[rows] == 0]
        n = rng.choice(n, size=min(len(n), NEG_RATIO * len(p)), replace=False)
        idx = np.r_[p, n]
        models.append(LR(PIXEL_NAMES, PIXEL_PROTECTED).fit(X[idx], y[idx], mult[idx].astype(float)))
    return models


def class_edges(model: LR, Xs: np.ndarray) -> np.ndarray:
    """Descending score quantiles of the hillslope domain sample: class r = number of edges above the score + 1."""
    s = np.sort(model.linear(Xs))[::-1]
    return s[np.ceil(np.arange(1, 100) / 100 * len(s)).astype(int) - 1]  # score at the 1 %, 2 %, ... 99 % positions


def to_class(score: np.ndarray, edges_desc: np.ndarray) -> np.ndarray:
    # number of edges strictly greater than the score -> 0..99 -> class 1..100
    return (np.searchsorted(-edges_desc, -score, side="left") + 1).astype(np.uint8)


def ensemble(models, rain_ref) -> dict:
    lab = C.INTERIM / f"labels_{REGION}"
    ds = pd.read_parquet(lab / "domain_sample.parquet")
    ds = ds[ds["hillslope"] == 1].assign(rain_mm=rain_ref)
    Xs = pixel_matrix(ds)
    edges = [class_edges(m, Xs) for m in models]
    prof = float_profile() | {"dtype": "uint8", "nodata": 0, "predictor": 1}
    hist = np.zeros((101, 101), np.int64)  # final-class x p90-class, for the stability summary
    with rasterio.open(SCORES / "rank_final_lr.tif") as fr, \
            rasterio.open(SCORES / "ens_rank_p10.tif", "w", **prof) as d10, \
            rasterio.open(SCORES / "ens_rank_p90.tif", "w", **prof) as d90:
        for win, sel, df in predictor_windows(rain_ref):
            t10 = np.zeros(sel.shape, np.uint8)
            t90 = np.zeros(sel.shape, np.uint8)
            if sel.any():
                X = pixel_matrix(df)
                cls = np.stack([to_class(m.linear(X), e) for m, e in zip(models, edges)])
                lo, hi = np.percentile(cls, [10, 90], axis=0, method="nearest")
                t10[sel], t90[sel] = lo, hi  # p10 of the class = the better (smaller) end
                fin = fr.read(1, window=win)[sel]
                np.add.at(hist, (fin, hi), 1)
            d10.write(t10, 1, window=win)
            d90.write(t90, 1, window=win)
    fin_tot = hist.sum(1)
    out = {"refits": len(models)}
    for k in (5, 10, 20):
        in_k = hist[1:k + 1].sum()
        out[f"final_top{k}_stays_in_top{k}_in_90pct_of_refits"] = float(hist[1:k + 1, 1:k + 1].sum() / in_k)
        out[f"final_top{k}_p90_class_beyond_{2 * k}"] = float(hist[1:k + 1, 2 * k + 1:].sum() / in_k)
    out["cells"] = int(fin_tot[1:].sum())
    return out


def aoa(final: LR, rain_ref) -> dict:
    df = training_cells()
    rng = np.random.default_rng(C.SEED + 31)
    idx = rng.choice(len(df), size=min(AOA_TRAIN, len(df)), replace=False)
    tr = df.iloc[idx].reset_index(drop=True)
    keep = [i for i in final.keep if PIXEL_NAMES[i] != "rain_mm"]
    wts = np.abs(final.m.coef_[0][[final.keep.index(i) for i in keep]])

    def space(frame):
        Z = (pixel_matrix(frame) - final.mu) / final.sd
        return Z[:, keep] * wts

    T = space(tr)
    # mean distance between training cells (random pairs)
    a, b = rng.integers(0, len(T), 200_000), rng.integers(0, len(T), 200_000)
    dbar = float(np.mean(np.linalg.norm(T[a] - T[b], axis=1)))
    # cross-validated DI of training cells: nearest training cell in another HUC-12
    h = tr["huc12"].to_numpy()
    di_tr = np.empty(len(T))
    for g in np.unique(h):
        m = h == g
        di_tr[m] = cKDTree(T[~m]).query(T[m], k=1, workers=-1)[0] / dbar
    q1, q3 = np.percentile(di_tr, [25, 75])
    thr = float(min(q3 + 1.5 * (q3 - q1), di_tr.max()))
    tree = cKDTree(T)
    # 50 m lattice over the hillslope domain
    lab = C.INTERIM / f"labels_{REGION}"
    mask = read(lab / "domain.tif").astype(bool) & read(lab / "hillslope.tif").astype(bool)
    sub = mask[::AOA_STEP, ::AOA_STEP]
    rr, cc = np.nonzero(sub)
    rr5, cc5 = rr * AOA_STEP, cc * AOA_STEP
    frame = {}
    for group, names in ((f"terrain_{REGION}", TERRAIN_LAYERS), (f"hydro_{REGION}", HYDRO_LAYERS),
                         (f"stack_{REGION}", STACK_FLOAT + STACK_INT)):
        for k in names:
            frame[k] = read(C.INTERIM / group / f"{k}.tif")[rr5, cc5]
    frame = pd.DataFrame(frame).assign(rain_mm=rain_ref)
    di = tree.query(space(frame), k=1, workers=-1)[0] / dbar
    with rasterio.open(C.INTERIM / f"dem_5m_{REGION}.tif") as d:
        tr50 = d.transform * rasterio.Affine.scale(AOA_STEP)
        crs = d.crs
    shp = sub.shape
    di_r = np.full(shp, np.nan, np.float32)
    di_r[rr, cc] = di
    flag = np.zeros(shp, np.uint8)
    flag[rr, cc] = np.where(di <= thr, 1, 2)  # 1 inside the area of applicability, 2 outside
    base = {"driver": "GTiff", "count": 1, "crs": crs, "transform": tr50, "height": shp[0], "width": shp[1],
            "compress": "deflate", "tiled": True}
    with rasterio.open(SCORES / "aoa_di_50m.tif", "w", **base, dtype="float32", nodata=np.nan) as dst:
        dst.write(di_r, 1)
    with rasterio.open(SCORES / "aoa_50m.tif", "w", **base, dtype="uint8", nodata=0) as dst:
        dst.write(flag, 1)
    return {"threshold_di": thr, "mean_training_distance": dbar, "training_cells_used": len(T),
            "predictors": [PIXEL_NAMES[i] for i in keep],
            "lattice_cells": int(len(di)), "share_outside_aoa": float((di > thr).mean()),
            "training_di_quartiles": [float(q1), float(np.median(di_tr)), float(q3)],
            "domain_di_p50_p90_p99": [float(x) for x in np.percentile(di, [50, 90, 99])]}


def run() -> dict:
    rain_ref = rain_reference()
    df = training_cells()
    final = fit_final(df)
    res = {"ensemble": ensemble(bootstrap_models(df), rain_ref)}
    print(res, flush=True)
    res["area_of_applicability"] = aoa(final, rain_ref)
    print(res["area_of_applicability"], flush=True)
    (C.VALIDATION / "m6_uncertainty.json").write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    run()
