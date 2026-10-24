"""M6 item 5: Watauga County, indicative only (METHOD §Validation, fixed 2026-10-10; never in the headline).

Test positives: Helene outlines with SlopeModifier "None Apparent" or not assessed, existence and location
confidence High/Moderate, more than 30 m from TIGER ∪ OSM vehicle roads. Initiation proxy for every outline (1940
and Helene): its cells in the top 20 % by elevation (a polygon without a cell centre uses its representative point).
Domain as in the AOI: county, MRMS 72 h >= 250 mm, every predictor valid, no water; hillslopes with the AOI slope
threshold. Negatives: domain hillslope cells outside every mapped feature (+30 m) and road corridors (+15 m),
seeded sample, split in two halves (training / test) for the temporal model.

(i) Transfer: the final AOI 5 m LR applied unchanged.
(ii) Temporal: a 5 m LR trained on the 1940 outlines' initiation proxies with continuous predictors smoothed to
     15 m (3 x 3 mean); recurrence baseline = distance to the nearest 1940 outline (closer = higher).
Reported: AUC of positives vs test negatives (pooled; rainfall bins as a check) with 95 % intervals from a
bootstrap over outlines (positive clusters) and negative cells. Writes validation/m6_watauga.json.
Note: 1,209 of 1,218 1940 outlines have location confidence "Low"; they are used as pre-registered.
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask, rasterize
from scipy import ndimage

from . import config as C
from .baseline import NEG_RATIO, PIXEL_CONT, PIXEL_NAMES, PIXEL_PROTECTED, LR, pixel_matrix, rain_bin
from .labels import (EXCLUSION_BUFFER_M, HYDRO_LAYERS, OSM_NON_VEHICLE, ROAD_BUFFER_M, ROAD_EXCLUDE_MTFCC,
                     STACK_FLOAT, STACK_INT, burn, inventory)
from .metrics import Ranked, block_bootstrap, ci
from .product import fit_final, rain_reference, training_cells
from .terrain import LAYERS as TERRAIN_LAYERS

R = "watauga"
N_NEG = 100_000
N_BOOT = 2000
TOP_SHARE = 0.20


def layer_paths() -> dict:
    p = {k: C.INTERIM / f"terrain_{R}" / f"{k}.tif" for k in TERRAIN_LAYERS}
    p |= {k: C.INTERIM / f"hydro_{R}" / f"{k}.tif" for k in HYDRO_LAYERS}
    p |= {k: C.INTERIM / f"stack_{R}" / f"{k}.tif" for k in STACK_FLOAT + STACK_INT}
    return p


def roads() -> gpd.GeoDataFrame:
    fips = C.REGIONS[R]["Watauga County"]
    t = gpd.read_file(C.RAW / f"tl_2024_{C.STATE_FIPS}{fips}_roads.zip").to_crs(C.CRS)
    t = t[t["MTFCC"].str.startswith("S1") & ~t["MTFCC"].isin(ROAD_EXCLUDE_MTFCC)]
    o = gpd.read_parquet(C.RAW / "osm_roads_watauga.parquet").to_crs(C.CRS)
    o = o[~o["highway"].isin(OSM_NON_VEHICLE)]
    return pd.concat([t[["geometry"]], o[["geometry"]]], ignore_index=True)


def top_cells(polys: gpd.GeoSeries, dem: np.ndarray, tr, valid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Flat indices of the top-20 % elevation cells of every polygon, and the polygon number of each cell."""
    lab = rasterize(((g, i + 1) for i, g in enumerate(polys)), out_shape=dem.shape, transform=tr, fill=0,
                    dtype=np.int32)
    idx, owner = [], []
    flat_lab = lab.ravel()
    cells = np.flatnonzero(flat_lab)
    order = np.argsort(flat_lab[cells], kind="stable")
    cells = cells[order]
    ids = flat_lab[cells]
    starts = np.r_[0, np.flatnonzero(np.diff(ids)) + 1, len(ids)]
    seen = set()
    for a, b in zip(starts[:-1], starts[1:]):
        c = cells[a:b]
        z = dem.ravel()[c]
        n = max(1, int(np.ceil(TOP_SHARE * len(c))))
        top = c[np.argsort(-z, kind="stable")[:n]]
        idx.append(top)
        owner.append(np.full(len(top), ids[a]))
        seen.add(int(ids[a]))
    inv_tr = ~tr
    for i, g in enumerate(polys):  # polygons without a cell centre: representative point
        if i + 1 in seen:
            continue
        p = g.representative_point()
        col, row = inv_tr * (p.x, p.y)
        r, c = int(np.floor(row)), int(np.floor(col))
        if 0 <= r < dem.shape[0] and 0 <= c < dem.shape[1]:
            idx.append(np.array([r * dem.shape[1] + c]))
            owner.append(np.array([i + 1]))
    idx, owner = np.concatenate(idx), np.concatenate(owner)
    ok = valid.ravel()[idx]
    return idx[ok], owner[ok]


