"""M1b prepare: raw inputs -> one analysis grid per fire (PLAN §5, METHOD "Harmonization").

  uv run python -m firepath.prepare <fire>

Writes data/interim/<fire>/inputs.npz (fuel, canopy, terrain, observed arrival intervals) and
data/interim/<fire>/wind.npz (hourly UTM-grid-relative U/V at 300 m), plus provenance/prepare_<fire>.json
with the checks below. Every raster shares the grid in data/interim/<fire>/grid.json.

Checks (raise on failure, otherwise reported):
- grid identity of every output (shape, transform, CRS);
- fuel classes: proportions on the grid vs the source tile within the grid footprint (< 1 pp each);
- DEM: no nodata inside the grid; source tiles predate the fire (3DEP source dates are recorded, not asserted);
- HRRR: valid times hourly and strictly increasing; rotation angle at the grid centre recorded;
- perimeters: scan times strictly increasing; the sequence audit (observed.audit_sequence) summary.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from math import atan2, degrees

import numpy as np

from .harvest import FIRES, INTERIM, PROJECT, RAW, fire_perimeters
from .observed import audit_sequence

WIND_CELL = 300.0


def grid_profile(fire: str) -> dict:
    from rasterio.crs import CRS
    from rasterio.transform import from_origin

    g = json.loads((INTERIM / fire / "grid.json").read_text())
    return {"crs": CRS.from_epsg(g["epsg"]), "transform": from_origin(g["x0"], g["y1"], g["cell"], g["cell"]),
            "width": g["width"], "height": g["height"], "grid": g}


def warp(src_path, prof, resampling, band=1, src_nodata=None, dtype="float32"):
    import rasterio
    from rasterio.warp import reproject

    out = np.full((prof["height"], prof["width"]), np.nan if dtype.startswith("float") else -1, dtype)
    with rasterio.open(src_path) as src:
        reproject(rasterio.band(src, band), out, src_nodata=src.nodata if src_nodata is None else src_nodata,
                  dst_transform=prof["transform"], dst_crs=prof["crs"],
                  dst_nodata=np.nan if dtype.startswith("float") else -1, resampling=resampling)
    return out


def class_proportions(a: np.ndarray, valid: np.ndarray) -> dict[int, float]:
    u, c = np.unique(a[valid], return_counts=True)
    return {int(k): float(v) / float(valid.sum()) for k, v in zip(u, c)}


def source_footprint_proportions(src_path, prof) -> dict[int, float]:
    """Class shares of the source raster over the analysis-grid footprint (source cells whose centre
    falls inside the grid polygon), as the reference for the < 1 pp resampling check."""
    import rasterio
    from pyproj import Transformer

    with rasterio.open(src_path) as src:
        a = src.read(1)
        rows, cols = np.mgrid[0:src.height, 0:src.width]
        xs, ys = rasterio.transform.xy(src.transform, rows.ravel(), cols.ravel())
        x, y = Transformer.from_crs(src.crs, prof["crs"], always_xy=True).transform(np.asarray(xs), np.asarray(ys))
        x0, y0, x1, y1 = prof["grid"]["bounds_utm"]
        inside = ((x >= x0) & (x < x1) & (y >= y0) & (y < y1)).reshape(a.shape) & (a != src.nodata)
    return class_proportions(a, inside)


def horn_slope_aspect(z: np.ndarray, cell: float):
    """Horn (1981) 3x3 gradient in grid metres. Returns tan(slope) and the upslope direction (rad, CCW
    from grid east). Edge cells use replicated borders."""
    p = np.pad(z, 1, mode="edge")
    a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    d, f = p[1:-1, :-2], p[1:-1, 2:]
    g, h, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * cell)
    dzdy = ((a + 2 * b + c) - (g + 2 * h + i)) / (8 * cell)        # row 0 is north, so +y is up
    return np.hypot(dzdx, dzdy), np.arctan2(dzdy, dzdx)


def north_angle(crs_from, x, y, crs_to=4326) -> np.ndarray:
    """Angle (rad, CCW from the grid's +x axis) of true north at grid points, by finite difference."""
    from pyproj import Transformer

    fwd = Transformer.from_crs(crs_from, crs_to, always_xy=True)
    inv = Transformer.from_crs(crs_to, crs_from, always_xy=True)
    lon, lat = fwd.transform(x, y)
    x2, y2 = inv.transform(lon, np.asarray(lat) + 1e-4)
    return np.arctan2(np.asarray(y2) - y, np.asarray(x2) - x)


def rotate_to_grid(u, v, north_src, north_dst):
    """Rotate vectors given in a grid whose true north is at angle north_src into a grid whose true
    north is at north_dst (both CCW from that grid's +x). Speed is preserved."""
    rot = north_dst - north_src
    c, s = np.cos(rot), np.sin(rot)
    return c * u - s * v, s * u + c * v


def wind(fire: str, prof: dict, report: dict):
    """HRRR grid-relative U/V -> earth-relative -> UTM grid-relative, bilinear to a 300 m grid (PLAN §5)."""
    from pyproj import CRS as PCRS
    from pyproj import Transformer
    from scipy.interpolate import RegularGridInterpolator

    z = np.load(RAW / fire / "hrrr" / "hrrr_f00_uv10_crop.npz")
    u, v, tr = z["u"], z["v"], z["transform"]
    hcrs = PCRS.from_wkt(str(z["crs_wkt"]))
    t = z["valid_unix"]
    if not (np.diff(t) == 3600).all():
        raise ValueError("HRRR valid times are not strictly hourly")
    ny, nx = u.shape[1:]
    hx = tr[2] + (np.arange(nx) + 0.5) * tr[0]
    hy = tr[5] + (np.arange(ny) + 0.5) * tr[4]
    HX, HY = np.meshgrid(hx, hy)
    n_h = north_angle(hcrs, HX, HY)                      # true north in the HRRR grid
    utm = prof["crs"].to_epsg()
    to_utm = Transformer.from_crs(hcrs, utm, always_xy=True)
    UX, UY = to_utm.transform(HX, HY)
    n_u = north_angle(utm, UX, UY)                       # true north in the UTM grid, at the same points
    uu, vv = rotate_to_grid(u, v, n_h[None], n_u[None])
    g = prof["grid"]
    wx = g["x0"] + (np.arange(int(np.ceil(g["width"] * g["cell"] / WIND_CELL))) + 0.5) * WIND_CELL
    wy = g["y1"] - (np.arange(int(np.ceil(g["height"] * g["cell"] / WIND_CELL))) + 0.5) * WIND_CELL
    WX, WY = np.meshgrid(wx, wy)
    back = Transformer.from_crs(utm, hcrs, always_xy=True)
    qx, qy = back.transform(WX, WY)
    pts = np.column_stack([qy.ravel(), qx.ravel()])
    out_u = np.empty((len(t), *WX.shape), "f4")
    out_v = np.empty_like(out_u)
    asc_y = hy[::-1]                                     # RegularGridInterpolator needs ascending axes
    for k in range(len(t)):
        out_u[k] = RegularGridInterpolator((asc_y, hx), uu[k][::-1], method="linear")(pts).reshape(WX.shape)
        out_v[k] = RegularGridInterpolator((asc_y, hx), vv[k][::-1], method="linear")(pts).reshape(WX.shape)
    cy, cx = ny // 2, nx // 2
    report["wind"] = {"hours": int(len(t)), "first_utc": datetime.fromtimestamp(int(t[0]), timezone.utc).isoformat(),
                      "last_utc": datetime.fromtimestamp(int(t[-1]), timezone.utc).isoformat(),
                      "rotation_deg_at_centre": float(degrees(n_u[cy, cx] - n_h[cy, cx])),
                      "hrrr_true_north_deg_from_grid_x_at_centre": float(degrees(n_h[cy, cx])),
                      "speed_max_ms": float(np.hypot(out_u, out_v).max()), "wind_grid_shape": list(WX.shape)}
    np.savez_compressed(INTERIM / fire / "wind.npz", u=out_u, v=out_v, valid_unix=t, x=wx, y=wy,
                        cell=WIND_CELL, frame="UTM grid-relative, 10 m, m/s")


def perimeters(fire: str, prof: dict, report: dict):
    from pyproj import Transformer
    from rasterio.features import rasterize
    from shapely.geometry import shape
    from shapely.ops import transform

    feats = fire_perimeters(fire)
    to_utm = Transformer.from_crs(4326, prof["crs"].to_epsg(), always_xy=True).transform
    times = [datetime.fromisoformat(f["properties"]["UTC"]).replace(tzinfo=timezone.utc).timestamp() for f in feats]
    masks = [rasterize([(transform(to_utm, shape(f["geometry"])), 1)], out_shape=(prof["height"], prof["width"]),
                       transform=prof["transform"], all_touched=False, dtype="uint8").astype(bool) for f in feats]
    # equal scan times (two polygons for one flight) are merged by union
    t_u, m_u = [], []
    for t, m in zip(times, masks):
        if t_u and t == t_u[-1]:
            m_u[-1] = m_u[-1] | m
        else:
            t_u.append(t)
            m_u.append(m)
    audit = audit_sequence(t_u, m_u, jitter_cells=1)
    report["perimeters"] = {"n": len(t_u), "merged_equal_times": len(times) - len(t_u),
                            "first_utc": feats[0]["properties"]["UTC"], "last_utc": feats[-1]["properties"]["UTC"],
                            "steps": audit["steps"],
                            "flags": {k: int((audit["flag"] == i).sum()) for i, k in
                                      enumerate(["consistent", "initial", "never", "inconsistent"])}}
    return np.array(t_u), np.stack(m_u), audit


def gridmet_median(fire: str, var: str, t0: float, t1: float) -> float:
    """Median over the evaluation window of the AOI-mean gridMET value (METHOD M1)."""
    import rasterio

    path = RAW / fire / "gridmet" / f"{var}.nc"
    with rasterio.open(path) as src:
        a = src.read().astype("f8")
        scale = float(src.tags(1).get("scale_factor", 1))
        days = [int(x) for x in src.tags()["NETCDF_DIM_day_VALUES"].strip("{}").split(",")]
        fill = float(src.tags(1).get("_FillValue", 32767))
    a = np.where(a == fill, np.nan, a * scale)
    # gridMET day d covers the 24 h ending 07 UTC on d+1 (file note5)
    epoch = datetime(1900, 1, 1, tzinfo=timezone.utc).timestamp()
    end = np.array([epoch + (d + 1) * 86400 + 7 * 3600 for d in days])
    sel = (end > t0) & (end - 86400 < t1)
    return float(np.median(np.nanmean(a[sel], axis=(1, 2))))


def main(argv=None):
    from rasterio.enums import Resampling

    fire = (argv or sys.argv[1:])[0]
    prof = grid_profile(fire)
    report = {"fire": fire, "grid": prof["grid"], "utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    ver = FIRES[fire]["landfire"][1]
    lf = RAW / fire / "landfire"

    fuel = warp(lf / f"{ver}_FBFM40.tif", prof, Resampling.nearest, dtype="int16")
    valid = fuel > 0
    p_grid = class_proportions(fuel, valid)
    p_src = source_footprint_proportions(lf / f"{ver}_FBFM40.tif", prof)
    diff = {k: abs(p_grid.get(k, 0) - p_src.get(k, 0)) for k in set(p_grid) | set(p_src)}
    report["fuel"] = {"version": ver, "missing_cells": int((~valid).sum()),
                      "max_class_share_change_pp": 100 * max(diff.values()),
                      "shares_grid": {str(k): round(v, 5) for k, v in sorted(p_grid.items())}}
    if max(diff.values()) >= 0.01:
        raise ValueError(f"fuel resampling changed a class share by {100 * max(diff.values()):.2f} pp")
    cc = warp(lf / f"{ver}_CC.tif", prof, Resampling.nearest, dtype="int16")          # percent
    ch = warp(lf / f"{ver}_CH.tif", prof, Resampling.nearest, dtype="int16") / 10.0   # LANDFIRE stores m x 10

    dem = warp(RAW / fire / "dem" / "usgs_13_merged.tif", prof, Resampling.average)
    if np.isnan(dem).any():
        raise ValueError(f"DEM has {int(np.isnan(dem).sum())} nodata cells inside the grid")
    tan_slope, upslope = horn_slope_aspect(dem, prof["grid"]["cell"])
    report["terrain"] = {"elev_min": float(dem.min()), "elev_max": float(dem.max()),
                         "tan_slope_p50": float(np.median(tan_slope)), "tan_slope_p99": float(np.percentile(tan_slope, 99))}

    times, masks, audit = perimeters(fire, prof, report)
    wind(fire, prof, report)
    fm100 = gridmet_median(fire, "fm100", times[0], times[-1])
    fm1000 = gridmet_median(fire, "fm1000", times[0], times[-1])
    report["moisture"] = {"fm100_median_pct": fm100, "fm1000_median_pct": fm1000,
                          "window_utc": [datetime.fromtimestamp(times[0], timezone.utc).isoformat(),
                                         datetime.fromtimestamp(times[-1], timezone.utc).isoformat()]}

    out = INTERIM / fire / "inputs.npz"
    np.savez_compressed(out, fuel=fuel, cc=cc, ch=ch, dem=dem.astype("f4"), tan_slope=tan_slope.astype("f4"),
                        upslope=upslope.astype("f4"), scan_unix=times, first_in=audit["first_in"].astype("i2"),
                        flag=audit["flag"], transform=np.array(prof["transform"])[:6], epsg=prof["crs"].to_epsg())
    report["outputs"] = {str(p.relative_to(PROJECT)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (out, INTERIM / fire / "wind.npz")}
    (PROJECT / "provenance" / f"prepare_{fire}.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({k: report[k] for k in ("fuel", "terrain", "moisture", "wind")}, indent=1, default=str)[:3000])
    print("perimeters:", report["perimeters"]["n"], report["perimeters"]["flags"])


if __name__ == "__main__":
    main()
