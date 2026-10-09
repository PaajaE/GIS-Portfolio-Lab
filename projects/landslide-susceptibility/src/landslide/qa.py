"""M1 data QA: checks every harvested source and writes validation/M1_DATA_QA.md + m1_data_qa.json.

Each check reports what was verified and how; failures are listed, not hidden. Numbers in the report
come from the files on disk and the provenance manifest.
"""

from __future__ import annotations

import hashlib
import json
import shutil

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterio.features

from . import config as C
from .inventory import normalise, positive_mask

# Expected figures from the 2026-10-08 feasibility queries (PLAN §0 / §0b); the snapshot must match.
EXPECTED = {"positives_aoi": 2962, "positives_buncombe": 1806, "positives_yancey": 1156}
ELEV_RANGE_M = (150.0, 2040.0)  # French Broad valley ~ 400 m; Mount Mitchell 2,037 m


def _fmt(d: dict) -> str:
    return ", ".join(f"{k}: {v:,}" if isinstance(v, (int, np.integer)) else f"{k}: {v}" for k, v in d.items())


def check_inventory(rep: dict):
    raw = gpd.read_parquet(C.RAW / "ncgs_features.parquet")
    inv = normalise(raw).to_crs(C.CRS)
    cty = gpd.read_parquet(C.RAW / "counties.parquet").to_crs(C.CRS)
    pts = inv.set_geometry(inv.geometry.representative_point())
    j = gpd.sjoin(pts, cty[["NAME", "geometry"]], predicate="within", how="left")
    j = j[~j.index.duplicated()]
    inv["county"] = j["NAME"]
    pos = positive_mask(inv)
    geom_hash = raw.geometry.to_wkb().map(lambda b: hashlib.sha1(b).hexdigest())
    r = {
        "n_features_bbox": len(inv),
        "by_event": inv["event"].value_counts().to_dict(),
        "by_feature_type": inv["FeatureType"].fillna("NA").value_counts().to_dict(),
        "invalid_geometries": int((~inv.is_valid).sum()),
        "empty_geometries": int(inv.geometry.is_empty.sum()),
        "duplicate_geometries": int(geom_hash.duplicated().sum()),
        "positives_by_county": inv.loc[pos, "county"].value_counts().to_dict(),
        "exist_conf_unparsed": int(inv["ExistenceConfidence"].notna().sum() - inv["exist_conf"].notna().sum()),
        "loc_conf_unparsed": int(inv["LocationConfidence"].notna().sum() - inv["loc_conf"].notna().sum()),
    }
    pa = inv.loc[pos & inv["county"].isin(C.REGIONS["aoi"])]
    r["positives_aoi"] = len(pa)
    r["positive_area_m2"] = {"median": round(float(pa.area.median()), 1), "p95": round(float(pa.area.quantile(0.95)), 1)}
    exp_ok = (r["positives_aoi"] == EXPECTED["positives_aoi"]
              and r["positives_by_county"].get("Buncombe County") == EXPECTED["positives_buncombe"]
              and r["positives_by_county"].get("Yancey County") == EXPECTED["positives_yancey"])
    r["matches_feasibility_counts"] = bool(exp_ok)
    # Undated features in the AOI: become exclusion zones, never positives or negatives
    r["undated_in_aoi"] = int((inv["event"].eq("undated") & inv["county"].isin(C.REGIONS["aoi"])).sum())
    rep["inventory"] = r


