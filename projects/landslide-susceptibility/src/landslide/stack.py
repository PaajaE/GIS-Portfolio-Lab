"""Harmonize the non-terrain predictors onto each region's 5 m DEM grid (PLAN §4-5).

Every output shares the DEM mosaic's CRS (EPSG:26917), transform and shape. Rules:
* categorical rasters (NLCD 2021) -> nearest; categorical polygons (geology, SSURGO) -> cell-centre rasterization
* continuous rasters (tree canopy, MRMS rainfall) -> bilinear
* nodata is declared per layer and never zero-filled; the canopy product's 254 flag becomes nodata,
  and its 0 stays a valid 0 % (the file wrongly declares nodata = 0)

Outputs in data/interim/stack_<region>/:
  lc_group.tif (uint8)    1 forest (41-43), 2 developed open (21), 3 developed (22-24),
                          4 open / agricultural (31, 52, 71, 81, 82), 5 wetland (90, 95), 6 open water (11); 0 nodata
  canopy.tif (float32)    tree canopy %, 2021
  rain_mm.tif (float32)   MRMS 72 h storm total, cell-wise max of the windows ending 2024-09-28 00Z and 12Z
  geology.tif (uint8)     lithology group, GEOLOGY_GROUPS; 0 = unmapped
  hsg.tif (uint8)         SSURGO dominant hydrologic soil group 1 A, 2 B, 3 C, 4 D (dual X/D -> 4); 0 = not rated
  bedrock_cm.tif (float32) SSURGO minimum depth to bedrock (cm); NO_BEDROCK_CM where none is recorded within
                          the described profile (SSURGO null) — see `bedrock_recorded.tif`
  bedrock_recorded.tif (uint8) 1 = depth recorded, 0 = none within the profile, 255 = no soil data
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.warp import reproject

from . import config as C

ND_F = np.float32(C.OUT_NODATA)
NO_BEDROCK_CM = 250.0  # beyond the ~200 cm SSURGO profile; paired with the bedrock_recorded flag

LC_GROUPS = {41: 1, 42: 1, 43: 1, 21: 2, 22: 3, 23: 3, 24: 3, 31: 4, 52: 4, 71: 4, 81: 4, 82: 4, 90: 5, 95: 5, 11: 6}
# Lithology groups (NCGS 1985 units in the AOI, Watauga and their buffers), by weathering / mechanical
# behaviour. Units outside the counties only matter for buffer cells, which are never in the domain.
GEOLOGY_GROUPS = {
    1: ("metasedimentary / metavolcanic schist, gneiss and slate",
        ["Zatm", "Zatw", "Zabg", "ZYbn", "Zs", "Zgs", "Ccl", "Ccu", "bz", "CZbg", "Zgma", "Zgms", "Zgmw", "Zgmf",
         "Zgmu", "Zabs", "Zatb", "CZgms", "CZms", "CZpg", "CZtp", "CZba", "Zsl", "Zsp", "Zsr", "Zss", "Zsw", "Zwc",
         "Cr", "Cs"]),
    2: ("Mesoproterozoic basement orthogneiss", ["Ymg", "Ybgg", "Ygg", "Ybrg"]),
    3: ("granitoid intrusions", ["Chg", "SOgg", "Dqd", "Zg", "Dsc", "OCg", "OCgm", "Zm"]),
    4: ("mafic and ultramafic rocks", ["Ymam", "Zata", "Zaba", "PzZu", "Ybam", "CZab", "Zgmg", "Zlm"]),
}
HSG = {"A": 1, "B": 2, "C": 3, "D": 4, "A/D": 4, "B/D": 4, "C/D": 4}


def grid(region: str) -> dict:
    with rasterio.open(C.INTERIM / f"dem_5m_{region}.tif") as s:
        return {"crs": s.crs, "transform": s.transform, "height": s.height, "width": s.width}


def _write(path, a, g, nodata):
    prof = {"driver": "GTiff", "count": 1, "dtype": a.dtype.name, "nodata": nodata, "crs": g["crs"],
            "transform": g["transform"], "height": g["height"], "width": g["width"], "compress": "deflate",
            "tiled": True, "blockxsize": 512, "blockysize": 512, "BIGTIFF": "IF_SAFER"}
    if a.dtype == np.float32:
        prof["predictor"] = 3
    with rasterio.open(path, "w", **prof) as d:
        d.write(a, 1)


def _warp(src_path, g, resampling, src_nodata, dtype, dst_nodata, src_array=None, src_transform=None, src_crs=None):
    dst = np.full((g["height"], g["width"]), dst_nodata, dtype=dtype)
    if src_array is None:
        with rasterio.open(src_path) as s:
            src_array, src_transform, src_crs = s.read(1), s.transform, s.crs
    reproject(src_array, dst, src_transform=src_transform, src_crs=src_crs, src_nodata=src_nodata,
              dst_transform=g["transform"], dst_crs=g["crs"], dst_nodata=dst_nodata, resampling=resampling)
    return dst


def lc_group(region, g):
    nlcd = _warp(C.RAW / f"nlcd2021_{region}.tif", g, Resampling.nearest, 0, np.uint8, 0)
    lut = np.zeros(256, np.uint8)
    for k, v in LC_GROUPS.items():
        lut[k] = v
    return lut[nlcd]


def canopy(region, g):
    with rasterio.open(C.RAW / f"tcc2021_{region}.tif") as s:
        a = s.read(1).astype(np.float32)
        a[a > 100] = ND_F  # 254 = no-data flag of the product; 0 is a valid 0 %
        return _warp(None, g, Resampling.bilinear, float(ND_F), np.float32, float(ND_F), a, s.transform, s.crs)


def rain(region, g):
    arrs = []
    for f in C.MRMS_FILES:
        with rasterio.open(C.RAW / f.removesuffix(".gz")) as s:
            arrs.append(s.read(1).astype(np.float32))
            tr, crs = s.transform, s.crs
    a = np.maximum(*arrs)
    a[a < 0] = ND_F  # MRMS missing / outside coverage
    return _warp(None, g, Resampling.bilinear, float(ND_F), np.float32, float(ND_F), a, tr, crs)


def geology(region, g):
    geo = gpd.read_parquet(C.RAW / "geology_1985.parquet").to_crs(C.CRS)
    code = {u: k for k, (_, units) in GEOLOGY_GROUPS.items() for u in units}
    geo["code"] = geo["UnitLabel"].map(code)
    unknown = sorted(set(geo.loc[geo["code"].isna(), "UnitLabel"]))
    geo = geo.dropna(subset=["code"])
    out = rasterize(zip(geo.geometry, geo["code"].astype(int)), out_shape=(g["height"], g["width"]),
                    transform=g["transform"], fill=0, dtype=np.uint8, all_touched=False)
    return out, unknown


def soils(region, g):
    parts = [gpd.read_parquet(p) for p in sorted(C.RAW.glob("ssurgo_*.parquet"))]
    s = pd.concat(parts, ignore_index=True).set_crs(4326, allow_override=True).to_crs(C.CRS)
    s["depth"] = pd.to_numeric(s["brockdepmin"], errors="coerce")
    s["hsg"] = s["hydgrpdcd"].map(HSG).fillna(0).astype(int)
    s = s[s.is_valid | s.geometry.notna()].copy()
    s["geometry"] = s.geometry.make_valid()
    s["idx"] = np.arange(1, len(s) + 1)
    shape = (g["height"], g["width"])
    idx = rasterize(zip(s.geometry, s["idx"]), out_shape=shape, transform=g["transform"], fill=0,
                    dtype=np.uint32, all_touched=False)
    hsg_lut = np.r_[0, s["hsg"].to_numpy()].astype(np.uint8)
    rec = np.r_[255, np.where(s["depth"].notna(), 1, 0)].astype(np.uint8)
    dep = np.r_[ND_F, s["depth"].fillna(NO_BEDROCK_CM).to_numpy()].astype(np.float32)
    return hsg_lut[idx], dep[idx], rec[idx]


def run_region(region: str) -> dict:
    g = grid(region)
    out = C.INTERIM / f"stack_{region}"
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    a = lc_group(region, g)
    _write(out / "lc_group.tif", a, g, 0)
    report["lc_group_counts"] = {int(k): int(v) for k, v in zip(*np.unique(a, return_counts=True))}
    del a
    for name, fn in (("canopy", canopy), ("rain_mm", rain)):
        a = fn(region, g)
        _write(out / f"{name}.tif", a, g, float(ND_F))
        v = a[a != ND_F]
        report[name] = {"nodata_share": float((a == ND_F).mean()), "min": float(v.min()), "max": float(v.max())}
        del a, v
    a, unknown = geology(region, g)
    _write(out / "geology.tif", a, g, 0)
    report["geology_counts"] = {int(k): int(v) for k, v in zip(*np.unique(a, return_counts=True))}
    report["geology_units_not_grouped"] = unknown
    del a
    hsg, dep, rec = soils(region, g)
    _write(out / "hsg.tif", hsg, g, 0)
    _write(out / "bedrock_cm.tif", dep, g, float(ND_F))
    _write(out / "bedrock_recorded.tif", rec, g, 255)
    report["hsg_counts"] = {int(k): int(v) for k, v in zip(*np.unique(hsg, return_counts=True))}
    report["bedrock_recorded_counts"] = {int(k): int(v) for k, v in zip(*np.unique(rec, return_counts=True))}
    return report


if __name__ == "__main__":
    import json

    for r in C.REGIONS:
        rep = run_region(r)
        (C.INTERIM / f"stack_{r}" / "report.json").write_text(json.dumps(rep, indent=1))
        print(r, json.dumps(rep), flush=True)
