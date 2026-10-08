"""Download source data for the AOI into data/raw/ and write a provenance manifest.

Vector layers come from MassGIS ArcGIS REST services (queried by object id in
chunks so no record is silently dropped by server transfer limits). The DEM is
read as windows from USGS 3DEP 1 m COG tiles; only the AOI is transferred.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import time
import urllib.parse
import urllib.request
import zipfile

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.windows import from_bounds

from . import config as C

UA = {"User-Agent": "parcel-intel/0.1 (research; local pipeline)"}


def _get(url: str, data: dict | None = None, retries: int = 4) -> bytes:
    body = urllib.parse.urlencode(data).encode() if data else None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=UA)
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def _json(url, data=None):
    out = json.loads(_get(url, data))
    if "error" in out:
        raise RuntimeError(f"{url}: {out['error']}")
    return out


def _mtime(path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.UTC).isoformat(timespec="seconds")


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_layer(url: str, where: str, fields: str, envelope=None, chunk: int = 400) -> dict:
    base = {"where": where, "f": "json"}
    if envelope is not None:
        base.update(
            geometry=",".join(f"{v:.6f}" for v in envelope),
            geometryType="esriGeometryEnvelope",
            inSR="4326",
            spatialRel="esriSpatialRelIntersects",
        )
    ids = _json(f"{url}/query", {**base, "returnIdsOnly": "true"}).get("objectIds") or []
    ids = sorted(ids)
    features = []
    for i in range(0, len(ids), chunk):
        part = ids[i : i + chunk]
        q = {"objectIds": ",".join(map(str, part)), "outFields": fields, "outSR": "4326", "f": "geojson"}
        fc = json.loads(_get(f"{url}/query", q))
        if len(fc.get("features", [])) != len(part):
            raise RuntimeError(f"{url}: asked {len(part)} features, got {len(fc.get('features', []))}")
        features.extend(fc["features"])
    return {"type": "FeatureCollection", "features": features}


def layer_metadata(url: str) -> dict:
    m = _json(url, {"f": "json"})
    svc = _json(url.rsplit("/", 1)[0], {"f": "json"})
    edit = (m.get("editingInfo") or {}).get("lastEditDate") or (m.get("editingInfo") or {}).get("dataLastEditDate")
    return {
        "layer_name": m.get("name"),
        "copyright": m.get("copyrightText") or svc.get("copyrightText"),
        "source_spatial_reference": (m.get("extent") or {}).get("spatialReference"),
        "last_edit_utc": dt.datetime.fromtimestamp(edit / 1000, dt.UTC).isoformat() if edit else None,
        "description_head": (m.get("description") or svc.get("serviceDescription") or "")[:400],
    }


def aoi_envelope(town: gpd.GeoDataFrame) -> tuple[float, float, float, float]:
    buf = town.to_crs(C.CRS).buffer(C.AOI_BUFFER_M).to_crs(4326)
    return tuple(buf.total_bounds)


def harvest_vectors(manifest: dict) -> None:
    for name, (url, where, fields) in C.VECTOR_SOURCES.items():
        path = C.RAW / f"{name}.geojson"
        if not path.exists():
            env = None
            if name not in ("town", "parcels"):
                env = aoi_envelope(gpd.read_file(C.RAW / "town.geojson"))
            fc = fetch_layer(url, where, fields, env)
            path.write_text(json.dumps(fc))
        n = len(json.loads(path.read_text())["features"])
        manifest["sources"][name] = {
            "url": url,
            "where": where,
            "fields": fields,
            "features": n,
            "file": path.name,
            "sha256": _sha256(path),
            "acquired_utc": _mtime(path),
            **layer_metadata(url),
        }
        print(f"{name:12s} {n:7d} features")


def harvest_prihab(manifest: dict) -> None:
    path = C.RAW / "prihab.geojson"
    if not path.exists():
        z = zipfile.ZipFile(io.BytesIO(_get(C.PRIHAB_URL)))
        shp = next(n for n in z.namelist() if n.lower().endswith(".shp"))
        tmp = C.RAW / "prihab_zip"
        z.extractall(tmp)
        gdf = gpd.read_file(tmp / shp)
        town = gpd.read_file(C.RAW / "town.geojson").to_crs(gdf.crs)
        clip = gdf[gdf.intersects(town.buffer(C.AOI_BUFFER_M).union_all())]
        clip.to_crs(4326).to_file(path, driver="GeoJSON")
        meta = {"source_crs": gdf.crs.to_string(), "statewide_features": len(gdf)}
        xml = [n for n in z.namelist() if n.lower().endswith(".xml")]
        meta["metadata_files"] = xml
        for f in tmp.rglob("*"):
            if f.is_file():
                f.unlink()
        for d in sorted(tmp.rglob("*"), reverse=True):
            d.rmdir()
        tmp.rmdir()
        (C.RAW / "prihab_meta.json").write_text(json.dumps(meta))
    meta = json.loads((C.RAW / "prihab_meta.json").read_text())
    n = len(json.loads(path.read_text())["features"])
    manifest["sources"]["prihab"] = {"url": C.PRIHAB_URL, "features": n, "file": path.name, "sha256": _sha256(path), "acquired_utc": _mtime(path), **meta}
    print(f"{'prihab':12s} {n:7d} features")


def harvest_dem(manifest: dict) -> None:
    path = C.RAW / "dem_1m_utm18.tif"
    town = gpd.read_file(C.RAW / "town.geojson")
    env = aoi_envelope(town)
    items = _json(C.DEM_TNM_API + ",".join(f"{v:.5f}" for v in env))["items"]
    tiles = sorted({it["downloadURL"] for it in items if C.DEM_PROJECT in it["downloadURL"]})
    pubs = sorted({it.get("publicationDate") for it in items if C.DEM_PROJECT in it["downloadURL"]})
    if not path.exists():
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="4"):
            srcs = [rasterio.open("/vsicurl/" + u) for u in tiles]
            utm = town.to_crs(srcs[0].crs).buffer(C.AOI_BUFFER_M + 50).total_bounds
            arr, transform = merge(srcs, bounds=tuple(utm), nodata=-999999.0)
            profile = srcs[0].profile | {
                "driver": "GTiff",
                "height": arr.shape[1],
                "width": arr.shape[2],
                "transform": transform,
                "compress": "deflate",
                "predictor": 3,
                "tiled": True,
                "blockxsize": 512,
                "blockysize": 512,
                "BIGTIFF": "IF_SAFER",
            }
            for s in srcs:
                s.close()
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(arr)
    with rasterio.open(path) as d:
        info = {"crs": d.crs.to_string(), "res": d.res, "shape": d.shape, "nodata": d.nodata}
        sample = d.read(1, window=from_bounds(*d.bounds, d.transform), out_shape=(200, 200))
        valid = sample[sample != d.nodata]
        info["elev_range_sample_m"] = [float(np.min(valid)), float(np.max(valid))]
    manifest["sources"]["dem"] = {
        "provider": "USGS 3D Elevation Program",
        "project": C.DEM_PROJECT,
        "tiles": tiles,
        "publication_dates": pubs,
        "file": path.name,
        "sha256": _sha256(path),
        "acquired_utc": _mtime(path),
        **info,
    }
    print(f"{'dem':12s} {len(tiles)} tiles -> {info['shape']}")


def main() -> None:
    C.RAW.mkdir(parents=True, exist_ok=True)
    C.PROVENANCE.mkdir(parents=True, exist_ok=True)
    mpath = C.PROVENANCE / "harvest_manifest.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {}
    manifest.setdefault("sources", {})
    harvest_vectors(manifest)
    harvest_prihab(manifest)
    harvest_dem(manifest)
    manifest["aoi"] = {"town": C.TOWN_NAME, "town_id": C.TOWN_ID, "buffer_m": C.AOI_BUFFER_M}
    mpath.write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