def check_dem(rep: dict, manifest: dict):
    r = {}
    for region in C.REGIONS:
        rec = manifest["sources"].get(f"dem_tiles_{region}")
        if not rec or "mosaic" not in rec:
            r[region] = "not harvested"
            continue
        tiles = pd.DataFrame(rec["tiles"]).T
        beg = pd.to_datetime(tiles["lidar_begdate"], format="%Y%m%d", errors="coerce")
        end = pd.to_datetime(tiles["lidar_enddate"], format="%Y%m%d", errors="coerce")
        cty = gpd.read_parquet(C.RAW / "counties.parquet").to_crs(C.CRS)
        poly = cty[cty["NAME"].isin(C.REGIONS[region])].union_all()
        with rasterio.open(C.ROOT / rec["mosaic"]["path"]) as s:
            a = s.read(1)
            inside = ~rasterio.features.geometry_mask([poly], a.shape, s.transform)
            inside_b = ~rasterio.features.geometry_mask([poly.buffer(C.BUFFER_M)], a.shape, s.transform)
            v = a[inside]
            crs_ok, res = s.crs.to_epsg() == 26917, s.res
            origin_ok = s.transform.c % C.CELL_M == 0 and s.transform.f % C.CELL_M == 0
        valid = v[v != C.OUT_NODATA]
        r[region] = {
            "tiles": len(tiles), "projects": tiles["project"].value_counts().to_dict(),
            "lidar_dates_by_project": {p: [str(beg[tiles["project"] == p].min().date()) if beg[tiles["project"] == p].notna().any() else None,
                                           str(end[tiles["project"] == p].max().date()) if end[tiles["project"] == p].notna().any() else None]
                                       for p in tiles["project"].unique()},
            "tiles_without_dates": int(beg.isna().sum()),
            "latest_lidar_date": str(end.max().date()) if end.notna().any() else None,
            "transfer_gb": round(tiles["bytes_1m"].astype(float).sum() / 1e9, 2),
            "crs_26917": bool(crs_ok), "res": list(res), "origin_on_5m_lattice": bool(origin_ok),
            "nodata_share_in_counties": float((v == C.OUT_NODATA).mean()),
            "nodata_share_in_buffer": float((a[inside_b] == C.OUT_NODATA).mean()),
            "elev_min_max_m": [float(valid.min()), float(valid.max())],
            "elev_in_plausible_range": bool(ELEV_RANGE_M[0] <= valid.min() and valid.max() <= ELEV_RANGE_M[1]),
            "worst_seam_p99_abs_m": max(sd.get("p99_abs_m", 0) for sd in rec["mosaic"]["seams"]),
            "worst_seam_share_gt_1m": max(sd.get("share_gt_1m", 0) for sd in rec["mosaic"]["seams"]),
            "max_seam_diff_m": max(sd.get("max_abs_diff_m", 0) for sd in rec["mosaic"]["seams"]),
            "seams_p99_gt_20cm": [sd["tile"] for sd in rec["mosaic"]["seams"] if sd.get("p99_abs_m", 0) > 0.2],
        }
        r[region]["pre_event"] = bool(r[region]["latest_lidar_date"] and r[region]["latest_lidar_date"] < "2024-09-25")
    rep["dem"] = r


def check_rasters(rep: dict):
    r = {}
    for f in C.MRMS_FILES:
        with rasterio.open(C.RAW / f.removesuffix(".gz")) as s:
            a = s.read(1)
            r[f[-26:-8]] = {"driver": s.driver, "unit": s.tags(1).get("GRIB_UNIT"), "res_deg": s.res[0],
                            "valid_max_mm": float(a.max()), "missing_cells": int((a < 0).sum())}
    for key in C.MRLC_COVERAGES:
        for region in C.REGIONS:
            with rasterio.open(C.RAW / f"{key}_{region}.tif") as s:
                a = s.read(1)
                r[f"{key}_{region}"] = {"epsg": s.crs.to_epsg(), "res": list(s.res), "shape": list(a.shape),
                                        "declared_nodata": s.nodata, "n_values": int(len(np.unique(a))),
                                        "max": int(a.max()), "zero_share": float((a == 0).mean())}
    rep["rasters"] = r


def check_vectors(rep: dict):
    r = {}
    cty = gpd.read_parquet(C.RAW / "counties.parquet")
    r["counties"] = cty["NAME"].tolist()
    for name in ("huc12", "huc10", "geology_1985", "ncgs_observations", "ncgs_ground_ruptures"):
        g = gpd.read_parquet(C.RAW / f"{name}.parquet")
        r[name] = {"n": len(g), "invalid": int((~g.is_valid).sum()), "epsg": g.crs.to_epsg()}
    bpath = C.RAW / "nc_buildings.parquet"
    if bpath.exists():
        b = gpd.read_parquet(bpath)
        r["buildings"] = {"n": len(b), "invalid": int((~b.is_valid).sum()), "licence": "not stated (local only)"}
    for p in sorted(C.RAW.glob("ssurgo_*.parquet")):
        g = gpd.read_parquet(p)
        r[p.stem] = {"n": len(g), "invalid": int((~g.is_valid).sum()),
                     "brockdepmin_null_share": float(g["brockdepmin"].isna().mean()),
                     "hydgrpdcd_null_share": float(g["hydgrpdcd"].isna().mean())}
    for p in sorted(C.RAW.glob("tl_2024_*_roads.zip")):
        g = gpd.read_file(p)
        r[p.stem] = {"n": len(g), "epsg": g.crs.to_epsg()}
    rep["vectors"] = r