def smoothed(a: np.ndarray, nodata: float) -> np.ndarray:
    v = np.where(a == nodata, 0, a).astype(np.float64)
    m = (a != nodata).astype(np.float64)
    s = ndimage.uniform_filter(v, 3, mode="nearest")
    n = ndimage.uniform_filter(m, 3, mode="nearest")
    return np.where(n > 0, s / np.maximum(n, 1e-9), nodata)


def frame(idx: np.ndarray, shape, smooth: bool) -> pd.DataFrame:
    out = {}
    for k, p in layer_paths().items():
        with rasterio.open(p) as s:
            a = s.read(1)
            nd = s.nodata
        if smooth and k in PIXEL_CONT and k not in ("bedrock_recorded",):
            a = smoothed(a, nd if nd is not None else C.OUT_NODATA)
        out[k] = a.ravel()[idx]
    return pd.DataFrame(out)


def auc_ci(score: np.ndarray, y: np.ndarray, groups: np.ndarray, rain: np.ndarray) -> dict:
    r = Ranked(score, y)
    rb = Ranked(score, y, rain_bin(rain))
    reps = block_bootstrap(groups, lambda w: np.array([r.auc(w), rb.stratified_auc(w)]), N_BOOT, C.SEED)
    lo_hi = ci(reps)
    return {"auc": r.auc(), "ci95": lo_hi[0].tolist(), "auc_rain_stratified": rb.stratified_auc(),
            "ci95_rain_stratified": lo_hi[1].tolist(), "_reps": reps}


