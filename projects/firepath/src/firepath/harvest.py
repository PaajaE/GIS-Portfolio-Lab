"""M1b acquisition: raw inputs for one fire, with a provenance manifest (PLAN §3–5, DATA_SOURCES.md).

  uv run python -m firepath.harvest <fire> [step ...]      steps: perimeters aoi landfire dem hrrr gridmet

Every file written under data/raw/<fire>/ (perimeters: data/raw/perimeters/) is recorded in
provenance/harvest_<fire>.json with its URL, byte count, sha256 and retrieval time. Nothing here
warps to the analysis grid; that is the prepare stage. No credentials are used: LANDFIRE comes from
the public LANDFIRE GeoServer WCS (the LFPS API requires an e-mail address).
"""

from __future__ import annotations

import hashlib
import io
import json
import struct
import sys
import tempfile
import time
import urllib.request
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
RAW = PROJECT / "data" / "raw"
INTERIM = PROJECT / "data" / "interim"
UA = "FirePath/0.1 (portfolio research; reproducible harvest)"

MENDELEY_ZIP = ("https://data.mendeley.com/public-files/datasets/95rj5d379g/files/"
                "e9caf5e3-dcd1-4633-98a9-7f857d110b29/file_downloaded")
MENDELEY_MEMBER = "NIROPS_2020_2024_R1_R6/NIROPS_2020_2024_R1_R6"
WCS = "https://edcintl.cr.usgs.gov/geoserver/landfire/{ws}/ows"
DEM_TILE = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/{t}/USGS_13_{t}.tif"
HRRR = "https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.{d:%Y%m%d}/conus/hrrr.t{d:%H}z.wrfsfcf00.grib2"
GRIDMET = ("https://thredds.northwestknowledge.net/thredds/ncss/agg_met_{v}_1979_CurrentYear_CONUS.nc"
           "?var={var}&north={n}&west={w}&east={e}&south={s}&disableProjSubset=on&horizStride=1"
           "&time_start={t0}&time_end={t1}&timeStride=1&accept=netcdf")

# Pool fires: Mendeley incident ids (Mangum is spelled "Magnum" there), CRS, LANDFIRE rule version (PLAN §3).
FIRES = {
    "mangum": {"incident": "AZ-KNF-000359_Magnum", "epsg": 26912, "landfire": ("conus_2016", "LF2016")},
    "bush": {"incident": "AZ-TNF-001581_Bush", "epsg": 26912, "landfire": ("conus_2016", "LF2016")},
    "telegraph": {"incident": "AZ-TNF-001255_Telegraph", "epsg": 26912, "landfire": None},     # LF 2020: ScienceBase
    "pipeline": {"incident": "AZ-COF-000523_Pipeline", "epsg": 26912, "landfire": None},
    "cerro_pelado": {"incident": "NM-SNF-000049_CerroPelado", "epsg": 26913, "landfire": None},
}
POOL_INCIDENTS = [f["incident"] for f in FIRES.values()] + ["AZ-COF-000536_Haywire", "AZ-COF-000159_Tunnel"]
LANDFIRE_LAYERS = ("FBFM40", "CC", "CH")
WCS_ALL = "https://edcintl.cr.usgs.gov/geoserver/landfire/ows"
# annual disturbance layers after each fuel version (stale years) and the fire years 2020-2022
DIST_LAYERS = {"LF2016": ("LF2020_Dist17", "LF2020_Dist18", "LF2020_Dist19", "LF2020_Dist20"),
               "LF2020": ("LF2022_Dist21", "LF2022_Dist22")}
BUFFER_M = 5000.0
CELL = 30.0


# ----------------------------------------------------------------------------- provenance

class Manifest:
    def __init__(self, fire: str):
        self.path = PROJECT / "provenance" / f"harvest_{fire}.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"fire": fire, "files": {}}

    def add(self, path: Path, url: str, **extra):
        b = path.read_bytes()
        self.data["files"][str(path.relative_to(PROJECT))] = {
            "url": url, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(),
            "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **extra}

    def note(self, key: str, value):
        self.data.setdefault("notes", {})[key] = value

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=1, sort_keys=True))


