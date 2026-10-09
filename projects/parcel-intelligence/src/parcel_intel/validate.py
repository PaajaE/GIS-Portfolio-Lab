"""Validation of structural correctness plus comparisons with independent information.

1. kernel: Rust == scipy reference on the full town (moderate scenario), exact.
2. rasterization: per-parcel constraint area, raster cell count vs GEOS overlay.
3. assessor comparison: does the screen separate parcels the assessor classes as
   developable vs undevelopable vacant land? (a different construct: comparison only)
4. built-parcel plausibility: where do post-2000 building footprints sit relative
   to the constraint mask?
5. hand-check figures for a stratified sample of parcels.

Writes data/out/validation.json and validation/figures/*.png.
"""

from __future__ import annotations

import json
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from parcel_kernels import screen_patches
from scipy.stats import mannwhitneyu

from . import analyze as A
from . import config as C
from .patches import screen_patches_reference

FIG = C.ROOT / "validation" / "figures"
# Parcels discussed in METHOD.md (hand checks); always rendered in addition to the sample.
DOCUMENTED = (1090, 3424, 4907, 1795)


def check_kernel(bits) -> dict:
    feasible = (A.pidx() > 0) & (bits == 0)
    min_cells = int(np.ceil(C.MIN_PATCH_M2 / A.grid()["cell_m"] ** 2))
    t = time.perf_counter()
    ref = screen_patches_reference(A.pidx(), feasible, A.n_parcels(), C.OPEN_SIZE_CELLS, C.CONNECTIVITY, min_cells)
    t_ref = time.perf_counter() - t
    t = time.perf_counter()
    got = screen_patches(A.pidx(), feasible, A.n_parcels(), C.OPEN_SIZE_CELLS, C.CONNECTIVITY, min_cells)
    t_rust = time.perf_counter() - t
    equal = all(np.array_equal(r, g) for r, g in zip(ref, got))
    return {"identical_outputs": bool(equal), "reference_s": round(t_ref, 2), "rust_s": round(t_rust, 3)}


def check_rasterization(bits) -> dict:
    """Compare raster area per parcel with exact GEOS overlay for three categories."""
    p = A.parcels()[["pid", "geometry"]]
    mod = C.SCENARIOS["moderate"]
    layers = {
        "flood": A.vec("flood").loc[lambda f: f["SFHA_TF"] == "T"].geometry,
        "wetland_water": pd.concat(
            [
                A.vec("wetlands").geometry.buffer(mod["wetland_buffer_m"]),
                A.vec("waterbodies").geometry.buffer(mod["wetland_buffer_m"]),
                A.vec("streams").loc[lambda s: s["ARC_CODE"] == 4].geometry.buffer(mod["perennial_stream_buffer_m"]),
                A.vec("streams").loc[lambda s: s["ARC_CODE"] != 4].geometry.buffer(mod["other_stream_buffer_m"]),
            ]
        ),
        "protected": A.vec("openspace").loc[lambda o: o["LEV_PROT"] == "P"].geometry,
    }
    cell_a = A.grid()["cell_m"] ** 2
    out = {}
    for cat, geoms in layers.items():
        u = gpd.GeoDataFrame(geometry=[geoms.union_all()], crs=p.crs)
        inter = gpd.overlay(p, u, how="intersection", keep_geom_type=True)
        vec_area = inter.groupby("pid").geometry.apply(lambda g: g.area.sum()).reindex(p["pid"], fill_value=0.0)
        ras_area = A.per_parcel_sum((A.pidx() > 0) & ((bits & A.BITS[cat]) != 0))[1:] * cell_a
        err = ras_area - vec_area.to_numpy()
        touched = (vec_area.to_numpy() > 0) | (ras_area > 0)
        out[cat] = {
            "parcels_affected": int(touched.sum()),
            "total_vector_ha": round(float(vec_area.sum()) / 1e4, 2),
            "total_raster_ha": round(float(ras_area.sum()) / 1e4, 2),
            "abs_error_m2_median": round(float(np.median(np.abs(err[touched]))), 1),
            "abs_error_m2_p95": round(float(np.percentile(np.abs(err[touched]), 95)), 1),
            "abs_error_share_of_parcel_p95": round(
                float(np.percentile(np.abs(err[touched]) / A.parcels()["area_m2"].to_numpy()[touched], 95)), 4
            ),
        }
    return out


def auc(pos, neg) -> float:
    """AUC = P(score_pos > score_neg) with ties counted half (Mann-Whitney U / n1 n2)."""
    u = mannwhitneyu(pos, neg, alternative="two-sided").statistic
    return float(u / (len(pos) * len(neg)))


