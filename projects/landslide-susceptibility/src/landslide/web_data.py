"""Static data for the local web prototype (PLAN §12): raster tiles, small GeoJSON overlays and summary.json.

* susceptibility.pmtiles - one lossless WebP tile set read by MapLibre as three `raster-dem` sources with the `custom`
  encoding (one colour channel each), coloured client-side by a `color-relief` layer, so the threshold slider is
  a paint-property change, not a computation:
    R = out-of-fold LR rank (held-out view), G = final LR rank (the product), B = slope-alone rank.
  Channel value: 0 = outside the triggered domain, 1 = domain but below the hillslope threshold (not ranked),
  102 - r for a cell in the top r % of hillslope area (r = 1..100 -> 101..2); above 30 % r is rounded up to
  the next 10 % (the slider stops at 30 %).
  Zoom 8..14 in Web Mercator (z14 = 7.8 m ground pixels at 35.7 N: nearest sampling of the 5 m cells, so the
  finest detail is generalised; z15 would be about 4x the payload). Lower zooms average the children's rank
  (weighted by the 5 m cells they stand for) and re-rank the pixels by area at that zoom (see `rerank`), so the
  top k % stays k % of the area at every zoom.
* hillshade.pmtiles - own 2017 lidar hillshade (JPEG), the only basemap (DESIGN_DECISIONS D10).
* overlays: county outlines, the area not tested by Helene's rainfall, HUC-12 outlines, mapped primary
  initiation sites (NCGS, credit required) - GeoJSON.
* summary.json - every number the page shows, from validation/*.json.
"""

from __future__ import annotations

import json
import math
import warnings

import geopandas as gpd
import numpy as np
import rasterio
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer
from rasterio.enums import Resampling
from rasterio.features import shapes
from rasterio.io import MemoryFile
from rasterio.warp import reproject
from shapely.geometry import shape as to_shape

from . import config as C
from .inventory import positive_mask
from .labels import REGION, counties, inventory, read

WEB = C.ROOT / "web" / "data"
SCORES = C.INTERIM / f"scores_{REGION}"
MIN_Z, MAX_Z, HS_MAX_Z = 8, 14, 13
R = 20037508.342789244
warnings.filterwarnings("ignore", category=rasterio.errors.NotGeoreferencedWarning)


def tile_size(z: int) -> float:
    return 2 * R / 2 ** z


def grid_for(z: int, bounds3857) -> tuple[rasterio.Affine, int, int, int, int]:
    """Tile-aligned pixel grid at zoom z covering the bounds; returns transform, width, height, x0, y0 (tiles)."""
    t = tile_size(z)
    x0, x1 = math.floor((bounds3857[0] + R) / t), math.ceil((bounds3857[2] + R) / t)
    y0, y1 = math.floor((R - bounds3857[3]) / t), math.ceil((R - bounds3857[1]) / t)
    px = t / 256
    tr = rasterio.Affine(px, 0, -R + x0 * t, 0, -px, R - y0 * t)
    return tr, (x1 - x0) * 256, (y1 - y0) * 256, x0, y0


def warp(src_path, tr, w, h, resampling=Resampling.nearest, dtype=None):
    with rasterio.open(src_path) as s:
        out = np.zeros((h, w), dtype or s.dtypes[0])
        reproject(rasterio.band(s, 1), out, dst_transform=tr, dst_crs="EPSG:3857", resampling=resampling,
                  dst_nodata=0 if np.issubdtype(out.dtype, np.integer) else np.nan)
    return out


SLIDER_MAX = 30  # 1 % classes up to the slider maximum; coarser 10 % classes beyond (payload)


def encode(rank: np.ndarray, dom: np.ndarray) -> np.ndarray:
    r = rank.astype(np.int16)
    r = np.where(r > SLIDER_MAX, np.ceil(r / 10) * 10, r).astype(np.int16)
    e = np.where(rank > 0, 102 - r, np.where(dom, 1, 0))
    return e.astype(np.uint8)


def reduce2(m: np.ndarray, n: np.ndarray, d: np.ndarray):
    """Next lower zoom: count-weighted mean of the children's score proxy, summed ranked-cell count, any-domain."""
    h, w = m.shape[0] // 2, m.shape[1] // 2
    q = lambda a: a[:2 * h, :2 * w].reshape(h, 2, w, 2)
    nn = q(n).sum((1, 3))
    mm = np.where(nn > 0, (q(m) * q(n)).sum((1, 3)) / np.maximum(nn, 1), 0).astype(np.float32)
    return mm, nn.astype(np.float32), q(d).any((1, 3))