def _get(url: str, headers: dict | None = None, attempts: int = 4, timeout: int = 120) -> bytes:
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(2 ** (i + 1))
    raise RuntimeError("unreachable")


def _resolve(url: str) -> str:
    """Mendeley answers with a redirect to S3; urllib's default user agent is refused there, so resolve once."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.geturl()


# ----------------------------------------------------------------------------- perimeters (Mendeley NIROPS)

class _RangeFile(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos = url, 0
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            self.size = int(r.headers["Content-Range"].split("/")[1])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(b), self.size) - 1
        d = _get(self.url, {"Range": f"bytes={self.pos}-{end}"})
        b[:len(d)] = d
        self.pos += len(d)
        return len(d)


def read_dbf(b: bytes) -> list[dict]:
    n, hl, rl = struct.unpack("<IHH", b[4:12])
    fields = [(b[i:i + 11].split(b"\0")[0].decode(), b[i + 16]) for i in range(32, hl - 1, 32)]
    out = []
    for k in range(n):
        r, o, d = b[hl + k * rl + 1:hl + (k + 1) * rl], 0, {}
        for name, ln in fields:
            d[name] = r[o:o + ln].decode("latin1").strip()
            o += ln
        out.append(d)
    return out


def shx_offsets(b: bytes) -> list[tuple[int, int]]:
    """(byte offset, content length) of every record in the .shp, from the .shx index."""
    return [(2 * o, 2 * ln) for o, ln in struct.iter_unpack(">ii", b[100:])]


def parse_polygon(rec: bytes):
    """Shapefile polygon record content (type 5/15/25) -> shapely (Multi)Polygon with rings by orientation."""
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.geometry.polygon import orient

    stype = struct.unpack("<i", rec[:4])[0]
    if stype == 0:
        return None
    nparts, npts = struct.unpack("<ii", rec[36:44])
    parts = list(struct.unpack(f"<{nparts}i", rec[44:44 + 4 * nparts])) + [npts]
    p0 = 44 + 4 * nparts
    xy = np.frombuffer(rec[p0:p0 + 16 * npts], "<f8").reshape(npts, 2)
    shells, holes = [], []
    for a, b in zip(parts, parts[1:]):
        ring = xy[a:b]
        if len(ring) < 4:
            continue
        x, y = ring[:, 0], ring[:, 1]
        area2 = float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]))     # shapefile: shells clockwise (area < 0)
        (shells if area2 < 0 else holes).append(Polygon(ring))
    polys = []
    for s in shells:
        inner = [h.exterior.coords for h in holes if s.contains(h.representative_point())]
        polys.append(orient(Polygon(s.exterior.coords, inner)))
    return polys[0] if len(polys) == 1 else MultiPolygon(polys)


def perimeters(manifest: Manifest, incidents=POOL_INCIDENTS) -> Path:
    """Stream the Mendeley shapefile once and keep only the pool incidents' records (no 2 GB file on disk)."""
    from shapely.geometry import mapping
    from shapely.validation import make_valid

    url = _resolve(MENDELEY_ZIP)
    z = zipfile.ZipFile(io.BufferedReader(_RangeFile(url), buffer_size=1 << 20))
    dbf_b = z.read(MENDELEY_MEMBER + ".dbf")
    shx_b = z.read(MENDELEY_MEMBER + ".shx")
    rows = read_dbf(dbf_b)
    offs = shx_offsets(shx_b)
    want = sorted(i for i, r in enumerate(rows) if r["Incident_C"] in set(incidents))
    info = z.getinfo(MENDELEY_MEMBER + ".shp")
    hdr = _get(url, {"Range": f"bytes={info.header_offset}-{info.header_offset + 29}"})
    nlen, xlen = struct.unpack("<HH", hdr[26:30])
    start = info.header_offset + 30 + nlen + xlen
    need = {offs[i][0]: (i, offs[i][1]) for i in want}
    last = max(o + 8 + ln for o, ln in (offs[i] for i in want))
    dec, buf, pos, got = zlib.decompressobj(-15), bytearray(), 0, {}
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Range": f"bytes={start}-{start + info.compress_size - 1}"})
    with urllib.request.urlopen(req, timeout=600) as r:
        while pos + len(buf) < last:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            buf += dec.decompress(chunk)
            for o in [o for o in need if o not in got and o + 8 + need[o][1] <= pos + len(buf)]:
                i, ln = need[o]
                got[o] = (i, bytes(buf[o - pos + 8:o - pos + 8 + ln]))
            keep_from = min(min([o for o in need if o not in got], default=pos + len(buf)) - pos, len(buf))
            if keep_from > 0:
                del buf[:keep_from]
                pos += keep_from
    feats = []
    for o, (i, rec) in sorted(got.items()):
        g = parse_polygon(rec)
        if g is None:
            continue
        g = make_valid(g) if not g.is_valid else g
        feats.append({"type": "Feature", "properties": rows[i] | {"record": i}, "geometry": mapping(g)})
    out = RAW / "perimeters" / "nirops_mendeley_pool.geojson"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"type": "FeatureCollection", "crs_note": "EPSG:4326 (dataset .prj: GCS_WGS_1984)",
                               "features": feats}))
    manifest.add(out, MENDELEY_ZIP, note="subset of NIROPS_2020_2024_R1_R6.shp by Incident_C; CC BY 4.0",
                 records=len(feats), source_dbf_sha256=hashlib.sha256(dbf_b).hexdigest(),
                 source_shx_sha256=hashlib.sha256(shx_b).hexdigest())
    return out


