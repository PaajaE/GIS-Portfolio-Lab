"""Download source data into data/raw/ and record provenance in provenance/harvest_manifest.json.

`python -m landslide.harvest small`  boundaries, WBD, inventory snapshot, MRMS, geology, NLCD/canopy,
                                      SSURGO, TIGER roads, building footprints (local use only)
`python -m landslide.harvest dem`    3DEP 1 m tiles -> 5 m block means (download, aggregate, delete),
                                      tile metadata, one mosaic per region

ArcGIS layers are queried by object id in chunks so server transfer limits cannot drop records. Large
DEM tiles are processed one at a time; at most one raw tile is on disk.
"""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import io
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from shapely import wkt
from shapely.geometry import box

from . import config as C
from .dem import block_mean, lattice_window, paste_first_valid, seam_stats

UA = {"User-Agent": "landslide-susceptibility/0.1 (research; local pipeline)"}
NOW = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


# --- helpers --------------------------------------------------------------------------------
def _get(url: str, data: dict | None = None, retries: int = 5, timeout: int = 300) -> bytes:
    body = urllib.parse.urlencode(data).encode() if data else None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("unreachable")


def _json(url: str, data: dict | None = None) -> dict:
    out = json.loads(_get(url, data))
    if isinstance(out, dict) and "error" in out:
        raise RuntimeError(f"{url}: {out['error']}")
    return out


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _manifest() -> dict:
    p = C.PROVENANCE / "harvest_manifest.json"
    return json.loads(p.read_text()) if p.exists() else {"sources": {}}


_TOUCHED: set[str] = set()  # manifest keys written by this process (merge-on-save, so `small` and `dem` can run together)