def build() -> dict:
    """Domain, test positives (Helene), 1940 proxies and negatives for Watauga."""
    with rasterio.open(C.INTERIM / f"dem_5m_{R}.tif") as d:
        dem, tr, shape = d.read(1), d.transform, d.shape
    cty = gpd.read_parquet(C.RAW / "counties.parquet").to_crs(C.CRS)
    w = cty[cty["NAME"].isin(C.REGIONS[R])].union_all()
    in_cty = ~geometry_mask([w], shape, tr)
    rain = rasterio.open(C.INTERIM / f"stack_{R}" / "rain_mm.tif").read(1)
    valid = in_cty & (rain != C.OUT_NODATA) & (rain >= C.TRIGGER_MM)
    # same validity rule as the AOI domain (labels.run): terrain, hydrology, canopy, bedrock depth and flag
    for k in TERRAIN_LAYERS + HYDRO_LAYERS + ("canopy", "bedrock_cm"):
        valid &= rasterio.open(layer_paths()[k]).read(1) != C.OUT_NODATA
    valid &= rasterio.open(layer_paths()["bedrock_recorded"]).read(1) != 255
    lc = rasterio.open(C.INTERIM / f"stack_{R}" / "lc_group.tif").read(1)
    valid &= lc != 6
    rep_aoi = json.loads((C.INTERIM / "labels_aoi" / "report.json").read_text())
    slope_thr = rep_aoi["domain"]["slope_p1_of_positive_cells_deg"]
    slope = rasterio.open(C.INTERIM / f"terrain_{R}" / "slope_deg.tif").read(1)
    hill = valid & (slope >= slope_thr)

    inv = inventory()
    inv = inv[inv.geometry.representative_point().within(w)]
    rd = roads()
    hel = inv[inv["event"].eq("helene") & (inv["SlopeModifier"].isna() | inv["SlopeModifier"].eq("None Apparent"))
              & inv["exist_conf"].isin(["High", "Moderate"]) & inv["loc_conf"].isin(["High", "Moderate"])]
    d_road = gpd.GeoDataFrame(geometry=hel.geometry).sjoin_nearest(rd, distance_col="d").groupby(level=0)["d"].min()
    hel_test = hel[d_road.reindex(hel.index).to_numpy() > 30]
    old = inv[inv["event"].eq("1940-08")]
    pos_test, own_test = top_cells(hel_test.geometry.reset_index(drop=True), dem, tr, hill)
    pos_old, own_old = top_cells(old.geometry.reset_index(drop=True), dem, tr, hill)

    excl = burn(inv.geometry.buffer(EXCLUSION_BUFFER_M), tr, shape) | burn(rd.geometry.buffer(ROAD_BUFFER_M), tr, shape)
    elig = np.flatnonzero((hill & ~excl).ravel())
    rng = np.random.default_rng(C.SEED + 50)
    neg = rng.choice(elig, size=min(N_NEG, len(elig)), replace=False)
    neg_train, neg_test = neg[: len(neg) // 2], neg[len(neg) // 2:]
    rain_flat = rain.ravel()

    info = {"domain_km2": float(valid.sum() * 25 / 1e6), "hillslope_km2": float(hill.sum() * 25 / 1e6),
           "slope_threshold_deg": slope_thr,
           "helene_outlines_natural_or_unassessed_conf_hm": int(len(hel)), "helene_test_outlines": int(len(hel_test)),
           "helene_test_outlines_with_cells": int(len(np.unique(own_test))), "helene_test_cells": int(len(pos_test)),
           "outlines_1940": int(len(old)), "outlines_1940_with_cells": int(len(np.unique(own_old))),
           "cells_1940": int(len(pos_old)),
           "outlines_1940_location_confidence": old["loc_conf"].value_counts().to_dict(),
           "negatives_test": int(len(neg_test)), "rain_mm_test_positives_median": float(np.median(rain_flat[pos_test]))}
    return {"info": info, "shape": shape, "tr": tr, "rain": rain.ravel(), "pos_test": pos_test, "own_test": own_test,
            "pos_old": pos_old, "neg_train": neg_train, "neg_test": neg_test, "old": old, "rng": rng}


def run() -> dict:
    B = build()
    res = dict(B["info"])
    shape, tr, rain_flat, rng, old = B["shape"], B["tr"], B["rain"], B["rng"], B["old"]
    pos_test, own_test, pos_old = B["pos_test"], B["own_test"], B["pos_old"]
    neg_train, neg_test = B["neg_train"], B["neg_test"]

    test_idx = np.r_[pos_test, neg_test]
    y = np.r_[np.ones(len(pos_test)), np.zeros(len(neg_test))].astype(int)
    groups = np.r_[own_test.astype(np.int64), -1 - np.arange(len(neg_test))]  # outlines = clusters; negatives single
    rt = rain_flat[test_idx]

    # (i) transfer of the final AOI model
    rain_ref = rain_reference()
    fin = fit_final(training_cells())
    ft = frame(test_idx, shape, smooth=False).assign(rain_mm=rain_ref)
    s_transfer = fin.linear(pixel_matrix(ft))
    s_slope = ft["slope_deg"].to_numpy()
    res["transfer_aoi_model"] = auc_ci(s_transfer, y, groups, rt)
    res["slope_alone"] = auc_ci(s_slope, y, groups, rt)

    # (ii) temporal: train on 1940 proxies (smoothed predictors), test on Helene
    tr_idx = np.r_[pos_old, neg_train]
    ytr = np.r_[np.ones(len(pos_old)), np.zeros(len(neg_train))].astype(int)
    keep = np.r_[np.arange(len(pos_old)),
                 len(pos_old) + rng.choice(len(neg_train), size=min(len(neg_train), NEG_RATIO * len(pos_old)),
                                           replace=False)]
    fr_tr = frame(tr_idx[keep], shape, smooth=True).assign(rain_mm=rain_flat[tr_idx[keep]])
    m40 = LR(PIXEL_NAMES, PIXEL_PROTECTED).fit(pixel_matrix(fr_tr), ytr[keep])
    fs = frame(test_idx, shape, smooth=True).assign(rain_mm=rain_ref)
    s_temporal = m40.linear(pixel_matrix(fs))
    res["temporal_1940_model"] = auc_ci(s_temporal, y, groups, rt)
    res["temporal_1940_model"]["coefficients"] = m40.coefs()
    # recurrence baseline: distance to the nearest 1940 outline (negative = closer ranks higher)
    r_, c_ = np.divmod(test_idx, shape[1])
    xs, ys = rasterio.transform.xy(tr, r_, c_)
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(xs, ys), crs=C.CRS)
    d40 = pts.sjoin_nearest(gpd.GeoDataFrame(geometry=old.geometry.reset_index(drop=True)), distance_col="d") \
        .groupby(level=0)["d"].min().reindex(range(len(pts))).to_numpy()
    res["recurrence_baseline"] = auc_ci(-d40, y, groups, rt)
    for k in ("transfer_aoi_model", "temporal_1940_model"):
        for ref in ("slope_alone", "recurrence_baseline"):
            d = res[k]["_reps"][:, 0] - res[ref]["_reps"][:, 0]
            res[f"delta_{k}_minus_{ref}"] = {"value": res[k]["auc"] - res[ref]["auc"],
                                             "ci95": [float(x) for x in np.nanquantile(d, [0.025, 0.975])]}
    res["spearman_transfer_vs_temporal_scores"] = float(pd.Series(s_transfer).corr(pd.Series(s_temporal), "spearman"))
    out = {k: ({kk: vv for kk, vv in v.items() if kk != "_reps"} if isinstance(v, dict) else v) for k, v in res.items()}
    (C.VALIDATION / "m6_watauga.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps({k: out[k] for k in out if k.startswith(("transfer", "temporal", "slope", "recurrence", "delta"))},
                     indent=1, default=float)[:3000], flush=True)
    return out



