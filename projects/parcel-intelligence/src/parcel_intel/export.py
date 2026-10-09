"""Web artifacts for the static app (web/data/).

parcels.pmtiles   parcel polygons with styling attributes (layer "parcels")
patches.pmtiles   largest contiguous patch per parcel and scenario (layer "patches")
context.pmtiles   flood, wetlands/water, streams, protected land, habitat, roads, buildings, town
hillshade.jpg / slope.png + overlays.json   Web Mercator image overlays
parcels.json      column-oriented parcel details (inspector + search)
summary.json      town-level results, sensitivity, validation, benchmark, provenance
downloads/        parcel results as CSV and GeoParquet (EPSG:26986)
"""

from __future__ import annotations

import json
import shutil
import subprocess

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject

from . import analyze as A
from . import config as C
from .prepare import NODATA, grid_transform

TMP = C.INTERIM / "web"
ROBUSTNESS_CODES = {"robust": 3, "assumption-dependent": 2, "only aggressive": 1, "constrained": 0, "not screened": -1}
SCEN_CODES = {s: i for i, s in enumerate(C.SCENARIO_ORDER)}


def tippecanoe(out, layers: dict[str, str], minzoom: int, maxzoom: int, extra=()) -> None:
    cmd = ["tippecanoe", "-o", str(out), "--force", "-Z", str(minzoom), "-z", str(maxzoom), "--quiet"]
    for name, path in layers.items():
        cmd += ["-L", f"{name}:{path}"]
    subprocess.run(cmd + list(extra), check=True)


def to_geojson(gdf: gpd.GeoDataFrame, name: str, cols: list[str], precision: int = 6) -> str:
    path = TMP / f"{name}.geojson"
    g = gdf[cols + ["geometry"]].to_crs(4326)
    g.to_file(path, driver="GeoJSON", COORDINATE_PRECISION=precision)
    return str(path)


def export_tiles(parcels: gpd.GeoDataFrame) -> None:
    p = parcels.copy()
    p["rob"] = p["robustness"].map(ROBUSTNESS_CODES).astype(int)
    p["lm"] = p["largest_m2_mod"].round().astype(int)
    p["v"] = p["vacant"].astype(int)
    tippecanoe(
        C.WEB_DATA / "parcels.pmtiles",
        {"parcels": to_geojson(p, "parcels", ["pid", "rob", "lm", "v"])},
        9,
        16,
        ["--no-feature-limit", "--no-tile-size-limit", "--detect-shared-borders", "--simplification=2"],
    )

    pt = gpd.read_parquet(C.OUT / "patches.parquet")
    pt["s"] = pt["scenario"].map(SCEN_CODES)
    pt["geometry"] = pt.geometry.simplify(0.5)
    tippecanoe(
        C.WEB_DATA / "patches.pmtiles",
        {"patches": to_geojson(pt, "patches", ["pid", "s"])},
        9,
        16,
        ["--no-feature-limit", "--no-tile-size-limit", "--simplification=2"],
    )

    f = A.vec("flood").copy()
    f["z"] = np.select(
        [f["ZONE_SUBTY"] == "FLOODWAY", f["SFHA_TF"] == "T", f["ZONE_SUBTY"].fillna("").str.startswith("0.2")],
        ["floodway", "sfha", "x02"],
        default="",
    )
    f = f[f["z"] != ""]
    w = pd.concat(
        [A.vec("wetlands").assign(t="wetland"), A.vec("waterbodies").assign(t="water")], ignore_index=True
    )
    w = gpd.GeoDataFrame(w, geometry="geometry", crs=C.CRS)
    s = A.vec("streams").copy()
    s["per"] = (s["ARC_CODE"] == 4).astype(int)
    o = A.vec("openspace").copy()
    o["lev"] = o["LEV_PROT"].fillna("X")
    r = A.vec("roads").copy()
    r["cls"] = r["CLASS"].fillna(6).astype(int)
    r["name"] = r["STREETNAME"].fillna("")
    b = A.vec("buildings")
    t = A.vec("town")
    tippecanoe(
        C.WEB_DATA / "context.pmtiles",
        {
            "flood": to_geojson(f, "flood", ["z"]),
            "wetlands": to_geojson(w, "wetlands", ["t"]),
            "streams": to_geojson(s, "streams", ["per"]),
            "protected": to_geojson(o, "protected", ["lev"]),
            "habitat": to_geojson(A.vec("prihab"), "habitat", []),
            "roads": to_geojson(r, "roads", ["cls", "name"]),
            "buildings": to_geojson(b, "buildings", []),
            "town": to_geojson(t.assign(geometry=t.boundary), "town", []),
        },
        9,
        16,
        ["--no-feature-limit", "--no-tile-size-limit", "--simplification=2"],
    )