def _save_manifest(m: dict) -> None:
    C.PROVENANCE.mkdir(parents=True, exist_ok=True)
    cur = _manifest()
    for k in _TOUCHED:
        cur["sources"][k] = m["sources"][k]
    cur["updated_utc"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    tmp = C.PROVENANCE / "harvest_manifest.json.tmp"
    tmp.write_text(json.dumps(cur, indent=1, sort_keys=True))
    tmp.replace(C.PROVENANCE / "harvest_manifest.json")


def _record(m: dict, key: str, path, **info) -> None:
    _TOUCHED.add(key)
    m["sources"][key] = {"path": str(path.relative_to(C.ROOT)), "sha256": _sha256(path),
                         "bytes": path.stat().st_size, "acquired_utc": NOW, **info}


def query_layer(layer_url: str, where: str = "1=1", bbox4326=None, out_fields: str = "*") -> gpd.GeoDataFrame:
    """All features of an ArcGIS layer as WGS84 GeoDataFrame, fetched by object-id chunks."""
    base = {"where": where, "f": "json"}
    if bbox4326 is not None:
        base |= {"geometry": ",".join(map(str, bbox4326)), "geometryType": "esriGeometryEnvelope",
                 "inSR": 4326, "spatialRel": "esriSpatialRelIntersects"}
    ids = _json(f"{layer_url}/query", base | {"returnIdsOnly": "true"})
    oid, oids = ids["objectIdFieldName"], sorted(ids.get("objectIds") or [])
    parts = []
    for i in range(0, len(oids), 500):
        chunk = ",".join(map(str, oids[i : i + 500]))
        js = _get(f"{layer_url}/query", {"objectIds": chunk, "outFields": out_fields, "outSR": 4326,
                                         "returnGeometry": "true", "f": "geojson"})
        if js[:200].lstrip().startswith(b'{"error"'):
            raise RuntimeError(f"{layer_url}: {js[:300]!r}")
        parts.append(gpd.read_file(io.BytesIO(js)))
    if not parts:
        return gpd.GeoDataFrame(geometry=[], crs=4326)
    gdf = pd.concat(parts, ignore_index=True).set_crs(4326, allow_override=True)
    if len(gdf) != len(oids):
        raise RuntimeError(f"{layer_url}: expected {len(oids)} features, got {len(gdf)}")
    return gdf.sort_values(oid).reset_index(drop=True) if oid in gdf else gdf


def regions() -> dict[str, gpd.GeoDataFrame]:
    """County polygons per region (EPSG:26917), from the harvested county file."""
    cty = gpd.read_parquet(C.RAW / "counties.parquet").to_crs(C.CRS)
    return {r: cty[cty["NAME"].isin(names)] for r, names in C.REGIONS.items()}


def region_bounds(buffer_m: float = C.BUFFER_M) -> dict[str, tuple]:
    """Buffered region bounds in EPSG:26917, snapped outward to the 5 m lattice."""
    out = {}
    for r, g in regions().items():
        x0, y0, x1, y1 = g.union_all().buffer(buffer_m).bounds
        c = C.CELL_M
        out[r] = (np.floor(x0 / c) * c, np.floor(y0 / c) * c, np.ceil(x1 / c) * c, np.ceil(y1 / c) * c)
    return out


def bbox4326_all() -> tuple:
    polys = [box(*b) for b in region_bounds().values()]
    return tuple(gpd.GeoSeries(polys, crs=C.CRS).to_crs(4326).union_all().bounds)


# --- small sources --------------------------------------------------------------------------
def harvest_counties(m):
    names = [n for names in C.REGIONS.values() for n in names]
    where = f"STATE='{C.STATE_FIPS}' AND NAME IN ({','.join(repr(n) for n in names)})".replace('"', "'")
    g = query_layer(C.TIGER_COUNTIES, where, out_fields="NAME,GEOID,STATE,COUNTY")
    assert sorted(g["NAME"]) == sorted(names), g["NAME"].tolist()
    p = C.RAW / "counties.parquet"
    g.to_parquet(p)
    _record(m, "counties", p, url=C.TIGER_COUNTIES, where=where, n=len(g))


def harvest_wbd(m):
    bb = bbox4326_all()
    for layer, name in ((6, "huc12"), (5, "huc10")):
        url = f"{C.WBD}/{layer}"
        g = query_layer(url, bbox4326=bb, out_fields=f"{name},name,areasqkm,loaddate,states")
        p = C.RAW / f"{name}.parquet"
        g.to_parquet(p)
        _record(m, name, p, url=url, bbox4326=bb, n=len(g))


def harvest_inventory(m):
    bb = bbox4326_all()
    for layer, name in C.NCGS_INVENTORY_LAYERS.items():
        url = f"{C.NCGS_INVENTORY}/{layer}"
        meta = _json(url, {"f": "json"})
        g = query_layer(url, bbox4326=bb)
        p = C.RAW / f"ncgs_{name}.parquet"
        g.to_parquet(p)
        _record(m, f"ncgs_{name}", p, url=url, bbox4326=bb, n=len(g),
                service_last_edit_utc=dt.datetime.fromtimestamp(
                    meta["editingInfo"]["dataLastEditDate"] / 1000, dt.UTC).isoformat(timespec="seconds"))


def harvest_geology(m):
    g = query_layer(C.NCGS_GEOLOGY, bbox4326=bbox4326_all())
    p = C.RAW / "geology_1985.parquet"
    g.to_parquet(p)
    _record(m, "geology", p, url=C.NCGS_GEOLOGY, n=len(g))


def harvest_buildings(m):
    """Exposure is computed for the AOI only, so footprints are fetched for the buffered AOI bbox."""
    bb = tuple(gpd.GeoSeries([box(*region_bounds()["aoi"])], crs=C.CRS).to_crs(4326).total_bounds)
    g = query_layer(C.NC_BUILDINGS, bbox4326=bb)
    g = g[g.to_crs(C.CRS).intersects(regions()["aoi"].union_all().buffer(C.BUFFER_M))]
    p = C.RAW / "nc_buildings.parquet"
    g.to_parquet(p)
    _record(m, "buildings", p, url=C.NC_BUILDINGS, n=len(g), bbox4326=bb,
            licence="not stated; local analysis only until resolved")


def harvest_mrms(m):
    for f in C.MRMS_FILES:
        gz = C.RAW / f
        gz.write_bytes(_get(C.MRMS + f))
        out = C.RAW / f.removesuffix(".gz")
        with gzip.open(gz) as src, open(out, "wb") as dst:
            shutil.copyfileobj(src, dst)
        _record(m, "mrms_" + re.search(r"_(\d{8}-\d{6})\.", f).group(1), gz, url=C.MRMS + f)


def harvest_mrlc(m):
    """NLCD 2021 land cover and tree canopy 2021 over each buffered region, native EPSG:5070 30 m."""
    for r, b in region_bounds().items():
        x0, y0, x1, y1 = gpd.GeoSeries([box(*b)], crs=C.CRS).to_crs(5070).total_bounds
        # snap outward to the NLCD 30 m grid (cell edges at -2493045 + 30 k, 3310005 - 30 k)
        sx = lambda v, f: -2493045 + f((v + 2493045) / 30) * 30  # noqa: E731
        sy = lambda v, f: 3310005 - f((3310005 - v) / 30) * 30  # noqa: E731
        X0, X1, Y0, Y1 = sx(x0, np.floor), sx(x1, np.ceil), sy(y0, np.ceil), sy(y1, np.floor)
        for key, cov in C.MRLC_COVERAGES.items():
            params = {"service": "WCS", "version": "2.0.1", "request": "GetCoverage", "coverageId": cov,
                      "subset": None, "format": "image/geotiff"}
            q = urllib.parse.urlencode({k: v for k, v in params.items() if v}) + \
                f"&subset=X({X0:.0f},{X1:.0f})&subset=Y({Y0:.0f},{Y1:.0f})"
            data = _get(f"{C.MRLC_WCS}?{q}")
            p = C.RAW / f"{key}_{r}.tif"
            p.write_bytes(data)
            with rasterio.open(p) as s:
                assert s.crs.to_epsg() == 5070 and s.res == (30.0, 30.0), (s.crs, s.res)
            _record(m, f"{key}_{r}", p, url=f"{C.MRLC_WCS}?{q}", coverage=cov)


def _sda(sql: str) -> list[list]:
    js = _json(C.SDA, {"query": sql, "format": "JSON"})
    return js.get("Table", [])


def harvest_ssurgo(m):
    """Map-unit polygons + map-unit aggregate attributes per soil survey area (one per county)."""
    for region, names in C.REGIONS.items():
        for name, fips in names.items():
            area = f"NC{fips}"
            rows = _sda(f"SELECT mupolygonkey, mukey, mupolygongeo.STAsText() FROM mupolygon "
                        f"WHERE areasymbol = '{area}'")
            g = gpd.GeoDataFrame({"mupolygonkey": [r[0] for r in rows], "mukey": [r[1] for r in rows]},
                                 geometry=[wkt.loads(r[2]) for r in rows], crs=4326)
            att = _sda(
                "SELECT mu.mukey, mu.muname, ma.brockdepmin, ma.hydgrpdcd, ma.aws0100wta, ma.wtdepannmin "
                "FROM mapunit mu JOIN legend l ON l.lkey = mu.lkey "
                f"JOIN muaggatt ma ON ma.mukey = mu.mukey WHERE l.areasymbol = '{area}'")
            a = pd.DataFrame(att, columns=["mukey", "muname", "brockdepmin", "hydgrpdcd", "aws0100wta",
                                           "wtdepannmin"])
            ver = _sda(f"SELECT saversion, saverest FROM sacatalog WHERE areasymbol = '{area}'")
            p = C.RAW / f"ssurgo_{area}.parquet"
            g.merge(a, on="mukey", how="left").to_parquet(p)
            _record(m, f"ssurgo_{area}", p, url=C.SDA, n=len(g), survey_version=ver[0] if ver else None)


def harvest_roads(m):
    for names in C.REGIONS.values():
        for name, fips in names.items():
            url = C.TIGER_ROADS.format(state=C.STATE_FIPS, county=fips)
            zf = C.RAW / url.rsplit("/", 1)[1]
            zf.write_bytes(_get(url))
            _record(m, f"roads_{fips}", zf, url=url)


def harvest_osm_roads(m):
    """All OSM `highway` lines in the buffered AOI (incl. service roads, driveways, tracks); pbf deleted after."""
    import pyogrio

    pbf = C.RAW / "osm_nc.osm.pbf"
    sha = _download(C.OSM_PBF, pbf)
    bb = tuple(gpd.GeoSeries([box(*region_bounds()["aoi"])], crs=C.CRS).to_crs(4326).total_bounds)
    g = pyogrio.read_dataframe(pbf, layer="lines", bbox=bb, where="highway IS NOT NULL",
                               columns=["osm_id", "name", "highway", "other_tags"])
    p = C.RAW / "osm_roads.parquet"
    g.to_parquet(p)
    nbytes = pbf.stat().st_size
    pbf.unlink()
    _record(m, "osm_roads", p, url=C.OSM_PBF, pbf_sha256=sha, pbf_bytes=nbytes, n=len(g),
            licence="ODbL; local audit only, never published")


SMALL_STEPS = ("counties", "wbd", "inventory", "mrms", "geology", "mrlc", "ssurgo", "roads", "buildings",
               "osm_roads")


def small(only: list[str] | None = None):
    """Run all small steps, or only the named ones (e.g. to resume after a failure)."""
    C.RAW.mkdir(parents=True, exist_ok=True)
    m = _manifest()
    for name in only or SMALL_STEPS:
        step = globals()[f"harvest_{name}"]
        t = time.time()
        step(m)
        _save_manifest(m)
        print(f"{step.__name__}: {time.time() - t:.0f} s", flush=True)


# --- DEM ------------------------------------------------------------------------------------
def dem_tiles(region: str) -> pd.DataFrame:
    """3DEP 1 m tiles whose footprint intersects the buffered region (from the TNM API)."""
    g = regions()[region].union_all().buffer(C.BUFFER_M)
    g4326 = gpd.GeoSeries([g], crs=C.CRS).to_crs(4326).iloc[0]
    bb = ",".join(f"{v:.5f}" for v in g4326.bounds)
    js = _json(f"{C.TNM_API}?" + urllib.parse.urlencode({"datasets": C.DEM_DATASET, "bbox": bb,
                                                           "max": 1000, "outputFormat": "JSON"}))
    rows = []
    for it in js["items"]:
        b = it["boundingBox"]
        if box(b["minX"], b["minY"], b["maxX"], b["maxY"]).intersects(g4326):
            url = it["downloadURL"]
            rows.append({"name": url.rsplit("/", 1)[1].removesuffix(".tif"), "url": url,
                         "project": url.split("/Projects/")[1].split("/")[0],
                         "published": it.get("publicationDate"), "size": it.get("sizeInBytes")})
    df = pd.DataFrame(rows).drop_duplicates("name")
    # mosaic priority (config.DEM_PROJECT_PRIORITY); unknown projects last
    order = {p: i for i, p in enumerate(C.DEM_PROJECT_PRIORITY)}
    df["prio"] = df["project"].map(order).fillna(len(order)).astype(int)
    return df.sort_values(["prio", "name"]).reset_index(drop=True)


def _download(url: str, path, retries: int = 5) -> str:
    for attempt in range(retries):
        try:
            h = hashlib.sha256()
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=600) as r, open(path, "wb") as f:
                for chunk in iter(lambda: r.read(1 << 22), b""):
                    f.write(chunk)
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("unreachable")


