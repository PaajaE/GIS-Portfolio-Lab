"""Vectorize largest patches and compute access / servicing metrics per parcel.

frontage: parcel boundary length within FRONTAGE_TOL_M of a road centreline
  (public = MassDOT jurisdiction 1 state or 2 town-accepted). A geometric proxy for
  legal frontage, which depends on recorded lot lines and zoning.
road distance: straight-line distance from the moderate largest patch to the nearest
  road centreline (not travel time, not legal access).
sewer: share of parcel area inside a MassDEP POTW sewer service area.

Writes data/out/patches.parquet and data/out/parcels.parquet (GeoParquet, final schema).
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape

from . import analyze as A
from . import config as C
from .prepare import grid_transform

FRONTAGE_TOL_M = 12.0
PUBLIC_JURISDICTIONS = ("1", "2")


def vectorize_patches() -> gpd.GeoDataFrame:
    frames = []
    for s in C.SCENARIO_ORDER:
        with rasterio.open(C.OUT / f"patches_{s}.tif") as src:
            mask = src.read(1)
        lab = np.where(mask == 2, A.pidx(), 0).astype(np.int32)
        geoms, pids = [], []
        for geom, val in shapes(lab, mask=lab > 0, transform=grid_transform(A.grid()), connectivity=4):
            geoms.append(geom)
            pids.append(int(val))
        g = gpd.GeoDataFrame({"pid": pids}, geometry=[shape(x) for x in geoms], crs=C.CRS)
        g = g.dissolve(by="pid", as_index=False)  # 4-connected patch = one polygon; dissolve guards edge cases
        g["scenario"] = s
        g["area_m2"] = g.area
        frames.append(g)
    return pd.concat(frames, ignore_index=True)


def frontage(p: gpd.GeoDataFrame, roads: gpd.GeoDataFrame) -> pd.Series:
    zone = roads.buffer(FRONTAGE_TOL_M).union_all()
    return p.geometry.boundary.intersection(zone).length


def main() -> None:
    p = A.parcels().copy()
    m = pd.read_parquet(C.OUT / "parcel_metrics.parquet")
    patches = vectorize_patches()
    patches.to_parquet(C.OUT / "patches.parquet")

    roads = A.vec("roads")
    public = roads[roads["JURISDICTN"].isin(PUBLIC_JURISDICTIONS)]
    p["frontage_public_m"] = frontage(p, public).round(1)
    p["frontage_any_m"] = frontage(p, roads).round(1)

    near = gpd.sjoin_nearest(p[["pid", "geometry"]], roads[["CLASS", "STREETNAME", "geometry"]], how="left", distance_col="d")
    near = near.sort_values(["pid", "d"]).drop_duplicates("pid").set_index("pid")
    p = p.set_index("pid")
    p["nearest_road_class"] = near["CLASS"]
    p["nearest_road_name"] = near["STREETNAME"]

    mod = patches[patches["scenario"] == "moderate"][["pid", "geometry"]]
    pd_ = gpd.sjoin_nearest(mod, roads[["geometry"]], how="left", distance_col="d").groupby("pid")["d"].min()
    p["patch_road_dist_m_mod"] = pd_.round(1)

    sewer = A.vec("sewer")
    amherst_sewer = sewer[sewer["TOWNNAME"].str.upper() == C.TOWN_NAME.upper()].union_all()
    p["sewer_share"] = (p.geometry.intersection(amherst_sewer).area / p.geometry.area).clip(0, 1).round(3)

    out = gpd.GeoDataFrame(p.join(m.set_index("pid")), geometry="geometry", crs=C.CRS).reset_index()
    out.to_parquet(C.OUT / "parcels.parquet")
    print(out[["frontage_public_m", "patch_road_dist_m_mod", "sewer_share"]].describe().round(1).to_string())
    print("parcels with no public frontage:", int((out.frontage_public_m < 1).sum()))


if __name__ == "__main__":
    main()
