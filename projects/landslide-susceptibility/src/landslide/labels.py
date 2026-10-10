"""Labels, exclusions, domain, sample tables, modifier audit and training-data density (PLAN §6, §0b).

AOI only (Watauga labels are built for the M6 temporal check).

* Positives: cells whose centre lies in a positive polygon (`inventory.positive_mask`). A polygon too small
  to contain a cell centre burns the cell containing its representative point, so no positive is lost.
* Exclusion zones (never negatives): every mapped polygon of every event, phase and confidence (+30 m);
  road corridors (TIGER S1xxx centrelines +15 m) so excluded road-related failures do not teach
  "near a road = safe"; open water.
* Domain: inside Buncombe + Yancey, MRMS storm total >= TRIGGER_MM, every predictor valid.
  Hillslope domain: additionally slope >= the 1st percentile of positive-cell slope.
* Sample tables: all positive cells, and a seeded random pool of negative cells (domain minus exclusions),
  each with every predictor, HUC-12, county and slope-unit ids. The pool records the number of eligible
  cells, so per-fold subsamples can be weighted back to the true prevalence.
* Modifier audit: distance of Helene source areas to roads and buildings vs their SlopeModifier.
* Training-data density: Gaussian kernel (sigma 2 km) of all mapped features, per km^2, 100 m grid.
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
from .inventory import normalise, positive_mask
from .terrain import LAYERS as TERRAIN_LAYERS

REGION = "aoi"
EXCLUSION_BUFFER_M = 30
ROAD_BUFFER_M = 15
ROAD_EXCLUDE_MTFCC = {"S1710", "S1720", "S1820", "S1830"}  # walkway, stairway, bike path, bridle path
NEG_POOL = 400_000
DENSITY_CELL_M = 100
DENSITY_SIGMA_M = 2000
ND = C.OUT_NODATA
HYDRO_LAYERS = ("log_area", "hand", "dist_channel")
STACK_FLOAT = ("canopy", "rain_mm", "bedrock_cm")
STACK_INT = ("lc_group", "geology", "hsg", "bedrock_recorded")
UNIT_THRESHOLDS = ("0.05", "0.1", "0.2")


def dem_grid():
    with rasterio.open(C.INTERIM / f"dem_5m_{REGION}.tif") as s:
        return s.transform, s.shape


def counties():
    cty = gpd.read_parquet(C.RAW / "counties.parquet").to_crs(C.CRS)
    return cty[cty["NAME"].isin(C.REGIONS[REGION])]


def inventory() -> gpd.GeoDataFrame:
    inv = normalise(gpd.read_parquet(C.RAW / "ncgs_features.parquet")).to_crs(C.CRS)
    inv["geometry"] = inv.geometry.make_valid()
    return inv


OSM_NON_VEHICLE = {"footway", "path", "steps", "bridleway", "cycleway", "pedestrian", "corridor", "proposed",
                   "construction", "elevator", "platform"}


def roads() -> gpd.GeoDataFrame:
    """Vehicle roads: TIGER/Line S1xxx (minus paths) united with OSM highways (minus paths). OSM adds the
    private drives and service / forest roads that TIGER lacks (46,584 `service` segments in the AOI)."""
    parts = [gpd.read_file(C.RAW / f"tl_2024_{C.STATE_FIPS}{f}_roads.zip") for f in C.REGIONS[REGION].values()]
    t = pd.concat(parts, ignore_index=True).to_crs(C.CRS)
    t = t[t["MTFCC"].str.startswith("S1") & ~t["MTFCC"].isin(ROAD_EXCLUDE_MTFCC)]
    o = gpd.read_parquet(C.RAW / "osm_roads.parquet").to_crs(C.CRS)
    o = o[~o["highway"].isin(OSM_NON_VEHICLE)]
    return pd.concat([t[["geometry"]].assign(source="tiger"), o[["geometry"]].assign(source="osm")],
                     ignore_index=True)


def burn(geoms, tr, shape, all_touched=False) -> np.ndarray:
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return np.zeros(shape, bool)
    return rasterize(((g, 1) for g in geoms), out_shape=shape, transform=tr, fill=0, dtype=np.uint8,
                     all_touched=all_touched).astype(bool)


def positives_raster(pos: gpd.GeoDataFrame, tr, shape) -> tuple[np.ndarray, int]:
    """Cell-centre rasterization; a polygon containing no cell centre burns the cell of its representative
    point instead. Returns the mask and the number of such fallback polygons."""
    m = burn(pos.geometry, tr, shape)
    inv_tr = ~tr
    fallback = 0
    for g in pos.geometry:
        c0, r0 = inv_tr * (g.bounds[0], g.bounds[3])  # (col, row) of the top-left corner
        c1, r1 = inv_tr * (g.bounds[2], g.bounds[1])
        r0, c0 = int(np.floor(r0)), int(np.floor(c0))
        nr, nc = int(np.ceil(r1)) - r0 + 1, int(np.ceil(c1)) - c0 + 1
        sub = burn([g], tr * rasterio.Affine.translation(c0, r0), (nr, nc))
        if sub.any():
            continue
        pt = g.representative_point()
        col, row = inv_tr * (pt.x, pt.y)
        row, col = int(np.floor(row)), int(np.floor(col))
        if 0 <= row < shape[0] and 0 <= col < shape[1]:
            m[row, col] = True
            fallback += 1
    return m, fallback


def read(path, dtype=None):
    with rasterio.open(path) as s:
        a = s.read(1)
    return a if dtype is None else a.astype(dtype)


def run() -> dict:
    tr, shape = dem_grid()
    rep: dict = {}
    out = C.INTERIM / f"labels_{REGION}"
    out.mkdir(parents=True, exist_ok=True)
    cty = counties()
    in_cty = ~geometry_mask(list(cty.geometry), shape, tr)
    county_id = rasterize(((g, i + 1) for i, g in enumerate(cty.geometry)), out_shape=shape, transform=tr,
                          fill=0, dtype=np.uint8)
    inv = inventory()
    pmask = positive_mask(inv)
    pos = inv[pmask & inv.geometry.representative_point().within(cty.union_all())]
    positive, lost = positives_raster(pos, tr, shape)
    rep["positive_polygons"] = int(len(pos))
    rep["positive_polygons_without_cell_centre"] = int(lost)

    # --- exclusions
    excl = burn(inv.geometry.buffer(EXCLUSION_BUFFER_M), tr, shape)
    rd = roads()
    road_corr = burn(rd.geometry.buffer(ROAD_BUFFER_M), tr, shape)
    lc = read(C.INTERIM / f"stack_{REGION}" / "lc_group.tif")
    water = lc == 6
    exclusion = excl | road_corr | water

    # --- domain: counties, triggered rainfall, all predictors valid
    rain = read(C.INTERIM / f"stack_{REGION}" / "rain_mm.tif")
    valid = in_cty & (rain != ND) & (rain >= C.TRIGGER_MM) & ~water
    for k in TERRAIN_LAYERS:
        valid &= read(C.INTERIM / f"terrain_{REGION}" / f"{k}.tif") != ND
    for k in HYDRO_LAYERS:
        valid &= read(C.INTERIM / f"hydro_{REGION}" / f"{k}.tif") != ND
    for k in ("canopy", "bedrock_cm"):
        valid &= read(C.INTERIM / f"stack_{REGION}" / f"{k}.tif") != ND
    valid &= read(C.INTERIM / f"stack_{REGION}" / "bedrock_recorded.tif") != 255
    slope = read(C.INTERIM / f"terrain_{REGION}" / "slope_deg.tif")
    pos_dom = positive & valid
    slope_p1 = float(np.percentile(slope[pos_dom], 1))
    hillslope = valid & (slope >= slope_p1)
    eligible_neg = valid & ~exclusion & ~positive
    rep["domain"] = {
        "county_cells": int(in_cty.sum()), "triggered_valid_cells": int(valid.sum()),
        "triggered_valid_km2": float(valid.sum() * C.CELL_M**2 / 1e6),
        "positive_cells_in_county": int((positive & in_cty).sum()), "positive_cells_in_domain": int(pos_dom.sum()),
        "slope_p1_of_positive_cells_deg": slope_p1, "hillslope_cells": int(hillslope.sum()),
        "excluded_share_of_domain": float((valid & exclusion).sum() / valid.sum()),
        "road_corridor_share_of_domain": float((valid & road_corr).sum() / valid.sum()),
        "eligible_negative_cells": int(eligible_neg.sum()),
        "eligible_negative_hillslope_cells": int((eligible_neg & hillslope).sum()),
    }
    for name, a in (("positive", positive), ("exclusion", exclusion), ("domain", valid), ("hillslope", hillslope)):
        prof = {"driver": "GTiff", "count": 1, "dtype": "uint8", "nodata": None, "crs": C.CRS, "transform": tr,
                "height": shape[0], "width": shape[1], "compress": "deflate", "tiled": True}
        with rasterio.open(out / f"{name}.tif", "w", **prof) as d:
            d.write(a.astype(np.uint8), 1)
    del excl, road_corr

    # --- sample tables
    rng = np.random.default_rng(C.SEED)
    pos_idx = np.flatnonzero(pos_dom.ravel())
    neg_all = np.flatnonzero(eligible_neg.ravel())
    neg_idx = np.sort(rng.choice(neg_all, size=min(NEG_POOL, neg_all.size), replace=False))
    rep["sample"] = {"positives": int(pos_idx.size), "negative_pool": int(neg_idx.size),
                     "negative_pool_weight": float(neg_all.size / neg_idx.size), "seed": C.SEED}
    del neg_all
    huc = gpd.read_parquet(C.RAW / "huc12.parquet").to_crs(C.CRS).reset_index(drop=True)
    huc_r = rasterize(((g, i + 1) for i, g in enumerate(huc.geometry)), out_shape=shape, transform=tr, fill=0,
                      dtype=np.uint16)
    tables = {}
    for name, idx, y in (("positives", pos_idx, 1), ("negatives", neg_idx, 0)):
        r, c = np.divmod(idx, shape[1])
        x, yy = rasterio.transform.xy(tr, r, c)
        df = pd.DataFrame({"row": r.astype(np.int32), "col": c.astype(np.int32), "x": x, "y": yy, "label": y,
                           "county": county_id.ravel()[idx], "hillslope": hillslope.ravel()[idx]})
        h = huc_r.ravel()[idx]
        df["huc12"] = np.where(h > 0, huc["huc12"].to_numpy()[np.maximum(h, 1) - 1], None)
        tables[name] = df
    del huc_r, county_id, hillslope
    for group, names in ((f"terrain_{REGION}", TERRAIN_LAYERS), (f"hydro_{REGION}", HYDRO_LAYERS),
                         (f"stack_{REGION}", STACK_FLOAT + STACK_INT)):
        for k in names:
            a = read(C.INTERIM / group / f"{k}.tif")
            for df in tables.values():
                df[k] = a.ravel()[df["row"].to_numpy() * shape[1] + df["col"].to_numpy()]
            del a
    for a_km2 in UNIT_THRESHOLDS:
        with rasterio.open(C.INTERIM / f"units_{REGION}" / f"units_{a_km2}.tif") as s:
            lab, tr10 = s.read(1), s.transform
        for df in tables.values():
            rr, cc = rasterio.transform.rowcol(tr10, df["x"].to_numpy(), df["y"].to_numpy())
            rr, cc = np.asarray(rr), np.asarray(cc)
            ok = (rr >= 0) & (rr < lab.shape[0]) & (cc >= 0) & (cc < lab.shape[1])
            df[f"unit_{a_km2}"] = np.where(ok, lab[np.clip(rr, 0, lab.shape[0] - 1), np.clip(cc, 0, lab.shape[1] - 1)], 0)
    for name, df in tables.items():
        df.to_parquet(out / f"{name}.parquet", index=False)
    rep["county_names"] = {i + 1: n for i, n in enumerate(cty["NAME"])}
    rep["modifier_audit"] = modifier_audit(inv, cty, rd, out)
    rep["density"] = density(inv, tr, shape, out)
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=float))
    return rep


def modifier_audit(inv, cty, rd, out) -> dict:
    """Independent cross-check of the NCGS natural / road-related coding (PLAN §6), with TIGER + OSM roads
    and NC building footprints. Distance alone cannot verify road-runoff failures (they start downslope of
    the road), so the only flagged conflicts are primary-rule positives within 20 m of a road or building."""
    src = inv[inv["event"].eq("helene") & inv["is_source"]
              & inv.geometry.representative_point().within(cty.union_all())].copy()
    b = gpd.read_parquet(C.RAW / "nc_buildings.parquet").to_crs(C.CRS)

    def nearest(other):
        d = gpd.sjoin_nearest(src[["geometry"]], other[["geometry"]], distance_col="d", how="left")
        return d[~d.index.duplicated()]["d"]

    src["d_road_m"], src["d_building_m"] = nearest(rd), nearest(b)
    src["primary_positive"] = positive_mask(src)
    cls = np.select([src["primary_positive"], src["natural"] & ~src["natural_runoff"],
                     src["SlopeModifier"].isin(["Road Cut", "Road Embankment", "Embankment/Fill Slope", "Cut Slope"])],
                    ["natural (primary)", "natural slope, runoff-modified", "road / cut / fill"], "other")
    src["class"] = cls
    g = src.groupby("class")
    res = {
        "n_source_areas": int(len(src)),
        "by_class": {k: {"n": int(len(v)), "median_d_road_m": round(float(v["d_road_m"].median()), 1),
                         "share_le20m_road": round(float((v["d_road_m"] <= 20).mean()), 3),
                         "share_gt100m_road": round(float((v["d_road_m"] > 100).mean()), 3)} for k, v in g},
        "road_embankment_with_road_runoff": float(
            src.loc[src["SlopeModifier"].eq("Road Embankment"), "RunoffModifier"].eq("Road Runoff").mean()),
    }
    conflicts = src[src["primary_positive"] & ((src["d_road_m"] <= 20) | (src["d_building_m"] <= 20))]
    cols = ["OBJECTID", "SlopeModifier", "RunoffModifier", "d_road_m", "d_building_m"]
    C.VALIDATION.mkdir(exist_ok=True)
    conflicts[cols].sort_values("OBJECTID").to_csv(C.VALIDATION / "modifier_conflicts.csv", index=False,
                                                   float_format="%.1f")
    res["primary_positives_within_20m_of_road_or_building"] = int(len(conflicts))
    return res


def density(inv, tr, shape, out) -> dict:
    """Kernel density of all mapped features (any event, phase, confidence), features per km^2."""
    f = DENSITY_CELL_M // C.CELL_M
    h, w = shape[0] // f, shape[1] // f
    tr100 = tr * rasterio.Affine.scale(f)
    pts = inv.geometry.representative_point()
    rr, cc = rasterio.transform.rowcol(tr100, pts.x.to_numpy(), pts.y.to_numpy())
    rr, cc = np.asarray(rr), np.asarray(cc)
    ok = (rr >= 0) & (rr < h) & (cc >= 0) & (cc < w)
    cnt = np.zeros((h, w), np.float64)
    np.add.at(cnt, (rr[ok], cc[ok]), 1.0)
    dens = ndimage.gaussian_filter(cnt, DENSITY_SIGMA_M / DENSITY_CELL_M, mode="constant") / (DENSITY_CELL_M**2 / 1e6)
    prof = {"driver": "GTiff", "count": 1, "dtype": "float32", "nodata": None, "crs": C.CRS, "transform": tr100,
            "height": h, "width": w, "compress": "deflate"}
    with rasterio.open(out / "density_100m.tif", "w", **prof) as d:
        d.write(dens.astype(np.float32), 1)
    return {"features": int(ok.sum()), "sigma_m": DENSITY_SIGMA_M, "max_per_km2": float(dens.max())}


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=float))