def _tile_dates(xml: bytes) -> tuple[str | None, str | None]:
    t = xml.decode("utf-8", "replace")
    b, e = re.search(r"<begdate>(\d+)</begdate>", t), re.search(r"<enddate>(\d+)</enddate>", t)
    return (b.group(1) if b else None, e.group(1) if e else None)


def tile_metadata(url: str, name: str) -> tuple[str | None, str | None]:
    """Fetch the tile's FGDC XML (projects name it `<tile>.xml` or `<tile>_meta.xml`); return lidar dates."""
    base = url.replace("/TIFF/", "/metadata/").removesuffix(".tif")
    for xml_url in (base + ".xml", base + "_meta.xml"):
        try:
            xml = _get(xml_url, retries=2)
        except Exception:
            continue
        (C.RAW / "dem_meta" / f"{name}.xml").write_bytes(xml)
        return _tile_dates(xml)
    return None, None


def backfill_dates():
    """Fill missing lidar dates in the manifest from tile metadata (no re-download)."""
    m = _manifest()
    for r in C.REGIONS:
        key = f"dem_tiles_{r}"
        if key not in m["sources"]:
            continue
        _TOUCHED.add(key)
        for name, rec in m["sources"][key]["tiles"].items():
            if not rec.get("lidar_enddate"):
                rec["lidar_begdate"], rec["lidar_enddate"] = tile_metadata(rec["url"], name)
                print(name, rec["lidar_begdate"], rec["lidar_enddate"], flush=True)
    _save_manifest(m)


