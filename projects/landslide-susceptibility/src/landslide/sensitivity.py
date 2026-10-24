"""M6 item 3: one-at-a-time sensitivity of the 5 m logistic regression (METHOD §Validation, fixed 2026-10-10).

Every variant uses the M4/M5 design (leave-one-HUC-12-out, 500 m buffer, score at the reference rainfall) unless
the variant changes exactly that. Reported: rainfall-stratified and within-watershed AUC, their difference from the
primary run, and the within-watershed AUC of slope alone on the same evaluation rows, so the conclusion "the 5 m
model ranks better than slope alone" is restated per variant (point Δ, as pre-registered). No gate, no tuning.
Writes validation/m6_sensitivity.json.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from scipy import ndimage

from . import config as C
from .aggregate import unit_raster_5m
from .baseline import (NEG_RATIO, PIXEL_NAMES, PIXEL_PROTECTED, cross_val, huc_polygons, pixel_matrix, rain_bin)
from .inventory import positive_mask
from .labels import REGION, counties, inventory, read
from .metrics import Ranked

SCORES = C.INTERIM / f"scores_{REGION}"


def load() -> tuple[pd.DataFrame, np.ndarray, float]:
    lab = C.INTERIM / f"labels_{REGION}"
    pos = pd.read_parquet(lab / "positives.parquet")
    neg = pd.read_parquet(lab / "negatives.parquet")
    pos, neg = (t[(t["hillslope"] == 1) & t["huc12"].notna()] for t in (pos, neg))
    df = pd.concat([pos, neg], ignore_index=True)
    rep = json.loads((lab / "report.json").read_text())
    w = np.where(df["label"].to_numpy() == 1, 1.0, rep["domain"]["eligible_negative_hillslope_cells"] / len(neg))
    rain_ref = float(np.median(pd.read_parquet(lab / "domain_sample.parquet", columns=["rain_mm"])["rain_mm"]))
    return df, w, rain_ref


def metrics(score, y, rain, huc, w, slope) -> dict:
    out = {"auc_rain_stratified": Ranked(score, y, rain_bin(rain)).stratified_auc(w),
           "auc_within_huc": Ranked(score, y, huc).stratified_auc(w),
           "slope_auc_within_huc": Ranked(slope, y, huc).stratified_auc(w),
           "positives": int(y.sum())}
    out["model_minus_slope_within_huc"] = out["auc_within_huc"] - out["slope_auc_within_huc"]
    return out


def run_cv(df, w, rain_ref, *, ratio=NEG_RATIO, groups=None, polys=None, buffer_m=500, names=PIXEL_NAMES,
           drop_rain=False):
    y = df["label"].to_numpy()
    X = pixel_matrix(df)
    nm, prot, ref = list(names), PIXEL_PROTECTED, {"rain_mm": rain_ref}
    if drop_rain:
        X, nm, prot, ref = X[:, :-1], nm[:-1], (), {}

    def thin(idx, rng):
        p_, n_ = idx[y[idx] == 1], idx[y[idx] == 0]
        return np.r_[p_, rng.choice(n_, size=min(len(n_), ratio * len(p_)), replace=False)]

    g = df["huc12"].to_numpy() if groups is None else groups
    cv = cross_val(X, y, g, df[["x", "y"]].to_numpy(), huc_polygons().geometry if polys is None else polys,
                   nm, prot, ref, subsample=thin, buffer_m=buffer_m)
    return cv["ref"]


def evaluate_df(score, df, w) -> dict:
    return metrics(score, df["label"].to_numpy(), df["rain_mm"].to_numpy(), df["huc12"].to_numpy(), w,
                   df["slope_deg"].to_numpy())


def polygon_area_raster() -> np.ndarray:
    inv, cty = inventory(), counties()
    p = inv[positive_mask(inv)]
    p = p[p.geometry.representative_point().within(cty.union_all())]
    with rasterio.open(C.INTERIM / f"dem_5m_{REGION}.tif") as d:
        return rasterize(zip(p.geometry, p.area.clip(upper=60000).astype(np.uint16)), out_shape=d.shape,
                         transform=d.transform, fill=0, dtype=np.uint16)


def max3(path) -> np.ndarray:
    a = read(path).astype(np.float32)
    a[~np.isfinite(a)] = -np.inf
    return ndimage.maximum_filter(a, size=3, mode="nearest")


def unit_threshold(a_km2: str) -> dict:
    """Summary layer at another unit threshold: OOF 5 m LR aggregated to units (per-area intensity) vs slope p90."""
    u = pd.read_parquet(C.OUT / f"units_{a_km2}.parquet")
    u = u[u["in_model_domain"]].reset_index(drop=True)
    lab = C.INTERIM / f"labels_{REGION}"
    dom = read(lab / "domain.tif").astype(bool)
    u5, _ = unit_raster_5m(a_km2, dom.shape)
    n = int(u5.max()) + 1
    s = read(SCORES / "oof_lr_5m.tif").astype(np.float64)
    ok = np.isfinite(s)
    num = np.bincount(u5[ok], weights=np.exp(s[ok]), minlength=n)
    den = np.bincount(u5[dom], minlength=n)
    with np.errstate(divide="ignore", invalid="ignore"):
        agg = np.log(num / np.maximum(den, 1))
    sc = agg[u["unit"].to_numpy()]
    sc = np.where(np.isfinite(sc), sc, np.nanmin(sc[np.isfinite(sc)]) - 1)
    y, huc, rain = u["label"].to_numpy(), u["huc12"].to_numpy(), u["rain_mm_mean"].to_numpy()
    sl = u["slope_deg_p90"].to_numpy()
    r = {"units": len(u), "positive_units": int(y.sum()),
         "auc_rain_stratified": Ranked(sc, y, rain_bin(rain)).stratified_auc(),
         "auc_within_huc": Ranked(sc, y, huc).stratified_auc(),
         "slope_p90_auc_rain_stratified": Ranked(sl, y, rain_bin(rain)).stratified_auc(),
         "slope_p90_auc_within_huc": Ranked(sl, y, huc).stratified_auc()}
    r["model_minus_slope_within_huc"] = r["auc_within_huc"] - r["slope_p90_auc_within_huc"]
    r["model_minus_slope_rain_stratified"] = r["auc_rain_stratified"] - r["slope_p90_auc_rain_stratified"]
    return r


def run() -> dict:
    df, w, rain_ref = load()
    res: dict = {}
    base = run_cv(df, w, rain_ref)
    res["primary"] = evaluate_df(base, df, w)
    print("primary", res["primary"], flush=True)
    for ratio in (5, 20):
        res[f"negative_ratio_1to{ratio}"] = evaluate_df(run_cv(df, w, rain_ref, ratio=ratio), df, w)
    # positives from polygons >= 50 m2 only (train and evaluate)
    area = polygon_area_raster()
    pa = area[df["row"].to_numpy(), df["col"].to_numpy()]
    keep = (df["label"].to_numpy() == 0) | (pa >= 50)
    d2, w2 = df[keep].reset_index(drop=True), w[keep]
    res["positives_ge_50m2"] = evaluate_df(run_cv(d2, w2, rain_ref), d2, w2)
    res["positives_ge_50m2"]["positives_dropped"] = int((~keep).sum())
    del area
    # registration tolerance: 3x3 maximum of the OOF score (and of slope) for every evaluated cell
    r, c = df["row"].to_numpy(), df["col"].to_numpy()
    s3 = max3(SCORES / "oof_lr_5m.tif")[r, c]
    sl3 = max3(C.INTERIM / f"terrain_{REGION}" / "slope_deg.tif")[r, c]
    y = df["label"].to_numpy()
    res["registration_tolerance_3x3"] = metrics(s3, y, df["rain_mm"].to_numpy(), df["huc12"].to_numpy(), w, sl3)
    s0 = read(SCORES / "oof_lr_5m.tif")[r, c]
    res["registration_tolerance_3x3"]["note"] = "M5 OOF raster; reference without tolerance: " + \
        f"{Ranked(s0, y, rain_bin(df['rain_mm'].to_numpy())).stratified_auc(w):.4f} (stratified)"
    # domain >= 300 mm
    m300 = df["rain_mm"].to_numpy() >= 300
    d3, w3 = df[m300].reset_index(drop=True), w[m300]
    res["domain_ge_300mm"] = evaluate_df(run_cv(d3, w3, float(np.median(d3["rain_mm"]))), d3, w3)
    # terrain-only model
    res["terrain_only"] = evaluate_df(run_cv(df, w, rain_ref, drop_rain=True), df, w)
    # leave-one-county-out (county ids as in the label rasters: 1 Yancey, 2 Buncombe)
    cty = counties().reset_index(drop=True)
    cpolys = pd.Series(list(cty.geometry), index=range(1, len(cty) + 1))
    loco = run_cv(df, w, rain_ref, groups=df["county"].to_numpy().astype(int), polys=cpolys)
    res["leave_one_county_out"] = evaluate_df(loco, df, w)
    res["leave_one_county_out"]["by_county"] = {
        str(k): Ranked(loco[df["county"] == k], y[df["county"] == k],
                       df["huc12"].to_numpy()[df["county"] == k]).stratified_auc(w[df["county"] == k])
        for k in (1, 2)}
    # distance decay: training cells removed within d of the held-out watershed
    res["distance_decay"] = {}
    for d in (2000, 5000, 10000):
        res["distance_decay"][f"{d // 1000}km"] = evaluate_df(run_cv(df, w, rain_ref, buffer_m=d), df, w)
    # unit threshold of the summary layer
    res["summary_layer_unit_threshold"] = {a: unit_threshold(a) for a in ("0.05", "0.1", "0.2")}
    for k, v in res.items():
        if isinstance(v, dict) and "auc_rain_stratified" in v and k != "primary":
            v["delta_vs_primary_rain_stratified"] = v["auc_rain_stratified"] - res["primary"]["auc_rain_stratified"]
            v["delta_vs_primary_within_huc"] = v["auc_within_huc"] - res["primary"]["auc_within_huc"]
    for v in res["distance_decay"].values():
        v["delta_vs_primary_rain_stratified"] = v["auc_rain_stratified"] - res["primary"]["auc_rain_stratified"]
        v["delta_vs_primary_within_huc"] = v["auc_within_huc"] - res["primary"]["auc_within_huc"]
    (C.VALIDATION / "m6_sensitivity.json").write_text(json.dumps(res, indent=1, default=float))
    return res


if __name__ == "__main__":
    run()
