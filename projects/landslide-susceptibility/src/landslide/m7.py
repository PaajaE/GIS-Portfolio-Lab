"""M7 (simplified, owner 2026-10-24): frozen story sites with before/after imagery, and a frozen hand-check sample.

Story sites: 2 km x 2 km squares on the UTM lattice (multiples of 2,000 m), chosen by a fixed rule:
  S1 / S2 - most mapped primary initiation sites, in Buncombe and in Yancey (square >= 50 % in the domain);
  S3 - "high ranking, no mapped initiation": no mapped site, >= 80 % in the domain, mean 72 h rainfall >= 350 mm,
       largest share of top-10 % (final model) hillslope cells;
  S4 - "missed": most mapped sites whose held-out rank is outside the top 30 %.
Imagery (display only, never a model input): NC OneMap Orthoimagery 2020-2023 (before; credit NC911, NCCGIA) and
Helene 2025 (after; credit NC Collaboratory at UNC Chapel Hill), exportImage at 1 m, 2,000 px JPEG per epoch,
plus a transparent PNG of the site's top-10 % cells and the mapped sites as fractional coordinates.
Hand-check sample: 40 seeded locations (15 held-out hits, 15 top-10 % cells without mapped initiation, 10
misses), with empty review columns. Nothing is reviewed yet.
Writes validation/story_sites.json, validation/hand_check_sample.csv, web/data/sites/.
"""

from __future__ import annotations

import io
import json
import time
import urllib.parse
import urllib.request

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.io import MemoryFile
from rasterio.windows import from_bounds

from . import config as C
from .labels import REGION, counties, read
from .product import SCORES, site_cells

SQ = 2000
IMG_PX = 2000
ORTHO = {
    "before": ("https://services.nconemap.gov/secure/rest/services/Imagery/Orthoimagery_2020_2023/ImageServer",
               "NC OneMap Orthoimagery 2020–2023 (NC911, NCCGIA)"),
    "after": ("https://services.nconemap.gov/secure/rest/services/Imagery/Orthoimagery_Helene_2025/ImageServer",
              "NC OneMap Orthoimagery Helene 2025 (NC Collaboratory at UNC Chapel Hill)"),
}
CITATION = ("NC OneMap (2019). North Carolina Department of Information Technology, Government Data Analytics "
            "Center, Center for Geographic Information and Analysis. Available at www.nconemap.gov.")
SITES_DIR = C.ROOT / "web" / "data" / "sites"


def square_table() -> pd.DataFrame:
    lab = C.INTERIM / f"labels_{REGION}"
    dom = read(lab / "domain.tif").astype(bool)
    hill = read(lab / "hillslope.tif").astype(bool) & dom
    rk_f = read(SCORES / "rank_final_lr.tif")
    rk_o = read(SCORES / "rank_oof_lr.tif")
    rain = read(C.INTERIM / f"stack_{REGION}" / "rain_mm.tif")
    with rasterio.open(C.INTERIM / f"dem_5m_{REGION}.tif") as d:
        tr = d.transform
    n = SQ // C.CELL_M  # 400 cells per square side
    c0 = int(np.ceil(tr.c / SQ) * SQ - tr.c) // C.CELL_M  # first column on a 2 km boundary
    r0 = int(tr.f - np.floor(tr.f / SQ) * SQ) // C.CELL_M  # first row on a 2 km boundary (y decreases)
    nr, nc = (dom.shape[0] - r0) // n, (dom.shape[1] - c0) // n

    def blocks(a):
        return a[r0:r0 + nr * n, c0:c0 + nc * n].reshape(nr, n, nc, n).sum((1, 3), dtype=np.float64)

    t10 = hill & (rk_f >= 1) & (rk_f <= 10)
    df = pd.DataFrame({"domain": blocks(dom).ravel(), "hill": blocks(hill).ravel(), "top10": blocks(t10).ravel(),
                       "rain_sum": blocks(np.where(dom, rain, np.float32(0))).ravel()})
    ii, jj = np.divmod(np.arange(nr * nc), nc)
    df["x0"] = tr.c + (c0 + jj * n) * C.CELL_M
    df["y0"] = tr.f - (r0 + (ii + 1) * n) * C.CELL_M
    df["key"] = np.arange(len(df))
    df["domain_share"] = df["domain"] / n ** 2
    df["rain_mean"] = df["rain_sum"] / df["domain"].clip(lower=1)
    df["top10_share"] = df["top10"] / df["hill"].clip(lower=1)
    s = site_cells()
    ok = s["row"].between(0, dom.shape[0] - 1) & s["col"].between(0, dom.shape[1] - 1)
    s = s[ok].reset_index(drop=True)
    s["in_domain"] = dom[s["row"], s["col"]]
    s["rank_oof"] = rk_o[s["row"], s["col"]]
    s["rank_final"] = rk_f[s["row"], s["col"]]
    s["sq_x0"], s["sq_y0"] = np.floor(s["x"] / SQ) * SQ, np.floor(s["y"] / SQ) * SQ
    agg = s[s["in_domain"]].groupby(["sq_x0", "sq_y0"]).agg(
        sites=("x", "size"), misses=("rank_oof", lambda r: int(((r == 0) | (r > 30)).sum())))
    df = df.merge(agg, left_on=["x0", "y0"], right_index=True, how="left").fillna({"sites": 0, "misses": 0})
    cty = counties()
    cen = gpd.GeoSeries(gpd.points_from_xy(df["x0"] + SQ / 2, df["y0"] + SQ / 2), crs=C.CRS)
    df["county"] = None
    for name, g in zip(cty["NAME"], cty.geometry):
        df.loc[cen.within(g).to_numpy(), "county"] = name
    return df, s