def diagnostics() -> dict:
    """Post-hoc explanation of the transfer result (labelled as such; nothing here changes a model or a gate):
    single-predictor AUCs in Watauga vs the AOI, geology composition, and the transferred model without its
    geology terms."""
    B = build()
    shape = B["shape"]
    idx = np.r_[B["pos_test"], B["neg_test"]]
    y = np.r_[np.ones(len(B["pos_test"])), np.zeros(len(B["neg_test"]))].astype(int)
    fw = frame(idx, shape, smooth=False)
    aoi = training_cells()
    out = {"single_predictor_auc": {}}
    for k in ("slope_deg", "planc_15", "tpi_50", "relief_50", "hand", "dist_channel", "log_area", "eastness",
              "northness", "canopy"):
        out["single_predictor_auc"][k] = {"watauga": Ranked(fw[k].to_numpy(), y).auc(),
                                          "aoi": Ranked(aoi[k].to_numpy(), aoi["label"].to_numpy()).auc()}
    out["geology_share"] = {
        "watauga_test_positives": fw.loc[y == 1, "geology"].value_counts(normalize=True).round(3).to_dict(),
        "watauga_negatives": fw.loc[y == 0, "geology"].value_counts(normalize=True).round(3).to_dict(),
        "aoi_positives": aoi.loc[aoi["label"] == 1, "geology"].value_counts(normalize=True).round(3).to_dict()}
    ds = pd.read_parquet(C.INTERIM / "labels_aoi" / "domain_sample.parquet")
    ds = ds[ds["hillslope"] == 1]
    out["aoi_hillslope_by_geology"] = {
        str(int(g)): {"share": float(len(v) / len(ds)), "rain_mm_median": float(v["rain_mm"].median()),
                      "positive_cells": int(((aoi["label"] == 1) & (aoi["geology"] == g)).sum())}
        for g, v in ds.groupby("geology")}
    fin = fit_final(aoi)
    X = pixel_matrix(fw.assign(rain_mm=rain_reference()))
    geo = [i for i, n in enumerate(PIXEL_NAMES) if n.startswith("geology_")]
    Xg = X.copy()
    Xg[:, geo] = fin.mu[geo]  # geology terms at the AOI mean = their contribution removed
    out["transfer_auc"] = Ranked(fin.linear(X), y).auc()
    out["transfer_auc_without_geology_terms"] = Ranked(fin.linear(Xg), y).auc()
    (C.VALIDATION / "m6_watauga_diagnostics.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out, indent=1, default=float), flush=True)
    return out


if __name__ == "__main__":
    import sys
    diagnostics() if sys.argv[1:] == ["diagnostics"] else run()
