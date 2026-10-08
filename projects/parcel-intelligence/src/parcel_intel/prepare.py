"""Harmonize raw inputs: project to EPSG:26986, validate geometry, build the 2 m grid,
resample the DEM and derive slope.

Outputs (data/interim/):
  <layer>.parquet       GeoParquet in EPSG:26986
  parcels.parquet       one row per LOC_ID (stacked condo polygons collapsed)
  grid.json             grid definition shared by every raster
  dem_2m.tif            DEM, mean of 1 m cells (NAVD88 m)
  slope_pct.tif         slope in percent (Horn 3x3); nodata where any neighbour is nodata
  parcel_idx.tif        parcel index (1..N, 0 = no parcel), cell-centre rasterization
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import reproject

from . import config as C

NODATA = -9999.0
LAYERS = ("town", "flood", "wetlands", "streams", "waterbodies", "openspace", "roads", "buildings", "sewer", "prihab")


def load_raw(name: str) -> tuple[gpd.GeoDataFrame, int]:
    gdf = gpd.read_file(C.RAW / f"{name}.geojson")
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        raise ValueError(f"{name}: expected EPSG:4326 GeoJSON, got {gdf.crs}")
    gdf = gdf.to_crs(C.CRS)
    invalid = ~gdf.is_valid
    if invalid.any():
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].make_valid()
    gdf = gdf[~gdf.is_empty & gdf.geometry.notna()].copy()
    return gdf, int(invalid.sum())


def collapse_parcels(raw: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One row per LOC_ID. Condominium records are stacked copies of one polygon."""
    raw = raw[raw["POLY_TYPE"] == "FEE"].copy()
    raw["is_condo"] = raw["USE_CODE"].fillna("").str[:3] == "102"  # residential condominium
    raw["TOTAL_VAL"] = pd.to_numeric(raw["TOTAL_VAL"], errors="coerce")
    raw["is_exempt"] = raw["USE_CODE"].fillna("").str.startswith("9")
    # Use code, description and zoning come from one representative record (highest
    # assessed value) so they never mix records; exemption is flagged if any record is exempt.
    rep = raw.sort_values(["LOC_ID", "TOTAL_VAL"], ascending=[True, False], na_position="last").groupby("LOC_ID").first()
    agg = raw.groupby("LOC_ID", sort=True).agg(
        map_par_id=("MAP_PAR_ID", "first"),
        site_addr=("SITE_ADDR", lambda s: next((v for v in s if isinstance(v, str) and v.strip()), None)),
        any_exempt=("is_exempt", "any"),
        year_built=("YEAR_BUILT", "max"),
        fy=("FY", "max"),
        n_records=("LOC_ID", "size"),
        is_condo=("is_condo", "any"),
        total_val=("TOTAL_VAL", "sum"),
    )
    agg = agg.join(rep[["USE_CODE", "USE_DESC", "ZONING"]].rename(columns=str.lower))
    geom = raw.groupby("LOC_ID", sort=True).geometry.first()
    # stacked copies must be identical; verify rather than assume
    areas = raw.groupby("LOC_ID").geometry.agg(lambda g: float(np.ptp(g.area)))
    if (areas > 0.01).any():
        raise ValueError(f"{int((areas > 0.01).sum())} LOC_IDs have differing stacked geometries")
    out = gpd.GeoDataFrame(agg, geometry=geom, crs=raw.crs).reset_index().rename(columns={"LOC_ID": "loc_id"})
    out["year_built"] = pd.to_numeric(out["year_built"], errors="coerce").where(lambda v: v > 1600)
    out["zone_district"] = out["zoning"].str.extract(r"^([A-Z]+)", expand=False)
    out["area_m2"] = out.area
    out.insert(0, "pid", np.arange(1, len(out) + 1, dtype=np.int32))
    return out


def grid_for(town: gpd.GeoDataFrame) -> dict:
    x0, y0, x1, y1 = town.buffer(C.AOI_BUFFER_M).total_bounds
    c = C.CELL_M
    x0, y0 = np.floor(x0 / c) * c, np.floor(y0 / c) * c
    x1, y1 = np.ceil(x1 / c) * c, np.ceil(y1 / c) * c
    return {
        "crs": C.CRS,
        "cell_m": c,
        "xmin": float(x0),
        "ymax": float(y1),
        "width": int(round((x1 - x0) / c)),
        "height": int(round((y1 - y0) / c)),
    }


def grid_transform(g: dict):
    return from_origin(g["xmin"], g["ymax"], g["cell_m"], g["cell_m"])


def write_raster(path, arr, g, nodata=None):
    profile = {
        "driver": "GTiff",
        "height": g["height"],
        "width": g["width"],
        "count": 1,
        "dtype": arr.dtype,
        "crs": g["crs"],
        "transform": grid_transform(g),
        "compress": "deflate",
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
        "nodata": nodata,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)