def pick_sites(df: pd.DataFrame) -> list[dict]:
    rule = {
        "S1": ("Most mapped initiation sites, Buncombe", (df["county"] == "Buncombe County") & (df["domain_share"] >= 0.5), "sites"),
        "S2": ("Most mapped initiation sites, Yancey", (df["county"] == "Yancey County") & (df["domain_share"] >= 0.5), "sites"),
        "S3": ("Ranked high, no mapped initiation", (df["sites"] == 0) & (df["domain_share"] >= 0.8) & (df["rain_mean"] >= 350), "top10_share"),
        "S4": ("Mapped initiations the ranking missed", df["domain_share"] >= 0.5, "misses"),
    }
    out = []
    for sid, (title, m, by) in rule.items():
        r = df[m].sort_values([by, "key"], ascending=[False, True]).iloc[0]
        out.append({"id": sid, "title": title, "x0": float(r["x0"]), "y0": float(r["y0"]), "size_m": SQ,
                    "county": r["county"], "mapped_sites": int(r["sites"]), "missed_sites": int(r["misses"]),
                    "top10_share_of_hillslope": float(r["top10_share"]), "rain_mean_mm": float(r["rain_mean"]),
                    "domain_share": float(r["domain_share"]), "selected_by": by})
    return out


def export_image(url: str, bbox, path) -> None:
    q = urllib.parse.urlencode({"bbox": ",".join(f"{v:.1f}" for v in bbox), "bboxSR": 26917, "imageSR": 26917,
                                "size": f"{IMG_PX},{IMG_PX}", "format": "jpg", "compressionQuality": 80,
                                "interpolation": "RSP_BilinearInterpolation", "f": "image"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(f"{url}/exportImage?{q}", timeout=300) as r:
                data = r.read()
            if data[:2] != b"\xff\xd8":
                raise RuntimeError(f"not a JPEG: {data[:200]!r}")
            path.write_bytes(data)
            return
        except Exception as e:  # noqa: BLE001 - retried, then raised
            if attempt == 4:
                raise
            print("retry", e, flush=True)
            time.sleep(10 * (attempt + 1))


def overlay_png(x0, y0, path) -> None:
    """Top-10 % cells of the final model inside the square as a transparent PNG (one pixel per 5 m cell)."""
    with rasterio.open(SCORES / "rank_final_lr.tif") as s:
        win = from_bounds(x0, y0, x0 + SQ, y0 + SQ, s.transform).round_offsets().round_lengths()
        rk = s.read(1, window=win, boundless=True, fill_value=0)
    on = (rk >= 1) & (rk <= 10)
    rgba = np.zeros((4,) + rk.shape, np.uint8)
    rgba[0][on], rgba[1][on], rgba[2][on], rgba[3][on] = 179, 0, 0, 170
    with MemoryFile() as mf:
        with mf.open(driver="PNG", width=rk.shape[1], height=rk.shape[0], count=4, dtype="uint8") as d:
            d.write(rgba)
        path.write_bytes(mf.read())


def hand_check(s: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(C.SEED + 70)
    sd = s[s["in_domain"]]
    hits = sd[(sd["rank_oof"] >= 1) & (sd["rank_oof"] <= 10)].sample(15, random_state=int(rng.integers(1 << 31)))
    miss = sd[(sd["rank_oof"] == 0) | (sd["rank_oof"] > 30)].sample(10, random_state=int(rng.integers(1 << 31)))
    ds = pd.read_parquet(C.INTERIM / f"labels_{REGION}" / "domain_sample.parquet")
    rk_o = read(SCORES / "rank_oof_lr.tif")
    rk_f = read(SCORES / "rank_final_lr.tif")
    ds["rank_oof"] = rk_o[ds["row"], ds["col"]]
    ds["rank_final"] = rk_f[ds["row"], ds["col"]]
    cand = ds[(ds["positive"] == 0) & (ds["exclusion"] == 0) & (ds["rank_oof"] >= 1) & (ds["rank_oof"] <= 10)]
    flag = cand.sample(15, random_state=int(rng.integers(1 << 31)))
    parts = [("held-out hit (mapped, top 10 %)", hits), ("top 10 %, no mapped initiation", flag),
             ("miss (mapped, outside top 30 %)", miss)]
    rows = []
    for cls, t in parts:
        for _, r in t.iterrows():
            rows.append({"class": cls, "x": r["x"], "y": r["y"], "rank_oof": int(r["rank_oof"]),
                         "rank_final": int(r["rank_final"])})
    out = pd.DataFrame(rows)
    ll = gpd.GeoSeries(gpd.points_from_xy(out["x"], out["y"]), crs=C.CRS).to_crs(4326)
    out.insert(0, "id", [f"HC{i + 1:02d}" for i in range(len(out))])
    out["lon"], out["lat"] = ll.x.round(6), ll.y.round(6)
    out["review_status"] = "not reviewed"
    for c in ("ai_assessment", "ai_note", "human_assessment", "human_note"):
        out[c] = ""
    return out


def run() -> dict:
    df, s = square_table()
    sites = pick_sites(df)
    SITES_DIR.mkdir(parents=True, exist_ok=True)
    pts = s[s["in_domain"]]
    for st in sites:
        x0, y0 = st["x0"], st["y0"]
        bbox = (x0, y0, x0 + SQ, y0 + SQ)
        for epoch, (url, credit) in ORTHO.items():
            export_image(url, bbox, SITES_DIR / f"{st['id']}_{epoch}.jpg")
            st[f"{epoch}_credit"] = credit
        overlay_png(x0, y0, SITES_DIR / f"{st['id']}_top10.png")
        p = pts[(pts["x"] >= x0) & (pts["x"] < x0 + SQ) & (pts["y"] >= y0) & (pts["y"] < y0 + SQ)]
        st["points"] = [{"fx": round((px - x0) / SQ, 4), "fy": round((y0 + SQ - py) / SQ, 4),
                         "held_out_rank": int(r)} for px, py, r in zip(p["x"], p["y"], p["rank_oof"])]
        c = gpd.GeoSeries(gpd.points_from_xy([x0 + SQ / 2], [y0 + SQ / 2]), crs=C.CRS).to_crs(4326)
        st["center_lonlat"] = [round(float(c.x[0]), 5), round(float(c.y[0]), 5)]
        print(st["id"], st["title"], st["mapped_sites"], st["missed_sites"], flush=True)
    meta = {"rule": __doc__.split("Imagery")[0].strip(), "citation": CITATION, "image_px": IMG_PX, "sites": sites}
    (C.VALIDATION / "story_sites.json").write_text(json.dumps(meta, indent=1))
    (SITES_DIR / "sites.json").write_text(json.dumps(meta, indent=1))
    hc = hand_check(s)
    hc.to_csv(C.VALIDATION / "hand_check_sample.csv", index=False)
    return {"sites": [x["id"] for x in sites], "hand_check": len(hc)}


if __name__ == "__main__":
    print(run())
