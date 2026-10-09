"""M0 reachability / authentication / inventory probe (non-destructive, standard library only).

Run on the build Mac:   python3 src/firepath/probe.py --label build-mac
(or `make probe`). Writes provenance/probe_<label>.json and prints a summary table.

Downloads only metadata, directory listings, HEAD responses and byte-range samples (<= max_bytes per
request). Never submits jobs, never sends credentials, never registers. A failure is recorded with the
HTTP status or the exception text; "reachable" means the endpoint answered, not that the dataset is
usable — usability is decided in M1b with real AOI requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = "FirePath-M0-probe/0.1 (portfolio research; non-destructive metadata probe)"
TIMEOUT = 25
PROJECT = Path(__file__).resolve().parents[2]

FIRES = {  # name patterns used to find incidents in listings / services
    "Bush 2020": ["bush"], "Mangum 2020": ["mangum"], "Telegraph 2021": ["telegraph"],
    "Tunnel 2022": ["tunnel"], "Pipeline 2022": ["pipeline", "haywire", "double"],
    "Woodbury 2019": ["woodbury"], "Cerro Pelado 2022": ["cerro", "pelado"],
    "South Fork 2024": ["south_fork", "southfork", "south fork"],
}
FIRE_YEARS = {"Bush 2020": 2020, "Mangum 2020": 2020, "Telegraph 2021": 2021, "Tunnel 2022": 2022,
              "Pipeline 2022": 2022, "Woodbury 2019": 2019, "Cerro Pelado 2022": 2022,
              "South Fork 2024": 2024}

# id, purpose, url, method, max_bytes, extra headers
CHECKS = [
    ("hrrr_idx", "HRRR index (weather)", "https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.20220419/conus/hrrr.t21z.wrfsfcf00.grib2.idx", "GET", 200_000, {}),
    ("hrrr_range", "HRRR byte-range sample", "https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.20220419/conus/hrrr.t21z.wrfsfcf00.grib2", "GET", 4096, {"Range": "bytes=45506335-45510430"}),
    ("landfire_home", "LANDFIRE site", "https://landfire.gov/", "GET", 50_000, {}),
    ("landfire_versions", "LANDFIRE version table", "https://landfire.gov/data/lf_versions", "GET", 200_000, {}),
    ("lfps_root", "LANDFIRE Product Service API", "https://lfps.usgs.gov/api/", "GET", 50_000, {}),
    ("lfps_products", "LFPS product list", "https://lfps.usgs.gov/api/products", "GET", 500_000, {}),
    ("lfps_submit_noargs", "LFPS submit without args (expects a parameter error, no job)", "https://lfps.usgs.gov/api/job/submit", "GET", 20_000, {}),
    ("lf_dl_200_f40", "LANDFIRE LF2016 Remap FBFM40 CONUS zip (HEAD)", "https://landfire.gov/data-downloads/US_200/LF2016_FBFM40_200_CONUS.zip", "HEAD", 0, {}),
    ("lf_dl_220_f40", "LANDFIRE LF2020 FBFM40 CONUS zip (HEAD)", "https://landfire.gov/data-downloads/US_220/LF2022_FBFM40_220_CONUS.zip", "HEAD", 0, {}),
    ("lf_dl_230_f40", "LANDFIRE LF2022 FBFM40 CONUS zip (HEAD)", "https://landfire.gov/data-downloads/US_230/LF2022_FBFM40_230_CONUS.zip", "HEAD", 0, {}),
    ("lf_dl_240_f40", "LANDFIRE LF2023 FBFM40 CONUS zip (HEAD)", "https://landfire.gov/data-downloads/US_240/LF2023_FBFM40_240_CONUS.zip", "HEAD", 0, {}),
    ("mtbs_home", "MTBS site", "https://www.mtbs.gov/direct-download", "GET", 50_000, {}),
    ("mtbs_perims_zip", "MTBS national perimeters zip (HEAD)", "https://edcintl.cr.usgs.gov/downloads/sciweb1/shared/MTBS_Fire/data/composite_data/burned_area_extent_shapefile/mtbs_perimeter_data.zip", "HEAD", 0, {}),
    ("nifc_services", "NIFC ArcGIS Online services list", "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services?f=json", "GET", 2_000_000, {}),
    ("nifc_ftp_root", "NIFC FTP incident data (NIROPS IR)", "https://ftp.wildfire.gov/public/incident_specific_data/", "GET", 500_000, {}),
    ("mendeley_meta", "Mendeley NIROPS progression dataset metadata", "https://data.mendeley.com/public-api/datasets/95rj5d379g", "GET", 500_000, {"Accept": "application/vnd.mendeley-public-dataset.1+json"}),
    ("firms_nokey", "FIRMS API without MAP_KEY (expects key error)", "https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/NO_KEY/all", "GET", 20_000, {}),
    ("feds_collections", "NASA FEDS via VEDA OGC API", "https://openveda.cloud/api/features/collections?f=json", "GET", 500_000, {}),
    ("gridmet_listing", "gridMET file listing", "https://www.northwestknowledge.net/metdata/data/", "GET", 300_000, {}),
    ("gridmet_fm100_2022", "gridMET fm100 2022 (HEAD)", "https://www.northwestknowledge.net/metdata/data/fm100_2022.nc", "HEAD", 0, {}),
    ("gridmet_thredds", "gridMET THREDDS DAS", "http://thredds.northwestknowledge.net:8080/thredds/dodsC/agg_met_fm100_1979_CurrentYear_CONUS.nc.das", "GET", 50_000, {}),
    ("tnm_3dep", "TNM Access API: 3DEP 1/3 arc-second over Flagstaff", "https://tnmaccess.nationalmap.gov/api/v1/products?datasets=National%20Elevation%20Dataset%20(NED)%201/3%20arc-second&bbox=-111.8,35.2,-111.4,35.5&max=5&outputFormat=JSON", "GET", 500_000, {}),
    ("tiger_edges", "TIGER/Line 2022 edges, Coconino County (HEAD)", "https://www2.census.gov/geo/tiger/TIGER2022/EDGES/tl_2022_04005_edges.zip", "HEAD", 0, {}),
    ("tiger_blocks", "TIGER 2020 TABBLOCK20 Arizona (HEAD)", "https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_04_tabblock20.zip", "HEAD", 0, {}),
    ("usa_structures", "USA Structures (FEMA geoplatform)", "https://disasters.geoplatform.gov/USA_Structures/", "GET", 100_000, {}),
    ("agol_search_structures", "ArcGIS Online search: USA Structures", "https://www.arcgis.com/sharing/rest/search?q=title%3A%22USA%20Structures%22&num=5&f=json", "GET", 200_000, {}),
    ("ics209plus", "ICS-209-PLUS (figshare API)", "https://api.figshare.com/v2/articles/19858927", "GET", 500_000, {}),
    ("inciweb_tunnel", "InciWeb Tunnel Fire page", "https://inciweb.wildfire.gov/incident-information/azcof-tunnel-fire", "GET", 100_000, {}),
    ("nfmd", "National Fuel Moisture Database", "https://www.wfas.net/nfmd/public/index.php", "GET", 100_000, {}),
    ("raws_wrcc", "WRCC RAWS archive", "https://raws.dri.edu/", "GET", 50_000, {}),
    ("synoptic_notoken", "Synoptic API without token (expects auth error)", "https://api.synopticdata.com/v2/stations/metadata?stid=KFLG", "GET", 20_000, {}),
    ("pypi_pyretechnics", "pyretechnics package metadata (PyPI)", "https://pypi.org/pypi/pyretechnics/json", "GET", 2_000_000, {}),
]

AUTH_HINTS = re.compile(r"(api[_ ]?key|map_key|token|unauthori[sz]ed|login|credential|register)", re.I)


def _ctx():
    return ssl.create_default_context()


def fetch(url: str, method: str = "GET", max_bytes: int = 100_000, headers: dict | None = None) -> dict:
    h = {"User-Agent": UA, **(headers or {})}
    req = urllib.request.Request(url, method=method, headers=h)
    t0 = time.monotonic()
    rec = {"url": url, "method": method, "utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ctx()) as r:
            body = r.read(max_bytes) if method != "HEAD" and max_bytes else b""
            rec.update(status=r.status, reason=r.reason, final_url=r.geturl())
            hdr = {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        body = e.read(min(max_bytes, 20_000)) if max_bytes else b""
        rec.update(status=e.code, reason=str(e.reason))
        hdr = {k.lower(): v for k, v in (e.headers or {}).items()}
    except Exception as e:  # DNS, TLS, proxy CONNECT refusal, timeout
        rec.update(status=None, error=f"{type(e).__name__}: {e}", elapsed_s=round(time.monotonic() - t0, 2))
        return rec
    rec["elapsed_s"] = round(time.monotonic() - t0, 2)
    rec["headers"] = {k: hdr[k] for k in ("content-type", "content-length", "last-modified", "content-range") if k in hdr}
    rec["bytes_read"] = len(body)
    if body:
        rec["sha256"] = hashlib.sha256(body).hexdigest()
        text = body[:4000].decode("utf-8", "replace")
        rec["auth_hint"] = bool(AUTH_HINTS.search(text)) and (rec["status"] or 0) >= 400
        ctype = rec["headers"].get("content-type", "")
        if any(t in ctype for t in ("text", "json", "xml", "html")) or not ctype:
            snip = re.sub(r"\s+", " ", text[:300])
            rec["snippet"] = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>", snip)  # no third-party addresses
    rec["_body"] = body
    return rec


def fetch_retry(url, method="GET", max_bytes=100_000, headers=None, attempts=3) -> dict:
    """Retry transient failures (timeouts, 5xx, S3 'NoSuchBucket' blips seen in testing). Proxy policy
    refusals ('Tunnel connection failed: 403') are not retried. All attempt outcomes are recorded."""
    history = []
    for i in range(attempts):
        rec = fetch(url, method, max_bytes, headers)
        history.append(rec.get("status") or rec.get("error", "")[:80])
        err = rec.get("error", "")
        transient = (rec.get("status") is None and "Tunnel connection failed" not in err) or \
            (rec.get("status") or 0) >= 500 or "NoSuchBucket" in rec.get("snippet", "")
        if not transient:
            break
        time.sleep(2 * (i + 1))
    rec["attempts"] = history
    return rec


def links(html: bytes) -> list[str]:
    return re.findall(r'href="([^"?#]+)"', html.decode("utf-8", "replace"))


TS = re.compile(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)[-_ T]?([0-2]\d)?([0-5]\d)?")


NIROPS_ROOT = "https://ftp.wildfire.gov/public/incident_specific_data/"


def nirops_inventory(root: str = NIROPS_ROOT, budget: int = 250) -> dict:
    """Crawl the NIFC FTP (HTTPS listing) for candidate incidents and their IR perimeter files."""
    out = {"root": root, "requests": 0, "regions": [], "fires": {}, "notes": []}

    def get(url):
        out["requests"] += 1
        return fetch(url, "GET", 2_000_000)

    r = get(root)
    if r.get("status") != 200:
        out["notes"].append(f"root not listable: {r.get('status')} {r.get('error', '')}")
        return out
    regions = [l for l in links(r["_body"]) if l.endswith("/") and not l.startswith("/") and ".." not in l]
    out["regions"] = regions
    sw = [x for x in regions if "southwest" in x.lower()] or regions
    queue = [(urllib.parse.urljoin(root, x), 0) for x in sw]
    while queue and out["requests"] < budget:
        url, depth = queue.pop(0)
        r = get(url)
        if r.get("status") != 200:
            continue
        for l in links(r["_body"]):
            if l.startswith("/") or l.startswith("http") or ".." in l:
                continue
            full = urllib.parse.urljoin(url, l)
            low = urllib.parse.unquote(full).lower()
            for fire, pats in FIRES.items():
                year = str(FIRE_YEARS[fire])
                if year in low and any(p in low.replace("%20", " ") for p in pats):
                    rec = out["fires"].setdefault(fire, {"dirs": [], "ir_files": []})
                    if l.endswith("/") and full not in rec["dirs"]:
                        rec["dirs"].append(full)
                        queue.append((full, depth + 1))
                    elif not l.endswith("/") and ("/ir/" in low or "ir" in l.lower().split("_")):
                        m = TS.search(l)
                        rec["ir_files"].append({"file": urllib.parse.unquote(full), "timestamp_in_name":
                                                m.group(0) if m else None})
            if l.endswith("/") and depth < 2 and re.search(r"20(19|2[0-4])", l):
                queue.append((full, depth + 1))
    if queue:
        out["notes"].append(f"budget of {budget} requests exhausted; {len(queue)} listings not visited")
    return out


def nifc_perimeter_services(services_body: bytes) -> dict:
    """Find perimeter/archive feature services and count features for Pipeline/Haywire/Double."""
    out = {"services": [], "pipeline_haywire": []}
    try:
        svcs = json.loads(services_body).get("services", [])
    except Exception as e:
        out["error"] = str(e)
        return out
    wanted = [s for s in svcs if re.search(r"(perimeter|archive|nifs|wfigs)", s.get("name", ""), re.I)]
    out["services"] = [s["name"] for s in wanted][:60]
    for s in wanted[:25]:
        base = f"https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/{s['name']}/{s['type']}/0"
        meta = fetch(base + "?f=json", "GET", 500_000)
        if meta.get("status") != 200:
            continue
        try:
            fields = [f["name"] for f in json.loads(meta["_body"]).get("fields", [])]
        except Exception:
            continue
        name_f = next((f for f in fields if re.search(r"incidentname$", f, re.I)), None)
        time_f = [f for f in fields if re.search(r"(datetime|date_current|polygondate|gdb_from|createdate)", f, re.I)]
        if not name_f:
            continue
        where = f"UPPER({name_f}) LIKE '%PIPELINE%' OR UPPER({name_f}) LIKE '%HAYWIRE%' OR UPPER({name_f}) LIKE '%DOUBLE%'"
        q = base + "/query?" + urllib.parse.urlencode({
            "where": where, "outFields": ",".join([name_f, *time_f][:4]), "returnGeometry": "false",
            "resultRecordCount": 50, "f": "json"})
        res = fetch(q, "GET", 1_000_000)
        rows = []
        if res.get("status") == 200:
            try:
                rows = [ft["attributes"] for ft in json.loads(res["_body"]).get("features", [])]
            except Exception:
                pass
        out["pipeline_haywire"].append({"service": s["name"], "name_field": name_f, "time_fields": time_f,
                                        "status": res.get("status"), "n": len(rows), "rows": rows[:50]})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="where the probe runs, e.g. build-mac or cloud-session")
    ap.add_argument("--skip-crawl", action="store_true")
    a = ap.parse_args(argv)
    du = shutil.disk_usage(PROJECT)
    report = {
        "label": a.label, "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "platform": platform.platform(), "machine": platform.machine(), "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(), "https_proxy_set": bool(os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")),
        "disk": {"path": str(PROJECT), "free_gb": round(du.free / 1e9, 1), "total_gb": round(du.total / 1e9, 1),
                 "required_free_gb": 30, "ok": du.free / 1e9 >= 30},
        "checks": [],
    }
    bodies = {}
    for cid, purpose, url, method, mx, hdr in CHECKS:
        rec = fetch_retry(url, method, mx, hdr)
        bodies[cid] = rec.pop("_body", b"")
        rec.update(id=cid, purpose=purpose)
        report["checks"].append(rec)
        print(f"{cid:24s} {str(rec.get('status')):>5s} {rec.get('error', rec.get('reason', ''))[:90]}")
    if not a.skip_crawl:
        report["nirops_inventory"] = nirops_inventory()
        if bodies.get("nifc_services"):
            report["nifc_perimeters"] = nifc_perimeter_services(bodies["nifc_services"])
    for rec in report.get("nirops_inventory", {}).get("fires", {}).values():
        rec["n_ir_files"] = len(rec["ir_files"])
    out = PROJECT / "provenance" / f"probe_{a.label}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\ndisk free {report['disk']['free_gb']} GB (need >= 30): {'OK' if report['disk']['ok'] else 'NOT OK'}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