# ----------------------------------------------------------------------------- analysis domain

def fire_perimeters(fire: str) -> list[dict]:
    fc = json.loads((RAW / "perimeters" / "nirops_mendeley_pool.geojson").read_text())
    inc = FIRES[fire]["incident"]
    return sorted((f for f in fc["features"] if f["properties"]["Incident_C"] == inc),
                  key=lambda f: f["properties"]["UTC"])


def aoi(fire: str, manifest: Manifest) -> dict:
    """Grid = union of the fire's IR perimeters + 5 km, in UTM, origin snapped to 30 m (PLAN §5)."""
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform, unary_union

    epsg = FIRES[fire]["epsg"]
    to_utm = Transformer.from_crs(4326, epsg, always_xy=True).transform
    union = unary_union([transform(to_utm, shape(f["geometry"])) for f in fire_perimeters(fire)])
    x0, y0, x1, y1 = union.buffer(BUFFER_M).bounds
    x0, y0 = np.floor(x0 / CELL) * CELL, np.floor(y0 / CELL) * CELL
    x1, y1 = np.ceil(x1 / CELL) * CELL, np.ceil(y1 / CELL) * CELL
    grid = {"epsg": epsg, "cell": CELL, "x0": x0, "y1": y1, "width": int((x1 - x0) / CELL),
            "height": int((y1 - y0) / CELL), "bounds_utm": [x0, y0, x1, y1], "buffer_m": BUFFER_M}
    to_ll = Transformer.from_crs(epsg, 4326, always_xy=True)
    xs = np.linspace(x0, x1, 21)
    ys = np.linspace(y0, y1, 21)
    edge = [(x, y0) for x in xs] + [(x, y1) for x in xs] + [(x0, y) for y in ys] + [(x1, y) for y in ys]
    lon, lat = to_ll.transform(*zip(*edge))
    grid["bounds_lonlat"] = [min(lon), min(lat), max(lon), max(lat)]
    out = INTERIM / fire / "grid.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(grid, indent=1))
    manifest.note("grid", grid)
    return grid


def _grid(fire):
    return json.loads((INTERIM / fire / "grid.json").read_text())


def _lonlat_bbox(fire, margin_deg=0.02):
    w, s, e, n = _grid(fire)["bounds_lonlat"]
    return w - margin_deg, s - margin_deg, e + margin_deg, n + margin_deg


