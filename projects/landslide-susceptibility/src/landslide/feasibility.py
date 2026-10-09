"""Feasibility of the validation design (PLAN §0b), from the harvested inventory, HUC-12s and MRMS.

Answers, before any terrain processing: how clustered are the positives, do HUC-12 blocks separate them,
how strongly does Helene rainfall confound the inventory, and what the Watauga temporal test can support.
Writes validation/feasibility.json (all numbers quoted in PLAN §0b come from here).
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

from . import config as C
from .inventory import normalise, positive_mask

RAIN_BINS = [0, 200, 250, 300, 350, 400, 450, 1000]


def load_inventory() -> gpd.GeoDataFrame:
    inv = normalise(gpd.read_parquet(C.RAW / "ncgs_features.parquet")).to_crs(C.CRS)
    inv["pt"] = inv.geometry.representative_point()
    return inv


def rainfall():
    """Cell-wise maximum of the two 72 h windows (covers 25 Sep 00Z -> 28 Sep 12Z), mm, MRMS lat/lon grid."""
    arrs = []
    for f in C.MRMS_FILES:
        with rasterio.open(C.RAW / f.removesuffix(".gz")) as s:
            arrs.append(s.read(1).astype(np.float64))
            tr, crs, nod = s.transform, s.crs, s.nodata
    a = np.maximum(*arrs)
    a[a < 0] = np.nan  # MRMS missing (-3) / no coverage
    return a, tr, crs


def sample(a, tr, crs, pts: gpd.GeoSeries) -> np.ndarray:
    p = pts.to_crs(crs)
    r, c = rasterio.transform.rowcol(tr, p.x.values, p.y.values)
    return a[np.asarray(r), np.asarray(c)]


def run() -> dict:
    out: dict = {}
    cty = gpd.read_parquet(C.RAW / "counties.parquet").to_crs(C.CRS)
    aoi = cty[cty["NAME"].isin(C.REGIONS["aoi"])]
    aoi_u = aoi.union_all()
    inv = load_inventory()
    pts = inv.set_geometry("pt")
    in_aoi = pts.within(aoi_u)
    pos = pts[positive_mask(inv) & in_aoi].copy()
    pos = gpd.sjoin(pos, aoi[["NAME", "geometry"]], predicate="within").drop(columns="index_right")
    out["positives"] = {"n": len(pos), "by_county": pos["NAME"].value_counts().to_dict(),
                        "road_related_helene_sources_in_aoi": int(
                            (inv["event"].eq("helene") & inv["is_source"] & ~inv["natural"] & in_aoi).sum())}

    # --- HUC-12 concentration
    huc = gpd.read_parquet(C.RAW / "huc12.parquet").to_crs(C.CRS)
    h = huc[huc.intersects(aoi_u)].copy()
    h["frac_in_aoi"] = h.intersection(aoi_u).area / h.area
    h = h[h["frac_in_aoi"] >= 0.5].copy()
    h["km2_aoi"] = h.intersection(aoi_u).area / 1e6
    pos = gpd.sjoin(pos, h[["huc12", "geometry"]], predicate="within", how="left").drop(columns="index_right")
    h["n_pos"] = pos.groupby("huc12").size().reindex(h["huc12"]).fillna(0).astype(int).values
    s = np.sort(h["n_pos"].values)[::-1]
    out["huc12"] = {"n": len(h), "km2_median": float(h["km2_aoi"].median()), "zero": int((s == 0).sum()),
                    "ge10": int((s >= 10).sum()), "ge50": int((s >= 50).sum()),
                    "share_top3_5_10": [float(s[:k].sum() / s.sum()) for k in (3, 5, 10)],
                    "positives_outside_assigned_huc": int(pos["huc12"].isna().sum())}

    # --- clustering and cross-boundary proximity
    pos = pos.dropna(subset=["huc12"])
    xy = np.c_[pos.geometry.x, pos.geometry.y]
    t = cKDTree(xy)
    d, i = t.query(xy, k=2)
    hucs = pos["huc12"].values
    cross = {}
    for r in (250, 500, 1000):
        pr = t.query_pairs(r, output_type="ndarray")
        cross[r] = float((hucs[pr[:, 0]] != hucs[pr[:, 1]]).mean()) if len(pr) else 0.0
    lam = len(pos) / aoi_u.area
    out["clustering"] = {
        "nn_median_m": float(np.median(d[:, 1])), "nn_p90_m": float(np.percentile(d[:, 1], 90)),
        "nn_same_huc12": float((hucs[i[:, 1]] == hucs).mean()),
        "pairs_crossing_huc12_by_radius_m": cross,
        "within_500m_of_huc12_boundary": float((pos.geometry.distance(h.boundary.union_all()) < 500).mean()),
        "K_over_pi_r2": {r: float((t.query_ball_point(xy, r, return_length=True) - 1).mean() / lam / (np.pi * r * r))
                         for r in (200, 1000, 3000, 5000, 10000)},
    }

    # --- rainfall confounding (MRMS cells inside the AOI vs positives)
    a, tr, crs = rainfall()
    g = aoi.to_crs(crs).union_all()
    inside = ~geometry_mask([g], a.shape, tr, all_touched=False)
    lat = np.deg2rad((g.bounds[1] + g.bounds[3]) / 2)
    cell_km2 = (111.32 * abs(tr.e)) * (111.32 * np.cos(lat) * tr.a)
    rain_pos = sample(a, tr, crs, pos.geometry)
    ca = np.histogram(a[inside & np.isfinite(a)], RAIN_BINS)[0] * cell_km2
    cp = np.histogram(rain_pos[np.isfinite(rain_pos)], RAIN_BINS)[0]
    out["rainfall"] = {
        "bins_mm": RAIN_BINS, "area_km2": ca.round(1).tolist(), "positives": cp.tolist(),
        "per_km2": (cp / np.maximum(ca, 1e-9)).round(3).tolist(),
        "triggered_domain_km2": float(ca[np.array(RAIN_BINS[:-1]) >= C.TRIGGER_MM].sum()),
        "positives_in_triggered_domain": float((rain_pos >= C.TRIGGER_MM).mean()),
        "aoi_mrms_nan_cells": int((inside & ~np.isfinite(a)).sum()),
    }
    hr = h.to_crs(crs)
    h["rain"] = [np.nanmean(a[~geometry_mask([geom], a.shape, tr, all_touched=True)]) for geom in hr.geometry]
    h["dens"] = h["n_pos"] / h["km2_aoi"]
    rho, p = spearmanr(h["rain"], h["dens"])
    trig = h[h["rain"] >= C.TRIGGER_MM]
    out["rainfall"]["huc12_spearman_rain_density"] = {"rho": float(rho), "p": float(p)}
    out["rainfall"]["huc12_in_triggered_domain"] = {"n": len(trig), "positives": int(trig["n_pos"].sum()),
                                                    "ge50": int((trig["n_pos"] >= 50).sum())}

    # --- inventory method and size in AOI
    pp = inv.loc[pos.index]
    out["inventory_method"] = {"basemap_top": pp["Basemap"].fillna("NA").str.strip().value_counts().head(3).to_dict(),
                               "area_m2_median": float(pp.area.median()),
                               "share_lt_50m2": float((pp.area < 50).mean()),
                               "undated_in_aoi": int((inv["event"].eq("undated") & in_aoi).sum())}

    # --- Watauga temporal test
    w = cty[cty["NAME"].isin(C.REGIONS["watauga"])].union_all()
    wp = pts[pts.within(w)]
    w40, w24 = wp[wp["event"].eq("1940-08")], wp[wp["event"].eq("helene")]
    dist = cKDTree(np.c_[w40.geometry.x, w40.geometry.y]).query(np.c_[w24.geometry.x, w24.geometry.y])[0]
    overl = gpd.sjoin(inv.loc[w24.index][["geometry"]], inv.loc[w40.index][["geometry"]], predicate="intersects")
    out["watauga"] = {
        "n_1940": len(w40), "n_helene": len(w24),
        "feature_types_1940": w40["FeatureType"].value_counts().to_dict(),
        "feature_types_helene": w24["FeatureType"].value_counts().to_dict(),
        "basemap_1940": w40["Basemap"].fillna("NA").str.strip().value_counts().head(3).to_dict(),
        "basemap_helene": w24["Basemap"].fillna("NA").str.strip().value_counts().head(4).to_dict(),
        "modifier_helene": w24["SlopeModifier"].fillna("not assessed").value_counts().to_dict(),
        "exist_conf_1940": w40["exist_conf"].value_counts().to_dict(),
        "outline_area_m2_median": {"1940": float(inv.loc[w40.index].area.median()),
                                   "helene": float(inv.loc[w24.index].area.median())},
        "helene_to_1940_m": {"median": float(np.median(dist)), "lt100": float((dist < 100).mean()),
                             "lt250": float((dist < 250).mean()), "lt1000": float((dist < 1000).mean())},
        "helene_overlapping_1940": int(overl.index.nunique()),
        "helene_inside_1940_hull": float(w24.within(w40.union_all().convex_hull).mean()),
        "mean_rain_mm": float(np.nanmean(a[~geometry_mask([gpd.GeoSeries([w], crs=C.CRS).to_crs(crs).iloc[0]],
                                                           a.shape, tr, all_touched=True)])),
    }
    C.VALIDATION.mkdir(exist_ok=True)
    (C.VALIDATION / "feasibility.json").write_text(json.dumps(out, indent=1, default=float))
    h.drop(columns="geometry").sort_values("n_pos", ascending=False).to_csv(
        C.VALIDATION / "feasibility_huc12.csv", index=False, float_format="%.3f")
    return out


if __name__ == "__main__":
    r = run()
    print(json.dumps({k: r[k] for k in ("positives", "huc12", "rainfall")}, indent=1, default=float))