def check_assessor(m: pd.DataFrame) -> dict:
    p = A.parcels().set_index("pid")
    code = p["use_code"].fillna("").str[:3]
    # "developable" includes the assessor's "potentially developable" codes (131, 441)
    groups = {"developable": code.isin(["130", "131", "390", "441"]), "undevelopable": code.isin(["132", "392"])}
    out = {
        "n": {k: int(v.sum()) for k, v in groups.items()},
        "n_potentially_developable": int(code.isin(["131", "441"]).sum()),
        "group_labels": {"developable": "developable or potentially developable (130, 131, 390, 441)", "undevelopable": "undevelopable (132, 392)"},
        "auc": {},
        "median_m2": {},
    }
    pos, neg = groups["developable"], groups["undevelopable"]
    for k in ("con", "mod", "agg"):
        for metric in ("naive", "net", "largest"):
            col = f"{metric}_m2_{k}"
            out["auc"][f"{metric}_{k}"] = round(auc(m.loc[pos, col], m.loc[neg, col]), 3)
        out["median_m2"][f"largest_{k}"] = {
            "developable": float(m.loc[pos, f"largest_m2_{k}"].median()),
            "undevelopable": float(m.loc[neg, f"largest_m2_{k}"].median()),
        }
        out[f"qualifying_share_{k}"] = {
            "developable": round(float(m.loc[pos, f"qualifying_{k}"].mean()), 3),
            "undevelopable": round(float(m.loc[neg, f"qualifying_{k}"].mean()), 3),
        }
    # paired bootstrap (resample parcels within each class) for AUC differences
    rng = np.random.default_rng(20261008)
    ip, ineg = np.flatnonzero(pos.to_numpy()), np.flatnonzero(neg.to_numpy())
    cols = {k: m[k].to_numpy() for k in ("largest_m2_mod", "net_m2_mod", "naive_m2_mod")}
    diffs = {"largest_minus_net_mod": [], "largest_minus_naive_mod": []}
    for _ in range(2000):
        bp, bn = rng.choice(ip, len(ip)), rng.choice(ineg, len(ineg))
        a = {k: auc(v[bp], v[bn]) for k, v in cols.items()}
        diffs["largest_minus_net_mod"].append(a["largest_m2_mod"] - a["net_m2_mod"])
        diffs["largest_minus_naive_mod"].append(a["largest_m2_mod"] - a["naive_m2_mod"])
    out["auc_difference_95ci"] = {k: [round(float(q), 3) for q in np.percentile(v, [2.5, 97.5])] for k, v in diffs.items()}
    # rank-based AUC is invariant to monotone transforms; also report parcel-size-only AUC
    out["auc"]["parcel_area_only"] = round(auc(p.loc[pos, "area_m2"], p.loc[neg, "area_m2"]), 3)
    return out


def check_buildings(bits_mod) -> dict:
    """Share of footprint area of buildings on parcels built 2000+ that falls in each
    site constraint (moderate). Bare-earth lidar is interpolated under buildings and
    terrain is post-construction, so slope here is biased toward 'flat'."""
    p = A.parcels().set_index("pid")
    new = p.index[(p["year_built"] >= 2000) & ~p["is_condo"]].to_numpy()
    sel = np.isin(A.pidx(), new) & A.building_mask()
    n = int(sel.sum())
    out = {"parcels": int(len(new)), "footprint_cells": n}
    for cat in ("flood", "wetland_water", "protected", "steep_slope"):
        out[f"share_in_{cat}"] = round(float(((bits_mod[sel] & A.BITS[cat]) != 0).mean()), 4)
    hab = A.habitat_mask()
    out["share_in_priority_habitat"] = round(float(hab[sel].mean()), 4)
    return out


def sample_parcels(m: pd.DataFrame, seed: int = 20261008) -> list[int]:
    """One vacant and one built parcel (> 4,000 m2) per screened robustness class."""
    rng = np.random.default_rng(seed)
    picks = []
    big = A.parcels().set_index("pid")["area_m2"] > 4000
    for cls in ("robust", "assumption-dependent", "only aggressive", "constrained"):
        for vac in (True, False):
            ids = m.index[(m["robustness"] == cls) & (m["vacant"] == vac) & big]
            if len(ids):
                picks.append(int(rng.choice(ids)))
    # plus the screened parcels where naive vs patch disagree most (largest overstatement)
    over = (m["naive_m2_mod"] - m["largest_m2_mod"])[m["eligible_mod"]].sort_values(ascending=False)
    picks += [int(i) for i in over.index[:2] if i not in picks]
    picks += [p for p in DOCUMENTED if p not in picks]
    return picks


