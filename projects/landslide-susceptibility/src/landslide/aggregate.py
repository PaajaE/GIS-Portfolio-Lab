"""Slope-unit table (PLAN §3): predictors aggregated over each unit's domain cells, labels, HUC-12, county.

For each threshold A (0.05 / 0.1 / 0.2 km^2) -> data/out/units_<A>.parquet with one row per unit that touches
the counties:
* area_km2 (all cells), domain_km2 (triggered, valid, in county), domain_share
* continuous predictors over domain cells: mean and sd; slope also p90 (initiation favours the steepest part)
* categorical predictors: area fraction per class (lc_group, geology, hsg)
* label: unit contains >= 1 representative point of a primary-rule positive polygon; n_sources
* huc12 and county: majority over domain cells (ties -> lower code)
Units with domain_share < 0.5 are kept in the table but flagged; the model stage decides on inclusion.
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize

from . import config as C
from .hydro import to5
from .inventory import positive_mask
from .labels import HYDRO_LAYERS, REGION, UNIT_THRESHOLDS, counties, inventory, read
from .terrain import LAYERS as TERRAIN_LAYERS

CONTINUOUS = tuple(k for k in TERRAIN_LAYERS) + HYDRO_LAYERS + ("canopy", "rain_mm", "bedrock_cm")
CATEGORICAL = {"lc_group": range(1, 7), "geology": range(0, 5), "hsg": range(0, 5)}


def unit_raster_5m(a_km2: str, shape5) -> tuple[np.ndarray, rasterio.Affine]:
    with rasterio.open(C.INTERIM / f"units_{REGION}" / f"units_{a_km2}.tif") as s:
        lab, tr10 = s.read(1), s.transform
    with rasterio.open(C.INTERIM / f"dem_5m_{REGION}.tif") as d:
        tr5 = d.transform
    off = (int(round((tr5.f - tr10.f) / C.CELL_M)), int(round((tr10.c - tr5.c) / C.CELL_M)))
    return to5(lab, off, shape5, np.uint32(0)), tr10


def majority(units: np.ndarray, codes: np.ndarray, n_units: int) -> np.ndarray:
    """Most frequent code per unit (ties -> lower code); 0 where the unit has no cells."""
    key = units.astype(np.int64) * (codes.max() + 1) + codes
    k, c = np.unique(key, return_counts=True)
    u, code = np.divmod(k, codes.max() + 1)
    order = np.lexsort((code, -c, u))
    u, code = u[order], code[order]
    first = np.r_[True, u[1:] != u[:-1]]
    out = np.zeros(n_units, np.int64)
    out[u[first]] = code[first]
    return out


def run() -> dict:
    dom = read(C.INTERIM / f"labels_{REGION}" / "domain.tif").astype(bool)
    shape = dom.shape
    cty = counties()
    with rasterio.open(C.INTERIM / f"dem_5m_{REGION}.tif") as d:
        tr5 = d.transform
    county = rasterize(((g, i + 1) for i, g in enumerate(cty.geometry)), out_shape=shape, transform=tr5, fill=0,
                       dtype=np.uint8)
    huc = gpd.read_parquet(C.RAW / "huc12.parquet").to_crs(C.CRS).reset_index(drop=True)
    huc_r = rasterize(((g, i + 1) for i, g in enumerate(huc.geometry)), out_shape=shape, transform=tr5, fill=0,
                      dtype=np.uint16)
    inv = inventory()
    pts = inv[positive_mask(inv)].geometry.representative_point()
    pts = pts[pts.within(cty.union_all())]  # sources inside Buncombe + Yancey only
    C.OUT.mkdir(parents=True, exist_ok=True)
    rep = {}
    didx = np.flatnonzero(dom.ravel())
    for a_km2 in UNIT_THRESHOLDS:
        u5, tr10 = unit_raster_5m(a_km2, shape)
        uflat = u5.ravel()
        n = int(uflat.max()) + 1
        in_cty_units = np.unique(uflat[county.ravel() > 0])
        in_cty_units = in_cty_units[in_cty_units > 0]
        area = np.bincount(uflat, minlength=n)
        ud = uflat[didx]
        dcount = np.bincount(ud, minlength=n)
        df = pd.DataFrame({"unit": in_cty_units})
        df["area_km2"] = area[in_cty_units] * C.CELL_M**2 / 1e6
        df["domain_km2"] = dcount[in_cty_units] * C.CELL_M**2 / 1e6
        df["domain_share"] = df["domain_km2"] / df["area_km2"]
        safe = np.maximum(dcount, 1)
        for k in CONTINUOUS:
            group = (f"terrain_{REGION}" if k in TERRAIN_LAYERS else
                     f"hydro_{REGION}" if k in HYDRO_LAYERS else f"stack_{REGION}")
            v = read(C.INTERIM / group / f"{k}.tif").ravel()[didx].astype(np.float64)
            s1 = np.bincount(ud, weights=v, minlength=n)
            s2 = np.bincount(ud, weights=v * v, minlength=n)
            m = s1 / safe
            df[f"{k}_mean"] = np.where(dcount > 0, m, np.nan)[in_cty_units]
            df[f"{k}_sd"] = np.where(dcount > 0, np.sqrt(np.maximum(s2 / safe - m * m, 0)), np.nan)[in_cty_units]
            if k == "slope_deg":
                order = np.lexsort((v, ud))
                us, vs = ud[order], v[order]
                start = np.searchsorted(us, np.arange(n))
                p90 = np.full(n, np.nan)
                has = dcount > 0
                pos90 = start[has] + np.floor(0.9 * (dcount[has] - 1)).astype(np.int64)
                p90[has] = vs[pos90]
                df["slope_deg_p90"] = p90[in_cty_units]
            del v
        for k, classes in CATEGORICAL.items():
            v = read(C.INTERIM / f"stack_{REGION}" / f"{k}.tif").ravel()[didx].astype(np.int64)
            for c in classes:
                df[f"{k}_{c}_frac"] = (np.bincount(ud, weights=(v == c).astype(np.float64), minlength=n) / safe)[
                    in_cty_units]
        df["county"] = majority(ud, county.ravel()[didx].astype(np.int64), n)[in_cty_units]
        hm = majority(ud, huc_r.ravel()[didx].astype(np.int64), n)[in_cty_units]
        df["huc12"] = np.where(hm > 0, huc["huc12"].to_numpy()[np.maximum(hm, 1) - 1], None)
        # labels: representative points of positive polygons -> unit at 10 m
        rr, cc = rasterio.transform.rowcol(tr10, pts.x.to_numpy(), pts.y.to_numpy())
        with rasterio.open(C.INTERIM / f"units_{REGION}" / f"units_{a_km2}.tif") as s:
            lab10 = s.read(1)
        rr, cc = np.asarray(rr), np.asarray(cc)
        ok = (rr >= 0) & (rr < lab10.shape[0]) & (cc >= 0) & (cc < lab10.shape[1])
        pu = lab10[rr[ok], cc[ok]]
        ns = np.bincount(pu, minlength=n)
        df["n_sources"] = ns[in_cty_units]
        df["label"] = (df["n_sources"] > 0).astype(np.int8)
        df["in_model_domain"] = df["domain_share"] >= 0.5
        df.to_parquet(C.OUT / f"units_{a_km2}.parquet", index=False)
        m = df[df["in_model_domain"]]
        rep[a_km2] = {"units_touching_counties": int(len(df)), "units_in_model_domain": int(len(m)),
                      "positive_units": int(m["label"].sum()), "positive_share": float(m["label"].mean()),
                      "sources_in_model_units": int(m["n_sources"].sum()),
                      "sources_in_counties": int(len(pts)), "sources_in_any_unit": int(ns[1:].sum())}
        print(a_km2, rep[a_km2], flush=True)
        del u5, uflat, ud
    (C.OUT / "units_report.json").write_text(json.dumps(rep, indent=1))
    return rep


if __name__ == "__main__":
    run()