def resample_dem(g: dict) -> np.ndarray:
    dst = np.full((g["height"], g["width"]), NODATA, dtype=np.float32)
    with rasterio.open(C.RAW / "dem_1m_utm18.tif") as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_nodata=src.nodata,
            dst_transform=grid_transform(g),
            dst_crs=g["crs"],
            dst_nodata=NODATA,
            resampling=Resampling.average,  # continuous field, 1 m -> 2 m
        )
    return dst


def horn_slope_pct(dem: np.ndarray, cell: float, nodata: float = NODATA) -> np.ndarray:
    """Horn (1981) 3x3 gradient. Border cells and cells with any nodata neighbour -> nodata."""
    z = dem.astype(np.float64)
    valid = dem != nodata
    out = np.full(dem.shape, nodata, dtype=np.float32)
    if dem.shape[0] < 3 or dem.shape[1] < 3:
        return out
    a, b, c = z[:-2, :-2], z[:-2, 1:-1], z[:-2, 2:]
    d, f = z[1:-1, :-2], z[1:-1, 2:]
    g, h, i = z[2:, :-2], z[2:, 1:-1], z[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * cell)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * cell)
    s = 100.0 * np.hypot(dzdx, dzdy)
    ok = np.ones_like(s, dtype=bool)
    for dy in range(3):
        for dx in range(3):
            ok &= valid[dy : dy + s.shape[0], dx : dx + s.shape[1]]
    out[1:-1, 1:-1] = np.where(ok, s, nodata)
    return out


def main() -> None:
    C.INTERIM.mkdir(parents=True, exist_ok=True)
    report = {"invalid_repaired": {}, "features": {}}
    for name in LAYERS:
        gdf, n_bad = load_raw(name)
        report["invalid_repaired"][name] = n_bad
        report["features"][name] = len(gdf)
        gdf.to_parquet(C.INTERIM / f"{name}.parquet")

    raw_parcels, n_bad = load_raw("parcels")
    report["invalid_repaired"]["parcels"] = n_bad
    parcels = collapse_parcels(raw_parcels)
    overlap = gpd.overlay(parcels[["pid", "geometry"]], parcels[["pid", "geometry"]], how="intersection", keep_geom_type=True)
    overlap = overlap[overlap.pid_1 < overlap.pid_2]
    report["parcels"] = {
        "raw_polygons": len(raw_parcels),
        "parcels": len(parcels),
        "condo_parcels": int(parcels.is_condo.sum()),
        "total_area_km2": round(float(parcels.area_m2.sum()) / 1e6, 3),
        "overlap_pairs_gt_1m2": int((overlap.area > 1).sum()),
        "overlap_area_m2": round(float(overlap.area.sum()), 1),
    }
    parcels.to_parquet(C.INTERIM / "parcels.parquet")

    town = gpd.read_parquet(C.INTERIM / "town.parquet")
    g = grid_for(town)
    (C.INTERIM / "grid.json").write_text(json.dumps(g, indent=2))

    dem = resample_dem(g)
    write_raster(C.INTERIM / "dem_2m.tif", dem, g, NODATA)
    slope = horn_slope_pct(dem, g["cell_m"])
    write_raster(C.INTERIM / "slope_pct.tif", slope, g, NODATA)

    pidx = rasterize(
        zip(parcels.geometry, parcels.pid),
        out_shape=(g["height"], g["width"]),
        transform=grid_transform(g),
        fill=0,
        dtype="int32",
        all_touched=False,  # cell-centre semantics
    )
    write_raster(C.INTERIM / "parcel_idx.tif", pidx, g, None)

    cells = np.bincount(pidx.ravel(), minlength=len(parcels) + 1)[1:]
    valid = slope != NODATA
    report["grid"] = g
    report["dem"] = {
        "nodata_share_in_parcels": float(1 - valid[pidx > 0].mean()),
        "elev_min_m": float(dem[dem != NODATA].min()),
        "elev_max_m": float(dem[dem != NODATA].max()),
        "slope_pct_p50_p90_p99_in_parcels": [float(v) for v in np.percentile(slope[(pidx > 0) & valid], [50, 90, 99])],
    }
    report["rasterization"] = {
        "parcels_without_cells": int((cells == 0).sum()),
        "smallest_parcel_without_cells_m2": float(parcels.area_m2[cells == 0].max()) if (cells == 0).any() else None,
        "area_ratio_raster_over_vector_total": float(cells.sum() * g["cell_m"] ** 2 / parcels.area_m2.sum()),
    }
    (C.INTERIM / "prepare_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
