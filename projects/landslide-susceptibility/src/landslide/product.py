"""Product layer (owner decision 2026-10-10: the 5 m logistic regression is the product; METHOD §Validation).

* Final model: the 5 m LR fitted on all hillslope training cells (all positives + 1:10 negatives, seeded), scored
  on every hillslope domain cell at the reference rainfall -> data/interim/scores_aoi/final_lr_5m.tif.
* Area percentiles: every score raster is converted to its rank among all hillslope domain cells, as
  1..100 = "in the top k % of hillslope area" (1 = most susceptible), 0 = not ranked. Written for the final model,
  the out-of-fold LR and GBM (M5) and slope alone -> rank_<name>.tif (uint8).
* Per-k metrics (k = 1..30 % of hillslope area): share of mapped primary initiation sites (one representative
  point per polygon) whose cell lies in the top k %, from the **out-of-fold** ranks, with HUC-12 block-bootstrap
  intervals -> validation/per_k_metrics.json. The final-model map is shown; the numbers are held-out.
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window

from . import config as C
from .advanced import WINDOW_ROWS
from .baseline import NEG_RATIO, PIXEL_NAMES, PIXEL_PROTECTED, LR, pixel_matrix
from .inventory import positive_mask
from .labels import HYDRO_LAYERS, REGION, STACK_FLOAT, STACK_INT, counties, inventory, read
from .metrics import block_bootstrap, ci
from .terrain import LAYERS as TERRAIN_LAYERS

SCORES = C.INTERIM / f"scores_{REGION}"
KS = np.arange(1, 31)
N_BOOT = 2000


def rain_reference() -> float:
    d = pd.read_parquet(C.INTERIM / f"labels_{REGION}" / "domain_sample.parquet", columns=["rain_mm"])
    return float(np.median(d["rain_mm"]))


def training_cells() -> pd.DataFrame:
    lab = C.INTERIM / f"labels_{REGION}"
    pos = pd.read_parquet(lab / "positives.parquet")
    neg = pd.read_parquet(lab / "negatives.parquet")
    pos, neg = (t[(t["hillslope"] == 1) & t["huc12"].notna()] for t in (pos, neg))
    return pd.concat([pos, neg], ignore_index=True)


def thin_all(y: np.ndarray, seed: int = C.SEED) -> np.ndarray:
    rng = np.random.default_rng(seed)
    p, n = np.flatnonzero(y == 1), np.flatnonzero(y == 0)
    return np.r_[p, rng.choice(n, size=min(len(n), NEG_RATIO * len(p)), replace=False)]


def fit_final(df: pd.DataFrame, rows: np.ndarray | None = None) -> LR:
    X, y = pixel_matrix(df), df["label"].to_numpy()
    idx = thin_all(y) if rows is None else rows
    return LR(PIXEL_NAMES, PIXEL_PROTECTED).fit(X[idx], y[idx])


def predictor_windows(rain_ref: float):
    """Yield (window, hillslope-domain mask, predictor frame at the reference rainfall) in row bands."""
    lab = C.INTERIM / f"labels_{REGION}"
    dom = read(lab / "domain.tif").astype(bool)
    dom &= read(lab / "hillslope.tif").astype(bool)
    paths = {k: C.INTERIM / f"terrain_{REGION}" / f"{k}.tif" for k in TERRAIN_LAYERS}
    paths |= {k: C.INTERIM / f"hydro_{REGION}" / f"{k}.tif" for k in HYDRO_LAYERS}
    paths |= {k: C.INTERIM / f"stack_{REGION}" / f"{k}.tif" for k in STACK_FLOAT + STACK_INT}
    srcs = {k: rasterio.open(p) for k, p in paths.items()}
    try:
        for r0 in range(0, dom.shape[0], WINDOW_ROWS):
            nr = min(WINDOW_ROWS, dom.shape[0] - r0)
            win = Window(0, r0, dom.shape[1], nr)
            sel = dom[r0:r0 + nr]
            df = pd.DataFrame({k: s.read(1, window=win)[sel] for k, s in srcs.items()})
            df["rain_mm"] = rain_ref
            yield win, sel, df
    finally:
        for s in srcs.values():
            s.close()


def float_profile():
    with rasterio.open(C.INTERIM / f"dem_5m_{REGION}.tif") as d:
        return {"driver": "GTiff", "count": 1, "dtype": "float32", "nodata": np.nan, "crs": d.crs,
                "transform": d.transform, "height": d.height, "width": d.width, "compress": "deflate",
                "predictor": 3, "tiled": True, "blockxsize": 256, "blockysize": 256}


def score_final(model: LR, rain_ref: float, path) -> None:
    with rasterio.open(path, "w", **float_profile()) as dst:
        for win, sel, df in predictor_windows(rain_ref):
            tile = np.full(sel.shape, np.nan, np.float32)
            if sel.any():
                tile[sel] = model.linear(pixel_matrix(df))
            dst.write(tile, 1, window=win)


def area_rank(score: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """1..100 = top-k % of the masked area by descending score (ceil), 0 outside the mask or where NaN."""
    ok = mask & np.isfinite(score)
    v = score[ok]
    order = np.argsort(-v, kind="stable")
    r = np.empty(v.size, np.int64)
    r[order] = np.arange(v.size)
    out = np.zeros(score.shape, np.uint8)
    out[ok] = np.ceil((r + 1) * 100 / v.size).astype(np.uint8)
    return out


def write_rank(name: str, score: np.ndarray, mask: np.ndarray) -> np.ndarray:
    rk = area_rank(score, mask)
    p = float_profile() | {"dtype": "uint8", "nodata": 0, "predictor": 1}
    with rasterio.open(SCORES / f"rank_{name}.tif", "w", **p) as dst:
        dst.write(rk, 1)
    return rk


def site_cells() -> pd.DataFrame:
    """Representative point of every primary positive polygon in the counties, with its 5 m cell."""
    inv, cty = inventory(), counties()
    pts = inv[positive_mask(inv)].geometry.representative_point()
    pts = pts[pts.within(cty.union_all())]
    with rasterio.open(C.INTERIM / f"dem_5m_{REGION}.tif") as d:
        r, c = rasterio.transform.rowcol(d.transform, pts.x.to_numpy(), pts.y.to_numpy())
    return pd.DataFrame({"x": pts.x.to_numpy(), "y": pts.y.to_numpy(), "row": np.asarray(r), "col": np.asarray(c)})


def per_k(ranks: dict, sites: pd.DataFrame, huc_sites: np.ndarray, in_domain: np.ndarray) -> dict:
    """Capture of initiation sites in the top k % (sites outside the ranked area count as not captured)."""
    out = {"k_pct": KS.tolist(), "sites_in_domain": int(in_domain.sum())}
    hs = huc_sites[in_domain]
    for name, rk in ranks.items():
        r = rk[sites["row"], sites["col"]][in_domain].astype(np.int64)
        hit = (r[:, None] >= 1) & (r[:, None] <= KS[None, :])

        def stat(w, hit=hit):
            return (hit * w[:, None]).sum(0) / w.sum()

        point = stat(np.ones(len(r)))
        reps = block_bootstrap(hs, stat, N_BOOT, C.SEED)
        lo_hi = ci(reps)
        out[name] = {"capture": point.round(4).tolist(), "ci95_low": lo_hi[:, 0].round(4).tolist(),
                     "ci95_high": lo_hi[:, 1].round(4).tolist(), "sites_unranked": int((r == 0).sum())}
    return out


def run() -> dict:
    rain_ref = rain_reference()
    df = training_cells()
    fin = fit_final(df)
    SCORES.mkdir(parents=True, exist_ok=True)
    score_final(fin, rain_ref, SCORES / "final_lr_5m.tif")
    lab = C.INTERIM / f"labels_{REGION}"
    mask = read(lab / "domain.tif").astype(bool) & read(lab / "hillslope.tif").astype(bool)
    ranks = {}
    for name, path in (("final_lr", SCORES / "final_lr_5m.tif"), ("oof_lr", SCORES / "oof_lr_5m.tif"),
                       ("oof_gbm", SCORES / "oof_gbm_5m.tif"),
                       ("slope", C.INTERIM / f"terrain_{REGION}" / "slope_deg.tif")):
        ranks[name] = write_rank(name, read(path).astype(np.float32), mask)
    sites = site_cells()
    dom = read(lab / "domain.tif").astype(bool)
    shape = dom.shape
    inside = (sites["row"].between(0, shape[0] - 1) & sites["col"].between(0, shape[1] - 1)).to_numpy()
    in_domain = inside.copy()
    in_domain[inside] = dom[sites["row"][inside], sites["col"][inside]]
    sites = sites.assign(row=sites["row"].clip(0, shape[0] - 1), col=sites["col"].clip(0, shape[1] - 1))
    huc = gpd.read_parquet(C.RAW / "huc12.parquet").to_crs(C.CRS)
    j = gpd.sjoin(gpd.GeoDataFrame(geometry=gpd.points_from_xy(sites["x"], sites["y"]), crs=C.CRS),
                  huc[["huc12", "geometry"]], predicate="within", how="left")
    huc_sites = j.groupby(level=0)["huc12"].first().fillna("none").to_numpy()
    res = per_k({k: ranks[k] for k in ("oof_lr", "oof_gbm", "slope", "final_lr")}, sites, huc_sites, in_domain)
    res["note"] = ("capture = share of mapped primary Helene initiation sites (representative point per polygon) "
                   "inside the triggered domain whose 5 m cell lies in the top k % of hillslope area; oof_* = held-out "
                   "(leave-one-HUC-12-out) ranks, final_lr = in-sample (not a validation number)")
    res["rain_reference_mm"] = rain_ref
    res["hillslope_cells_ranked"] = {k: int((v > 0).sum()) for k, v in ranks.items()}
    res["final_model_coefficients"] = fin.coefs()
    (C.VALIDATION / "per_k_metrics.json").write_text(json.dumps(res, indent=1))
    print({k: (res[k]["capture"][4], res[k]["capture"][9], res[k]["capture"][19]) for k in ("oof_lr", "oof_gbm", "slope", "final_lr")},
          flush=True)
    return res


if __name__ == "__main__":
    run()