def aggregate_tile(src_path, dst_path) -> dict:
    with rasterio.open(src_path) as s:
        if s.crs.to_epsg() != 26917:
            raise ValueError(f"{src_path.name}: CRS {s.crs} (expected EPSG:26917)")
        assert abs(s.res[0] - 1) < 1e-6 and abs(s.res[1] - 1) < 1e-6, s.res
        col0, row0, nx, ny, x0, y0 = lattice_window(s.bounds.left, s.bounds.top, s.width, s.height, C.CELL_M)
        a = s.read(1, window=((row0, row0 + ny * C.CELL_M), (col0, col0 + nx * C.CELL_M)))
        nod = s.nodata if s.nodata is not None else C.DEM_NODATA
        units = s.crs.linear_units
    out = block_mean(a, nod, C.CELL_M, C.OUT_NODATA)
    prof = {"driver": "GTiff", "width": nx, "height": ny, "count": 1, "dtype": "float32", "crs": C.CRS,
            "transform": rasterio.transform.from_origin(x0, y0, C.CELL_M, C.CELL_M), "nodata": C.OUT_NODATA,
            "compress": "deflate", "predictor": 3, "tiled": True}
    with rasterio.open(dst_path, "w", **prof) as d:
        d.write(out, 1)
    return {"nodata_share_5m": float((out == C.OUT_NODATA).mean()), "zmin": float(out[out != C.OUT_NODATA].min())
            if (out != C.OUT_NODATA).any() else None, "zmax": float(out.max()), "units": units}