def hillshade(dem: np.ndarray, cell: float, az=315.0, alt=45.0) -> np.ndarray:
    z = np.where(dem == NODATA, np.nan, dem).astype(np.float64)
    gy, gx = np.gradient(z, cell)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)  # rows increase southwards
    a, e = np.radians(360 - az + 90), np.radians(alt)
    hs = np.sin(e) * np.cos(slope) + np.cos(e) * np.sin(slope) * np.cos(a - aspect)
    return np.nan_to_num(np.clip(hs, 0, 1) * 255, nan=0).astype(np.uint8)


def export_images() -> dict:
    g = A.grid()
    with rasterio.open(C.INTERIM / "dem_2m.tif") as src:
        dem = src.read(1)
    hs = hillshade(dem, g["cell_m"])
    s = A.slope()
    cls = np.zeros(s.shape, dtype=np.uint8)
    for i, thr in enumerate((15, 25, 35), start=1):
        cls[(s != NODATA) & (s >= thr)] = i

    src_t = grid_transform(g)
    bounds = rasterio.transform.array_bounds(g["height"], g["width"], src_t)
    out_res = 5.0  # metres in EPSG:3857 (~3.7 m on the ground at 42.4 N)
    dst_t, w, h = calculate_default_transform(g["crs"], "EPSG:3857", g["width"], g["height"], *bounds, resolution=out_res)

    def warp(arr, resampling, nodata):
        dst = np.full((h, w), nodata, dtype=arr.dtype)
        reproject(arr, dst, src_transform=src_t, src_crs=g["crs"], dst_transform=dst_t, dst_crs="EPSG:3857",
                  resampling=resampling, src_nodata=nodata, dst_nodata=nodata)
        return dst

    hs3 = warp(hs, Resampling.average, 0)
    cl3 = warp(cls, Resampling.nearest, 0)
    with rasterio.open(C.WEB_DATA / "hillshade.jpg", "w", driver="JPEG", width=w, height=h, count=1, dtype="uint8", QUALITY=78) as d:
        d.write(hs3, 1)
    palette = {1: (253, 224, 71, 150), 2: (234, 140, 30, 175), 3: (154, 52, 18, 200)}  # 15-25, 25-35, >=35 %
    rgba = np.zeros((4, h, w), dtype=np.uint8)
    for k, col in palette.items():
        for b_, v in enumerate(col):
            rgba[b_][cl3 == k] = v
    with rasterio.open(C.WEB_DATA / "slope.png", "w", driver="PNG", width=w, height=h, count=4, dtype="uint8", ZLEVEL=9) as d:
        d.write(rgba)
    for aux in C.WEB_DATA.glob("*.aux.xml"):
        aux.unlink()
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    x0, y1 = dst_t.c, dst_t.f
    x1, y0 = x0 + w * dst_t.a, y1 + h * dst_t.e
    corners = [tr.transform(x, y) for x, y in ((x0, y1), (x1, y1), (x1, y0), (x0, y0))]
    return {"coordinates": [[round(a, 6), round(b, 6)] for a, b in corners], "size": [w, h]}