def figures(picks: list[int], m: pd.DataFrame) -> list[dict]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    FIG.mkdir(parents=True, exist_ok=True)
    for stale in FIG.glob("parcel_*.png"):
        stale.unlink()
    g = A.grid()
    with rasterio.open(C.INTERIM / "dem_2m.tif") as src:
        dem = src.read(1)
    with rasterio.open(C.OUT / "constraints_moderate.tif") as src:
        bits = src.read(1)
    masks = {}
    for s in C.SCENARIO_ORDER:
        with rasterio.open(C.OUT / f"patches_{s}.tif") as src:
            masks[s] = src.read(1)
    p = A.parcels().set_index("pid")
    notes = []
    order = ["flood", "wetland_water", "protected", "steep_slope", "existing_development", "yard_setback"]
    colors = ["#2b6cb0", "#38a1a1", "#5a8f29", "#b7791f", "#444444", "#cccccc"]
    for pid in picks:
        geom = p.loc[pid, "geometry"]
        x0, y0, x1, y1 = geom.buffer(30).bounds
        c0, c1 = int((x0 - g["xmin"]) / g["cell_m"]), int((x1 - g["xmin"]) / g["cell_m"]) + 1
        r0, r1 = int((g["ymax"] - y1) / g["cell_m"]), int((g["ymax"] - y0) / g["cell_m"]) + 1
        ext = (g["xmin"] + c0 * g["cell_m"], g["xmin"] + c1 * g["cell_m"], g["ymax"] - r1 * g["cell_m"], g["ymax"] - r0 * g["cell_m"])
        z = dem[r0:r1, c0:c1].astype(float)
        gy, gx = np.gradient(z, g["cell_m"])
        hs = np.clip(0.6 - 0.4 * (gx - gy) / np.hypot(1, np.hypot(gx, gy)), 0, 1)
        b = bits[r0:r1, c0:c1]
        inp = A.pidx()[r0:r1, c0:c1] == pid
        cat = np.zeros(b.shape, dtype=int)
        for i, name in reversed(list(enumerate(order, start=1))):
            cat[(b & A.BITS[name]) != 0] = i
        cat[~inp] = 0
        fig, axes = plt.subplots(1, 2, figsize=(11, 6.0), constrained_layout=True)
        for ax in axes:
            ax.imshow(hs, cmap="gray", extent=ext, vmin=0, vmax=1)
            gpd.GeoSeries([geom]).boundary.plot(ax=ax, color="black", linewidth=1.2)
            ax.set_xticks([])
            ax.set_yticks([])
        axes[0].imshow(np.ma.masked_equal(cat, 0), cmap=ListedColormap(colors), vmin=1, vmax=len(order), extent=ext, alpha=0.75, interpolation="nearest")
        axes[0].set_title("hard constraints, moderate scenario (black line = parcel)", fontsize=8)
        lay = np.zeros(b.shape, dtype=int)
        for i, s in enumerate(reversed(C.SCENARIO_ORDER), start=1):
            lay[(masks[s][r0:r1, c0:c1] > 0) & inp] = i
        axes[1].imshow(np.ma.masked_equal(lay, 0), cmap=ListedColormap(["#fde68a", "#f59e0b", "#b45309"]), vmin=1, vmax=3, extent=ext, alpha=0.8, interpolation="nearest")
        axes[1].set_title("feasible after cleanup, by scenario (nested)", fontsize=8)
        from matplotlib.patches import Patch

        axes[0].legend(
            handles=[Patch(color=c, alpha=0.75, label=n.replace("_", " ")) for n, c in zip(order, colors)],
            loc="upper left", bbox_to_anchor=(0, -0.01), ncol=3, fontsize=7, frameon=False,
        )
        axes[1].legend(
            handles=[Patch(color=c, alpha=0.8, label=f"{s} (largest patch + other feasible)") for s, c in zip(("aggressive", "moderate", "conservative"), ("#fde68a", "#f59e0b", "#b45309"))],
            loc="upper left", bbox_to_anchor=(0, -0.01), ncol=1, fontsize=7, frameon=False,
        )
        r = m.loc[pid]
        fig.suptitle(
            f"pid {pid} | {p.loc[pid, 'site_addr']} | {p.loc[pid, 'use_desc']} | {p.loc[pid, 'area_m2']:.0f} m2 | "
            f"largest con/mod/agg {r['largest_m2_con']:.0f}/{r['largest_m2_mod']:.0f}/{r['largest_m2_agg']:.0f} m2 | "
            f"naive mod {r['naive_m2_mod']:.0f} | {r['robustness']} | {'vacant' if r['vacant'] else 'built'}",
            fontsize=7,
        )
        path = FIG / f"parcel_{pid}.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
        notes.append({"pid": int(pid), "figure": str(path.relative_to(C.ROOT)), "robustness": r["robustness"], "vacant": bool(r["vacant"])})
    return notes


def main() -> None:
    m = pd.read_parquet(C.OUT / "parcel_metrics.parquet").set_index("pid")
    with rasterio.open(C.OUT / "constraints_moderate.tif") as src:
        bits = src.read(1)
    res = {
        "kernel_full_town_moderate": check_kernel(bits),
        "rasterization_vs_geos": check_rasterization(bits),
        "assessor_comparison": check_assessor(m),
        "post2000_buildings": check_buildings(bits),
    }
    picks = sample_parcels(m)
    res["hand_check_sample"] = figures(picks, m)
    (C.OUT / "validation.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