# ----------------------------------------------------------------------------- LANDFIRE (WCS)

def landfire(fire: str, manifest: Manifest):
    """LANDFIRE rule version for the fire from the public GeoServer WCS. The coverages are served in
    EPSG:3857 at 30 m (≈ 24 m on the ground at 36° N), already resampled by the server from the native
    EPSG:5070; prepare() warps them with nearest and reports class-proportion changes."""
    from pyproj import Transformer

    if FIRES[fire]["landfire"] is None:
        raise SystemExit(f"{fire}: LANDFIRE 2020 comes from the ScienceBase archive (not automated yet)")
    ws, ver = FIRES[fire]["landfire"]
    w, s, e, n = _lonlat_bbox(fire)
    t = Transformer.from_crs(4326, 3857, always_xy=True)
    (x0, x1), (y0, y1) = zip(*[t.transform(w, s), t.transform(e, n)])
    x0, y0, x1, y1 = (np.floor(x0 / 30) * 30, np.floor(y0 / 30) * 30, np.ceil(x1 / 30) * 30, np.ceil(y1 / 30) * 30)
    for layer in LANDFIRE_LAYERS:
        cov = f"landfire__{ver}_{layer}_CONUS"
        url = (WCS.format(ws=ws) + f"?service=WCS&version=2.0.1&request=GetCoverage&coverageId={cov}"
               f"&format=image/geotiff&subset=X({x0:.0f},{x1:.0f})&subset=Y({y0:.0f},{y1:.0f})")
        b = _get(url, timeout=600)
        if not b.startswith((b"II*\x00", b"MM\x00*")):
            raise RuntimeError(f"WCS did not return a GeoTIFF for {cov}: {b[:200]!r}")
        out = RAW / fire / "landfire" / f"{ver}_{layer}.tif"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b)
        manifest.add(out, url, version=ver, crs="EPSG:3857")


def disturbance(fire: str, manifest: Manifest):
    """Annual LANDFIRE disturbance layers between the fuel version's last disturbance year and the fire
    year (stale fuels, PLAN §3), plus the fire year itself (shows what a later version would leak). Same
    WCS and box as landfire(); prepare.stale_fuels() summarises them."""
    from pyproj import Transformer

    ver = FIRES[fire]["landfire"][1] if FIRES[fire]["landfire"] else "LF2020"
    w, s, e, n = _lonlat_bbox(fire)
    t = Transformer.from_crs(4326, 3857, always_xy=True)
    (x0, x1), (y0, y1) = zip(*[t.transform(w, s), t.transform(e, n)])
    x0, y0, x1, y1 = (np.floor(x0 / 30) * 30, np.floor(y0 / 30) * 30, np.ceil(x1 / 30) * 30, np.ceil(y1 / 30) * 30)
    for cov in DIST_LAYERS[ver]:
        url = (WCS_ALL + f"?service=WCS&version=2.0.1&request=GetCoverage&coverageId=landfire__{cov}_CONUS"
               f"&format=image/geotiff&subset=X({x0:.0f},{x1:.0f})&subset=Y({y0:.0f},{y1:.0f})")
        b = _get(url, timeout=600)
        if not b.startswith((b"II*\x00", b"MM\x00*")):
            raise RuntimeError(f"WCS did not return a GeoTIFF for {cov}: {b[:200]!r}")
        out = RAW / fire / "landfire" / f"{cov}.tif"
        out.write_bytes(b)
        manifest.add(out, url, crs="EPSG:3857")


# ----------------------------------------------------------------------------- 3DEP DEM