def rerank(m: np.ndarray, n: np.ndarray, d: np.ndarray) -> np.ndarray:
    """Encode one zoom level: pixels re-ranked by their (generalised) score, weighted by the 5 m-cell count they
    stand for, so "top k % of hillslope area" keeps its meaning at every zoom (averaged ranks would drift to the
    middle and nothing would reach the top classes at overview zooms)."""
    ok = n > 0
    v, wt = m[ok], n[ok].astype(np.float64)
    o = np.argsort(-v, kind="stable")
    cum = np.empty(v.size)
    cum[o] = np.cumsum(wt[o])
    r = np.zeros(m.shape, np.int16)
    r[ok] = np.clip(np.ceil(cum / wt.sum() * 100), 1, 100)
    return encode(r, d)


def webp_lossless(arr: np.ndarray) -> bytes:
    """Lossless WebP: exact channel values (verified by a round-trip test), ~40 % smaller than PNG here."""
    with MemoryFile() as mf:
        with mf.open(driver="WEBP", width=arr.shape[-1], height=arr.shape[-2], count=arr.shape[0], dtype="uint8",
                     LOSSLESS=True, QUALITY=100) as d:
            d.write(arr)
        return mf.read()


def jpeg(arr: np.ndarray) -> bytes:
    with MemoryFile() as mf:
        with mf.open(driver="JPEG", width=arr.shape[-1], height=arr.shape[-2], count=1, dtype="uint8",
                     QUALITY=78) as d:
            d.write(arr[None])
        return mf.read()


def write_pmtiles(path, tiles: dict, tile_type, minz, maxz, bounds_ll, meta: dict) -> dict:
    with open(path, "wb") as f:
        wr = Writer(f)
        for tid in sorted(tiles):
            wr.write_tile(tid, tiles[tid])
        lon = (bounds_ll[0] + bounds_ll[2]) / 2
        lat = (bounds_ll[1] + bounds_ll[3]) / 2
        wr.finalize({"tile_type": tile_type, "tile_compression": Compression.NONE, "min_zoom": minz, "max_zoom": maxz,
                     "min_lon_e7": int(bounds_ll[0] * 1e7), "min_lat_e7": int(bounds_ll[1] * 1e7),
                     "max_lon_e7": int(bounds_ll[2] * 1e7), "max_lat_e7": int(bounds_ll[3] * 1e7),
                     "center_zoom": 10, "center_lon_e7": int(lon * 1e7), "center_lat_e7": int(lat * 1e7)}, meta)
    return {"tiles": len(tiles), "bytes": path.stat().st_size}


def cut(levels: dict, x0s: dict, y0s: dict, encoder) -> dict:
    tiles = {}
    for z, a in levels.items():
        nty, ntx = a.shape[-2] // 256, a.shape[-1] // 256
        for ty in range(nty):
            for tx in range(ntx):
                blk = a[..., ty * 256:(ty + 1) * 256, tx * 256:(tx + 1) * 256]
                if not blk.any():
                    continue
                tiles[zxy_to_tileid(z, x0s[z] + tx, y0s[z] + ty)] = encoder(blk)
    return tiles


def aoi_bounds():
    cty = counties()
    b3857 = cty.to_crs(3857).total_bounds
    return cty, b3857, cty.to_crs(4326).total_bounds