def export_details(parcels: gpd.GeoDataFrame) -> None:
    p = parcels.sort_values("pid")
    bb = p.to_crs(4326).bounds.round(6)
    cats = [c for c in A.BITS if c != "no_data"]
    cols = {
        "pid": p["pid"],
        "loc": p["loc_id"],
        "addr": p["site_addr"].fillna(""),
        "use": p["use_desc"].fillna(""),
        "uc": p["use_code"].fillna(""),
        "zone": p["zoning"].fillna(""),
        "area": p["area_m2"].round(),
        "rob": p["robustness"],
        "yb": p["year_built"].fillna(0).astype(int),
        "condo": p["is_condo"].astype(int),
        # cast before rounding: float32 values otherwise serialize as 4.400000095367432
        "slope": p["slope_mean_pct"].astype("float64").round(1),
        "slope90": p["slope_p90_pct"].astype("float64").round(1),
        "vac": p["vacant"].astype(int),
        "vcode": p["vacant_land_code"].astype(int),
        "bld": p["has_building"].astype(int),
        "front": p["frontage_public_m"].round(),
        "rdist": p["patch_road_dist_m_mod"].round().fillna(-1),
        "road": p["nearest_road_name"].fillna(""),
        "sewer": p["sewer_share"].round(2),
        "bind": p["binding_constraint_mod"],
        "bbox": bb[["minx", "miny", "maxx", "maxy"]].values.tolist(),
    }
    for k in ("con", "mod", "agg"):
        cols[f"el_{k}"] = p[f"eligible_{k}"].astype(int)
        cols[f"lg_{k}"] = p[f"largest_m2_{k}"].round()
        cols[f"nt_{k}"] = p[f"net_m2_{k}"].round()
        cols[f"nv_{k}"] = p[f"naive_m2_{k}"].round()
        cols[f"np_{k}"] = p[f"n_patches_{k}"]
    for c in cats:
        cols[f"c_{c}"] = p[f"c_{c}_m2_mod"].round()
        cols[f"r_{c}"] = p[f"relief_{c}_m2"].round()
    def clean(v):
        v = v if isinstance(v, list) else v.tolist()
        return [None if isinstance(x, float) and np.isnan(x) else x for x in v]

    data = {k: clean(v) for k, v in cols.items()}
    (C.WEB_DATA / "parcels.json").write_text(json.dumps(data, separators=(",", ":"), allow_nan=False))


def export_summary(overlays: dict) -> None:
    summary = json.loads((C.OUT / "summary.json").read_text())
    out = {
        "generated_from": "make all (local pipeline)",
        "scenarios": C.SCENARIOS,
        "scenario_order": list(C.SCENARIO_ORDER),
        "patch_definition": {"open_size_m": C.OPEN_SIZE_CELLS * C.CELL_M, "min_patch_m2": C.MIN_PATCH_M2, "cell_m": C.CELL_M, "connectivity": C.CONNECTIVITY},
        "results": summary,
        "sensitivity": json.loads((C.OUT / "sensitivity.json").read_text()),
        "validation": json.loads((C.OUT / "validation.json").read_text()),
        "benchmark": json.loads((C.ROOT / "benchmarks" / "patch_kernel.json").read_text()),
        "provenance": {
            k: {kk: v.get(kk) for kk in ("url", "features", "acquired_utc", "last_edit_utc", "copyright", "publication_dates", "project")}
            for k, v in json.loads((C.PROVENANCE / "harvest_manifest.json").read_text())["sources"].items()
        },
        "overlays": overlays,
    }
    for v in out["validation"].get("hand_check_sample", []):
        v.pop("figure", None)
    (C.WEB_DATA / "summary.json").write_text(json.dumps(out, indent=1))


def export_downloads(parcels: gpd.GeoDataFrame) -> None:
    d = C.WEB_DATA / "downloads"
    d.mkdir(exist_ok=True)
    keep = [c for c in parcels.columns if c != "geometry" and not c.startswith("cells_")]
    parcels[keep].to_csv(d / "amherst_parcel_screening.csv", index=False)
    parcels[keep + ["geometry"]].to_parquet(d / "amherst_parcel_screening.parquet", compression="zstd")


def main() -> None:
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    C.WEB_DATA.mkdir(parents=True, exist_ok=True)
    parcels = gpd.read_parquet(C.OUT / "parcels.parquet")
    export_tiles(parcels)
    overlays = export_images()
    export_details(parcels)
    export_summary(overlays)
    export_downloads(parcels)
    shutil.rmtree(TMP)
    for f in sorted(C.WEB_DATA.rglob("*")):
        if f.is_file():
            print(f"{f.relative_to(C.WEB_DATA)}  {f.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