def run() -> dict:
    manifest = json.loads((C.PROVENANCE / "harvest_manifest.json").read_text())
    rep: dict = {}
    check_inventory(rep)
    check_dem(rep, manifest)
    check_rasters(rep)
    check_vectors(rep)
    rep["disk"] = {"data_gb": round(sum(f.stat().st_size for f in C.DATA.rglob("*") if f.is_file()) / 1e9, 2),
                   "free_gb": round(shutil.disk_usage(C.ROOT).free / 1e9, 1)}
    (C.VALIDATION / "m1_data_qa.json").write_text(json.dumps(rep, indent=1, default=str))
    write_md(rep, manifest)
    return rep


def write_md(rep: dict, manifest: dict):
    inv, dem, ras, vec = rep["inventory"], rep["dem"], rep["rasters"], rep["vectors"]
    L = ["# M1 data QA", "",
         "Generated by `make qa` (`landslide.qa`) from the files in `data/raw`, `data/interim` and",
         "`provenance/harvest_manifest.json`. Machine-readable: `m1_data_qa.json`.", "",
         "## Inventory snapshot (NCGS)", "",
         f"- Service last edit: {manifest['sources']['ncgs_features'].get('service_last_edit_utc')}; "
         f"acquired {manifest['sources']['ncgs_features']['acquired_utc']}; sha256 "
         f"`{manifest['sources']['ncgs_features']['sha256'][:16]}…`",
         f"- Features in harvest bbox: {inv['n_features_bbox']:,}. By event: {_fmt(inv['by_event'])}",
         f"- Positives (natural source areas, existence + location confidence High/Moderate) in the AOI: "
         f"**{inv['positives_aoi']:,}** ({_fmt(inv['positives_by_county'])}); "
         f"matches feasibility counts: **{inv['matches_feasibility_counts']}**",
         f"- Positive polygon area: median {inv['positive_area_m2']['median']} m², p95 {inv['positive_area_m2']['p95']} m²",
         f"- Geometry: invalid {inv['invalid_geometries']}, empty {inv['empty_geometries']}, exact duplicates "
         f"{inv['duplicate_geometries']}; confidence strings not parsed: existence {inv['exist_conf_unparsed']}, "
         f"location {inv['loc_conf_unparsed']}",
         f"- Undated features in AOI (exclusion zones only): {inv['undated_in_aoi']}", "",
         "## DEM (3DEP 1 m → 5 m block mean)", ""]
    for region, d in dem.items():
        if isinstance(d, str):
            L.append(f"- {region}: {d}")
            continue
        L += [f"**{region}** — {d['tiles']} tiles ({_fmt(d['projects'])}), {d['transfer_gb']} GB transferred",
              f"- Lidar collection dates by project: " + "; ".join(f"{p}: {a} → {b}" for p, (a, b) in d['lidar_dates_by_project'].items())
              + f"; tiles without dates: {d['tiles_without_dates']}; **all pre-event: {d['pre_event']}**",
              f"- CRS EPSG:26917: {d['crs_26917']}; resolution {d['res']}; origin on 5 m lattice: {d['origin_on_5m_lattice']}",
              f"- Nodata share inside counties: {d['nodata_share_in_counties']:.5f}; inside 2 km buffer: {d['nodata_share_in_buffer']:.5f}",
              f"- Elevation {d['elev_min_max_m'][0]:.1f}–{d['elev_min_max_m'][1]:.1f} m (plausible: {d['elev_in_plausible_range']})",
              f"- Seams between overlapping tiles: worst p99 |diff| {d['worst_seam_p99_abs_m']:.3f} m, worst share > 1 m "
              f"{d['worst_seam_share_gt_1m']:.4f}, max {d['max_seam_diff_m']:.2f} m; tiles with p99 > 20 cm: "
              f"{', '.join(d['seams_p99_gt_20cm']) or 'none'}. Where tiles overlap, `config.DEM_PROJECT_PRIORITY` decides (NC Phase 5 > NC Phase 4 > TN).", ""]
    L += ["## Rasters", ""]
    for k, v in ras.items():
        L.append(f"- `{k}`: {_fmt(v)}")
    L += ["", "## Vectors", ""]
    for k, v in vec.items():
        L.append(f"- `{k}`: {v if not isinstance(v, dict) else _fmt(v)}")
    L += ["", f"## Disk", "", f"- data/: {rep['disk']['data_gb']} GB; free: {rep['disk']['free_gb']} GB", ""]
    (C.VALIDATION / "M1_DATA_QA.md").write_text("\n".join(L))


if __name__ == "__main__":
    run()
    print((C.VALIDATION / "M1_DATA_QA.md").read_text())