def dem(fire: str, manifest: Manifest):
    """1/3 arc-second 3DEP tiles (COG on the TNM S3 bucket), windowed reads, merged in native EPSG:4269."""
    import rasterio
    from rasterio.merge import merge
    from rasterio.windows import from_bounds

    w, s, e, n = _lonlat_bbox(fire)
    tiles = [f"n{lat:02d}w{-lon:03d}" for lat in range(int(np.floor(s)) + 1, int(np.floor(n)) + 2)
             for lon in range(int(np.floor(w)), int(np.floor(e)) + 1)]
    srcs, urls = [], []
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
        mem = []
        for t in tiles:
            url = DEM_TILE.format(t=t)
            with rasterio.open("/vsicurl/" + url) as src:
                win = from_bounds(max(w, src.bounds.left), max(s, src.bounds.bottom),
                                  min(e, src.bounds.right), min(n, src.bounds.top), src.transform).round_offsets().round_lengths()
                if win.width <= 0 or win.height <= 0:
                    continue
                a = src.read(1, window=win)
                prof = src.profile | {"driver": "GTiff", "width": a.shape[1], "height": a.shape[0],
                                      "transform": src.window_transform(win), "tiled": False, "compress": "deflate"}
                prof.pop("blockxsize", None), prof.pop("blockysize", None)
                f = rasterio.MemoryFile()
                with f.open(**prof) as dst:
                    dst.write(a, 1)
                mem.append(f)
                urls.append(url)
        srcs = [m.open() for m in mem]
        arr, tr = merge(srcs)
        prof = srcs[0].profile | {"width": arr.shape[2], "height": arr.shape[1], "transform": tr}
    out = RAW / fire / "dem" / "usgs_13_merged.tif"
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", **prof) as dst:
        dst.write(arr)
    manifest.add(out, " ; ".join(urls), tiles=tiles, crs="EPSG:4269", resolution="1/3 arc-second")


# ----------------------------------------------------------------------------- HRRR analyses

HRRR_FIELDS = ("UGRD:10 m above ground", "VGRD:10 m above ground")


def _hrrr_ranges(idx: str, fields=HRRR_FIELDS):
    lines = [ln.split(":") for ln in idx.strip().splitlines()]
    out = {}
    for k, ln in enumerate(lines):
        key = f"{ln[3]}:{ln[4]}"
        if key in fields and ln[5] == "anl":
            end = int(lines[k + 1][1]) - 1 if k + 1 < len(lines) else ""
            out[key] = (int(ln[1]), end)
    return out