def susceptibility_tiles() -> dict:
    cty, b3857, bll = aoi_bounds()
    tr, w, h, x0, y0 = grid_for(MAX_Z, b3857)
    dom = warp(C.INTERIM / f"labels_{REGION}" / "domain.tif", tr, w, h) > 0
    state = []
    for name in ("oof_lr", "final_lr", "slope"):
        rk = warp(SCORES / f"rank_{name}.tif", tr, w, h)
        state.append(((102 - rk.astype(np.float32)) * (rk > 0), (rk > 0).astype(np.float32), dom))
    del dom
    levels = {MAX_Z: np.stack([rerank(*st) for st in state])}
    x0s, y0s = {MAX_Z: x0}, {MAX_Z: y0}
    for z in range(MAX_Z - 1, MIN_Z - 1, -1):
        # parent grid: the child grid starts at an even tile only if x0 is even; pad by one tile when odd
        px, py = x0s[z + 1] % 2, y0s[z + 1] % 2

        def pad(a):
            a = np.pad(a, ((py * 256, 0), (px * 256, 0)))
            return np.pad(a, ((0, (a.shape[0] // 256) % 2 * 256), (0, (a.shape[1] // 256) % 2 * 256)))

        state = [reduce2(*(pad(a) for a in st)) for st in state]
        levels[z] = np.stack([rerank(*st) for st in state])
        x0s[z], y0s[z] = (x0s[z + 1] - px) // 2, (y0s[z + 1] - py) // 2
    tiles = cut(levels, x0s, y0s, webp_lossless)
    return write_pmtiles(WEB / "susceptibility.pmtiles", tiles, TileType.WEBP, MIN_Z, MAX_Z, bll,
                         {"name": "Relative landslide-initiation susceptibility (preliminary)",
                          "encoding": "R=held-out LR rank, G=final LR rank, B=slope rank; 0 outside domain, "
                                      "1 not ranked, 102-r = top r % of hillslope area at that zoom"})


def hillshade(z: np.ndarray, cell: float, az=315.0, alt=45.0) -> np.ndarray:
    gy, gx = np.gradient(z, cell)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    a, e = np.deg2rad(az), np.deg2rad(alt)
    hs = np.sin(e) * np.cos(slope) + np.cos(e) * np.sin(slope) * np.cos(a - aspect)
    return np.clip(hs * 255, 0, 255)


def hillshade_tiles() -> dict:
    cty, b3857, bll = aoi_bounds()
    tr, w, h, x0, y0 = grid_for(HS_MAX_Z, b3857)
    dem = warp(C.INTERIM / f"dem_5m_{REGION}.tif", tr, w, h, Resampling.average, np.float32)
    ok = np.isfinite(dem) & (dem > -1000)
    lat = math.degrees(2 * math.atan(math.exp((b3857[1] + b3857[3]) / 2 / R * math.pi)) - math.pi / 2)
    hs = hillshade(np.where(ok, dem, np.nanmedian(dem[ok])), tr.a * math.cos(math.radians(lat)))
    # soften toward paper white so the susceptibility ramp reads on top (D8 light theme)
    g = (150 + 0.42 * hs).astype(np.uint8)
    g[~ok] = 247  # paper colour (D8) outside lidar coverage; JPEG has no transparency
    levels, x0s, y0s = {HS_MAX_Z: g}, {HS_MAX_Z: x0}, {HS_MAX_Z: y0}
    for z in range(HS_MAX_Z - 1, MIN_Z - 1, -1):
        a = levels[z + 1].astype(np.float32)
        px, py = x0s[z + 1] % 2, y0s[z + 1] % 2
        a = np.pad(a, ((py * 256, 0), (px * 256, 0)), constant_values=247)
        a = np.pad(a, ((0, (a.shape[0] // 256) % 2 * 256), (0, (a.shape[1] // 256) % 2 * 256)), constant_values=247)
        hh, ww = a.shape[0] // 2, a.shape[1] // 2
        levels[z] = a.reshape(hh, 2, ww, 2).mean((1, 3)).astype(np.uint8)
        x0s[z], y0s[z] = (x0s[z + 1] - px) // 2, (y0s[z + 1] - py) // 2
    tiles = cut(levels, x0s, y0s, jpeg)
    return write_pmtiles(WEB / "hillshade.pmtiles", tiles, TileType.JPEG, MIN_Z, HS_MAX_Z, bll,
                         {"name": "Hillshade from USGS 3DEP 1 m lidar (2016-17), 5 m mean"})


def overlays() -> dict:
    cty = counties()
    out = {}
    cty[["NAME", "geometry"]].to_crs(4326).to_file(WEB / "counties.geojson", driver="GeoJSON",
                                                    COORDINATE_PRECISION=5)
    # area not tested by Helene's rainfall: county area minus the triggered domain (100 m generalisation)
    with rasterio.open(C.INTERIM / f"stack_{REGION}" / "rain_mm.tif") as s:
        f = 20
        rain = s.read(1, out_shape=(s.height // f, s.width // f), resampling=Resampling.average)
        tr = s.transform * rasterio.Affine.scale(s.width / rain.shape[1], s.height / rain.shape[0])
    low = ((rain < C.TRIGGER_MM) & (rain > -1)).astype(np.uint8)
    polys = [to_shape(g) for g, v in shapes(low, mask=low > 0, transform=tr) if v == 1]
    nt = gpd.GeoDataFrame(geometry=polys, crs=C.CRS).union_all().intersection(cty.union_all())
    nt = gpd.GeoSeries([nt], crs=C.CRS).simplify(50).to_crs(4326)
    gpd.GeoDataFrame({"label": ["not tested by Helene's rainfall"]}, geometry=nt).to_file(
        WEB / "not_tested.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)
    huc = gpd.read_parquet(C.RAW / "huc12.parquet").to_crs(C.CRS)
    huc = huc[huc.intersects(cty.union_all())][["huc12", "name", "geometry"]]
    huc.assign(geometry=huc.simplify(30)).to_crs(4326).to_file(WEB / "huc12.geojson", driver="GeoJSON",
                                                               COORDINATE_PRECISION=5)
    # outside the area of applicability (M6, 50 m lattice): polygons, generalised
    with rasterio.open(SCORES / "aoa_50m.tif") as a:
        flag, tra = a.read(1), a.transform
    out_ = (flag == 2).astype(np.uint8)
    polys = [to_shape(g) for g, v in shapes(out_, mask=out_ > 0, transform=tra) if v == 1]
    aoa = gpd.GeoSeries(polys, crs=C.CRS).buffer(25).union_all().buffer(-10).simplify(20)
    gpd.GeoDataFrame({"label": ["outside the area of applicability"]}, geometry=[aoa], crs=C.CRS).to_crs(4326) \
        .to_file(WEB / "outside_aoa.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)
    inv = inventory()
    p = inv[positive_mask(inv)].copy()
    p["geometry"] = p.geometry.representative_point()
    p = p[p.within(cty.union_all())]
    gpd.GeoDataFrame(geometry=p.geometry, crs=C.CRS).to_crs(4326).to_file(
        WEB / "initiations.geojson", driver="GeoJSON", COORDINATE_PRECISION=6)
    out["initiation_points"] = int(len(p))
    out["huc12"] = int(len(huc))
    return out


def summary(tiles: dict, ov: dict) -> dict:
    v = C.VALIDATION
    m4 = json.loads((v / "m4_baseline.json").read_text())
    m5 = json.loads((v / "m5_advanced.json").read_text())
    pk = json.loads((v / "per_k_metrics.json").read_text())
    lab = json.loads((C.INTERIM / f"labels_{REGION}" / "report.json").read_text())
    P = m5["pixels"]["scores"]
    s = {
        "status": "preliminary",
        "generated_from": ["validation/m4_baseline.json", "validation/m5_advanced.json", "validation/per_k_metrics.json"],
        "event": {"name": "Hurricane Helene", "date": "2024-09-27"},
        "domain": {"km2": round(lab["domain"]["triggered_valid_km2"]), "trigger_mm": C.TRIGGER_MM,
                   "hillslope_threshold_deg": round(lab["domain"]["slope_p1_of_positive_cells_deg"], 1),
                   "rain_reference_mm": round(pk["rain_reference_mm"])},
        "sites": {"primary_polygons": lab["positive_polygons"], "in_domain": pk["sites_in_domain"]},
        "bounds_lonlat": [round(float(v), 5) for v in counties().to_crs(4326).total_bounds],
        "hillslope_km2": round(pk["hillslope_cells_ranked"]["final_lr"] * C.CELL_M ** 2 / 1e6, 1),
        "per_k": {"k_pct": pk["k_pct"], **{k: pk[k] for k in ("oof_lr", "oof_gbm", "slope")}},
        "cells_auc": {k: {"within_huc": P[k]["auc_within_huc"], "rain_stratified": P[k]["auc_rain_stratified"]}
                      for k in ("lr", "gbm", "slope")},
        "gbm_minus_lr_cells": m5["pixels"]["C1_delta_gbm_minus_lr"],
        "units": {"lr_cell_agg_minus_slope": m5["units"]["C2_delta_vs_slope"]["c_cell_lr_agg"]},
        "validation": {"folds": "leave-one-HUC-12-out, 500 m buffer", "watersheds_with_positives":
                       sum(1 for h in m4["units"]["primary"]["per_huc"] if h["positive_units"] > 0),
                       "replicate_watersheds": m4["units"]["primary"]["replicates"]["n"],
                       "random_split_auc_cells": m4["pixels"]["primary"]["design_contrasts"]["random_5fold"]["auc_rain_stratified"]["value"]},
        "tiles": tiles, "overlays": ov,
    }
    m6u = json.loads((v / "m6_uncertainty.json").read_text())
    m6s = json.loads((v / "m6_sensitivity.json").read_text())
    m6w = json.loads((v / "m6_watauga.json").read_text())
    ng = json.loads((v / "nogeo_test.json").read_text())
    s["m6"] = {
        "top10_stable_share": m6u["ensemble"]["final_top10_stays_in_top10_in_90pct_of_refits"],
        "outside_aoa_share": m6u["area_of_applicability"]["share_outside_aoa"],
        "loco_auc_rain_stratified": m6s["leave_one_county_out"]["auc_rain_stratified"],
        "watauga_transfer_auc": m6w["transfer_aoi_model"]["auc"], "watauga_transfer_ci95": m6w["transfer_aoi_model"]["ci95"],
        "no_geology_adopted": ng["decision"]["replace_current_model"],
        "no_geology_watauga_auc": ng["watauga"]["transfer_no_geology"]["auc"],
        "top10_share_geology3": ng["ranking_and_stability"]["top10_share_by_geology"]["current"].get("3", 0),
        "hillslope_share_geology3": ng["ranking_and_stability"]["hillslope_share_by_geology"].get("3", 0),
    }
    (WEB / "summary.json").write_text(json.dumps(s, indent=1))
    return s


def run() -> dict:
    WEB.mkdir(parents=True, exist_ok=True)
    t = {"susceptibility": susceptibility_tiles(), "hillshade": hillshade_tiles()}
    print(t, flush=True)
    ov = overlays()
    return summary(t, ov)


if __name__ == "__main__":
    run()