def dem(region: str | None = None):
    m = _manifest()
    tmp = C.RAW / "dem_tmp"
    tiles5 = C.INTERIM / "dem5_tiles"
    meta_dir = C.RAW / "dem_meta"
    for d in (tmp, tiles5, meta_dir):
        d.mkdir(parents=True, exist_ok=True)
    for r in [region] if region else C.REGIONS:
        df = dem_tiles(r)
        print(f"{r}: {len(df)} tiles, {df['size'].sum() / 1e9:.1f} GB to transfer", flush=True)
        rec = m["sources"].setdefault(f"dem_tiles_{r}", {"tiles": {}})
        _TOUCHED.add(f"dem_tiles_{r}")
        for i, t in df.iterrows():
            out5 = tiles5 / f"{t['name']}_5m.tif"
            if out5.exists() and t["name"] in rec["tiles"]:
                continue
            t0 = time.time()
            raw = tmp / f"{t['name']}.tif"
            sha = _download(t["url"], raw)
            beg, end = tile_metadata(t["url"], t["name"])
            info = aggregate_tile(raw, out5)
            nbytes = raw.stat().st_size
            raw.unlink()
            rec["tiles"][t["name"]] = {"url": t["url"], "project": t["project"], "published": t["published"],
                                       "sha256_1m": sha, "bytes_1m": nbytes, "lidar_begdate": beg,
                                       "lidar_enddate": end, "sha256_5m": _sha256(out5), **info}
            _save_manifest(m)
            free = shutil.disk_usage(C.ROOT).free / 1e9
            print(f"  [{i + 1}/{len(df)}] {t['name']} {nbytes / 1e6:.0f} MB {time.time() - t0:.0f} s "
                  f"(lidar {beg}-{end}; free {free:.1f} GB)", flush=True)
            if free < 20:
                raise SystemExit("stopping: less than 20 GB free disk")
        mosaic(r, df, rec)
        _save_manifest(m)


def mosaic(region: str, df: pd.DataFrame, rec: dict):
    x0, y0, x1, y1 = region_bounds()[region]
    w, h = int((x1 - x0) / C.CELL_M), int((y1 - y0) / C.CELL_M)
    target = np.full((h, w), C.OUT_NODATA, dtype=np.float32)
    seams = []
    for name in df["name"]:  # priority order
        with rasterio.open(C.INTERIM / "dem5_tiles" / f"{name}_5m.tif") as s:
            row = int(round((y1 - s.bounds.top) / C.CELL_M))
            col = int(round((s.bounds.left - x0) / C.CELL_M))
            a = s.read(1)
            seams.append({"tile": name, **seam_stats(target, a, row, col, C.OUT_NODATA)})
            paste_first_valid(target, a, row, col, C.OUT_NODATA)
    prof = {"driver": "GTiff", "width": w, "height": h, "count": 1, "dtype": "float32", "crs": C.CRS,
            "transform": rasterio.transform.from_origin(x0, y1, C.CELL_M, C.CELL_M), "nodata": C.OUT_NODATA,
            "compress": "deflate", "predictor": 3, "tiled": True, "BIGTIFF": "IF_SAFER"}
    p = C.INTERIM / f"dem_5m_{region}.tif"
    with rasterio.open(p, "w", **prof) as d:
        d.write(target, 1)
    rec["mosaic"] = {"path": str(p.relative_to(C.ROOT)), "sha256": _sha256(p), "shape": [h, w],
                     "bounds": [x0, y0, x1, y1], "seams": seams}
    worst = max((s for s in seams if s["overlap_cells"]), key=lambda s: s["p99_abs_m"])
    print(f"{region}: mosaic {w} x {h}; worst seam p99 |diff| {worst['p99_abs_m']:.3f} m ({worst['tile']})", flush=True)


def rebuild_mosaics():
    """Rebuild region mosaics from the 5 m tiles already on disk (no download)."""
    m = _manifest()
    for r in C.REGIONS:
        key = f"dem_tiles_{r}"
        _TOUCHED.add(key)
        mosaic(r, dem_tiles(r), m["sources"][key])
    _save_manifest(m)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "small"
    if what == "small":
        small(sys.argv[2:] or None)
    elif what == "dem-dates":
        backfill_dates()
    elif what == "mosaic":
        rebuild_mosaics()
    elif what == "dem":
        dem(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        raise SystemExit("usage: python -m landslide.harvest small|dem [region]")