def hrrr(fire: str, manifest: Manifest, hours_before: int = 24, hours_after: int = 0, workers: int = 8):
    """Hourly f00 10 m U/V (grid-relative; rotation happens in prepare) cropped to the fire box + margin.
    Window: first IR perimeter − 24 h to last IR perimeter. Whole messages are fetched by byte range and
    discarded after cropping; each message's sha256 is kept."""
    import rasterio
    from pyproj import Transformer
    from rasterio.windows import from_bounds

    p = fire_perimeters(fire)
    t0 = datetime.fromisoformat(p[0]["properties"]["UTC"]).replace(tzinfo=timezone.utc, minute=0, second=0)
    t1 = datetime.fromisoformat(p[-1]["properties"]["UTC"]).replace(tzinfo=timezone.utc, minute=0, second=0)
    times = [t0 - timedelta(hours=hours_before) + timedelta(hours=h)
             for h in range(int((t1 - t0).total_seconds() // 3600) + hours_before + hours_after + 2)]
    w, s, e, n = _lonlat_bbox(fire, margin_deg=0.1)

    def one(t):
        url = HRRR.format(d=t)
        idx = _get(url + ".idx").decode()
        res = {}
        for key, (a, b) in _hrrr_ranges(idx).items():
            msg = _get(url, {"Range": f"bytes={a}-{b}"})
            with tempfile.NamedTemporaryFile(suffix=".grib2") as tmp:
                tmp.write(msg)
                tmp.flush()
                with rasterio.open(tmp.name) as src:
                    tr = Transformer.from_crs(4326, src.crs, always_xy=True)
                    xs, ys = tr.transform([w, e, w, e], [s, s, n, n])
                    win = from_bounds(min(xs), min(ys), max(xs), max(ys), src.transform).round_offsets().round_lengths()
                    res[key] = (src.read(1, window=win).astype("f4"), src.window_transform(win), src.crs.to_wkt(),
                                hashlib.sha256(msg).hexdigest(), src.tags(1).get("GRIB_VALID_TIME"))
        return t, url, res

    with ThreadPoolExecutor(workers) as ex:
        results = list(ex.map(one, times))
    missing = [t.isoformat() for t, _, r in results if len(r) != len(HRRR_FIELDS)]
    ok = [(t, url, r) for t, url, r in results if len(r) == len(HRRR_FIELDS)]
    u = np.stack([r["UGRD:10 m above ground"][0] for _, _, r in ok])
    v = np.stack([r["VGRD:10 m above ground"][0] for _, _, r in ok])
    tr, wkt = ok[0][2]["UGRD:10 m above ground"][1], ok[0][2]["UGRD:10 m above ground"][2]
    for _, _, r in ok:
        assert r["UGRD:10 m above ground"][1] == tr and r["VGRD:10 m above ground"][1] == tr, "HRRR window moved"
    valid = [int(r["UGRD:10 m above ground"][4]) for _, _, r in ok]
    assert valid == [int(t.timestamp()) for t, _, _ in ok], "GRIB valid time differs from the requested hour"
    out = RAW / fire / "hrrr" / "hrrr_f00_uv10_crop.npz"
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, u=u, v=v, valid_unix=np.array(valid, "i8"), transform=np.array(tr)[:6], crs_wkt=wkt)
    manifest.add(out, HRRR.replace("{d:%Y%m%d}", "<date>").replace("{d:%H}", "<hh>"),
                 hours=len(ok), first=ok[0][0].isoformat(), last=ok[-1][0].isoformat(), missing_hours=missing,
                 note="grid-relative U/V (Lambert conformal); rotate in prepare",
                 message_sha256={t.isoformat(): {k: r[k][3] for k in r} for t, _, r in ok})


# ----------------------------------------------------------------------------- gridMET

GRIDMET_VARS = {"fm100": "dead_fuel_moisture_100hr", "fm1000": "dead_fuel_moisture_1000hr"}


def gridmet(fire: str, manifest: Manifest):
    p = fire_perimeters(fire)
    t0 = datetime.fromisoformat(p[0]["properties"]["UTC"]) - timedelta(days=2)
    t1 = datetime.fromisoformat(p[-1]["properties"]["UTC"]) + timedelta(days=1)
    w, s, e, n = _lonlat_bbox(fire, margin_deg=0.1)
    for v, var in GRIDMET_VARS.items():
        url = GRIDMET.format(v=v, var=var, n=n, w=w, e=e, s=s, t0=f"{t0:%Y-%m-%d}T00:00:00Z",
                             t1=f"{t1:%Y-%m-%d}T00:00:00Z")
        b = _get(url, timeout=600)
        if not b.startswith((b"CDF", b"\x89HDF")):
            raise RuntimeError(f"gridMET did not return NetCDF for {v}: {b[:200]!r}")
        out = RAW / fire / "gridmet" / f"{v}.nc"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b)
        manifest.add(out, url)


STEPS = {"perimeters": lambda f, m: perimeters(m), "aoi": aoi, "landfire": landfire, "disturbance": disturbance,
         "dem": dem,
         "hrrr": hrrr, "gridmet": gridmet}


def main(argv=None):
    argv = argv or sys.argv[1:]
    fire, steps = argv[0], argv[1:] or list(STEPS)
    if fire not in FIRES:
        raise SystemExit(f"unknown fire {fire!r}; known: {sorted(FIRES)}")
    m = Manifest(fire)
    m.note("run", {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "host": __import__("platform").platform()})
    for step in steps:
        if step == "perimeters" and (RAW / "perimeters" / "nirops_mendeley_pool.geojson").exists():
            print("perimeters: already harvested", flush=True)
            continue
        t = time.perf_counter()
        STEPS[step](fire, m)
        m.save()
        print(f"{step}: {time.perf_counter() - t:.0f}s", flush=True)


if __name__ == "__main__":
    main()
