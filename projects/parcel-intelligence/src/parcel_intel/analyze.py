"""Scenario screening: hard-constraint mask -> morphological cleanup -> per-parcel
connected components -> parcel metrics, plus baselines, leave-one-out constraint
relief and one-at-a-time sensitivity.

Outputs (data/out/):
  parcel_metrics.parquet     one row per parcel (no geometry), all scenarios
  patches_<scenario>.tif     0 / 1 feasible after cleanup / 2 largest patch
  constraints_<scenario>.tif uint16 bit mask of active hard constraints
  sensitivity.json, summary.json
"""

from __future__ import annotations

import json
import time
from functools import cache

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from parcel_kernels import screen_patches
from rasterio.features import rasterize

from . import config as C
from .prepare import NODATA, grid_transform, write_raster

# Constraint bits (one per category; categories are reported separately)
BITS = {
    "flood": 1,
    "wetland_water": 2,
    "protected": 4,
    "priority_habitat": 8,
    "steep_slope": 16,
    "yard_setback": 32,
    "existing_development": 64,
    "no_data": 128,
}
CHAPTER_LAND = ("6", "7", "8")
NOT_SITE_RELIEF = ("relief_yard_setback_m2", "relief_existing_development_m2")  # Chapter 61 / 61A / 61B use classes (first digit)


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------
@cache
def grid() -> dict:
    return json.loads((C.INTERIM / "grid.json").read_text())


@cache
def vec(name: str) -> gpd.GeoDataFrame:
    return gpd.read_parquet(C.INTERIM / f"{name}.parquet")


@cache
def parcels() -> gpd.GeoDataFrame:
    return vec("parcels")


def read_raster(name: str) -> np.ndarray:
    with rasterio.open(C.INTERIM / name) as src:
        return src.read(1)


@cache
def pidx() -> np.ndarray:
    return read_raster("parcel_idx.tif")


@cache
def slope() -> np.ndarray:
    return read_raster("slope_pct.tif")


def burn(geoms) -> np.ndarray:
    g = grid()
    geoms = [x for x in geoms if x is not None and not x.is_empty]
    if not geoms:
        return np.zeros((g["height"], g["width"]), dtype=bool)
    return rasterize(
        geoms, out_shape=(g["height"], g["width"]), transform=grid_transform(g), fill=0, dtype="uint8"
    ).astype(bool)


@cache
def flood_mask(definition: str) -> np.ndarray:
    f = vec("flood")
    sfha = f["SFHA_TF"] == "T"
    if definition == "floodway":
        sel = f["ZONE_SUBTY"] == "FLOODWAY"
    elif definition == "sfha":
        sel = sfha
    elif definition == "sfha_and_0.2pct":
        sel = sfha | f["ZONE_SUBTY"].fillna("").str.startswith("0.2 PCT")
    else:
        raise ValueError(definition)
    return burn(f.geometry[sel])


@cache
def water_mask(wetland_m: float, perennial_m: float, other_m: float) -> np.ndarray:
    """Wetlands and water bodies with their buffer, plus stream buffers (GEOS buffers)."""
    w = vec("wetlands").geometry.buffer(wetland_m)
    wb = vec("waterbodies").geometry.buffer(wetland_m)
    s = vec("streams")
    per = s.geometry[s["ARC_CODE"] == 4].buffer(perennial_m)
    oth = s.geometry[s["ARC_CODE"] != 4].buffer(other_m)
    return burn(pd.concat([w, wb, per, oth]))


@cache
def protected_mask(levels: tuple[str, ...]) -> np.ndarray:
    o = vec("openspace")
    return burn(o.geometry[o["LEV_PROT"].isin(levels)])


@cache
def habitat_mask() -> np.ndarray:
    return burn(vec("prihab").geometry)


@cache
def building_mask() -> np.ndarray:
    return burn(vec("buildings").geometry)


# Assumed paved half-width (m) by MassDOT road class; SURFACE_WD was not harvested.
# 2 = multi-lane highway, 3/4 = numbered route / arterial-collector, 5/6 = local road.
ROAD_HALF_WIDTH_M = {1: 12.0, 2: 9.0, 3: 6.0, 4: 6.0, 5: 4.0, 6: 4.0, 7: 4.0}


@cache
def development_mask() -> np.ndarray:
    """Existing buildings plus road surface (centreline buffered by an assumed half-width).
    Matters for private ways and driveways mapped inside parcels."""
    r = vec("roads")
    half = r["CLASS"].map(ROAD_HALF_WIDTH_M).fillna(4.0)
    return building_mask() | burn(r.geometry.buffer(half, cap_style="flat"))


@cache
def yard_mask(yard_m: float) -> np.ndarray:
    """Parcel cells closer than yard_m to the parcel boundary (uniform inner setback)."""
    p = parcels()
    inner = p.geometry.buffer(-yard_m)
    keep = ~inner.is_empty
    core = rasterize(
        zip(inner[keep], p["pid"][keep]),
        out_shape=pidx().shape,
        transform=grid_transform(grid()),
        fill=0,
        dtype="int32",
    )
    return (pidx() > 0) & (core != pidx())


def constraint_bits(params: dict) -> np.ndarray:
    s = slope()
    bits = np.zeros(s.shape, dtype=np.uint16)
    bits |= flood_mask(params["flood"]) * np.uint16(BITS["flood"])
    bits |= water_mask(
        params["wetland_buffer_m"], params["perennial_stream_buffer_m"], params["other_stream_buffer_m"]
    ) * np.uint16(BITS["wetland_water"])
    bits |= protected_mask(tuple(params["protection_levels"])) * np.uint16(BITS["protected"])
    if params["exclude_priority_habitat"]:
        bits |= habitat_mask() * np.uint16(BITS["priority_habitat"])
    valid = s != NODATA
    bits |= (valid & (s >= params["slope_pct"])) * np.uint16(BITS["steep_slope"])
    bits |= yard_mask(params["yard_m"]) * np.uint16(BITS["yard_setback"])
    bits |= development_mask() * np.uint16(BITS["existing_development"])
    bits |= (~valid) * np.uint16(BITS["no_data"])
    return bits


def eligible(params: dict) -> np.ndarray:
    """Parcel-level land-use eligibility (index 0..N). Tax-exempt (use class 9) is out of
    scope in every scenario; Chapter 61/61A/61B land only in scenarios that exclude it."""
    uc = parcels()["use_code"].fillna("").str[:1]
    ok = (uc != "9") & ~parcels()["any_exempt"]
    if params["exclude_chapter_land"]:
        ok &= ~uc.isin(CHAPTER_LAND)
    return np.concatenate([[False], ok.to_numpy()])


# ---------------------------------------------------------------------------
# kernels
# ---------------------------------------------------------------------------
def n_parcels() -> int:
    return len(parcels())


def patches(bits: np.ndarray, ignore: int = 0, open_size: int = C.OPEN_SIZE_CELLS):
    feasible = (pidx() > 0) & ((bits & ~np.uint16(ignore)) == 0)
    min_cells = int(np.ceil(C.MIN_PATCH_M2 / grid()["cell_m"] ** 2))
    return screen_patches(pidx(), feasible, n_parcels(), open_size, C.CONNECTIVITY, min_cells)


def per_parcel_sum(mask: np.ndarray) -> np.ndarray:
    p = pidx()
    return np.bincount(p[mask], minlength=n_parcels() + 1)


def baseline_naive(params: dict, bits: np.ndarray) -> np.ndarray:
    """B1: whole parcel passes if parcel-mean slope < threshold and its representative
    point is outside flood / wetland-water / protected areas. Returns area (m2)."""
    p = pidx()
    s = slope()
    inside = (p > 0) & (s != NODATA)
    sums = np.bincount(p[inside], weights=s[inside], minlength=n_parcels() + 1)
    cnt = np.bincount(p[inside], minlength=n_parcels() + 1)
    mean_slope = np.divide(sums, cnt, out=np.full(sums.shape, np.inf), where=cnt > 0)
    rp = parcels().geometry.representative_point()
    g = grid()
    col = ((rp.x - g["xmin"]) / g["cell_m"]).astype(int).to_numpy()
    row = ((g["ymax"] - rp.y) / g["cell_m"]).astype(int).to_numpy()
    point_bits = bits[row, col]
    blocked = (point_bits & (BITS["flood"] | BITS["wetland_water"] | BITS["protected"])) != 0
    passes = (mean_slope[1:] < params["slope_pct"]) & ~blocked
    return np.concatenate([[0.0], np.where(passes, parcels()["area_m2"].to_numpy(), 0.0)])


# ---------------------------------------------------------------------------
# scenario run
# ---------------------------------------------------------------------------
def run_scenario(name: str, params: dict, write: bool = True) -> pd.DataFrame:
    cell_a = grid()["cell_m"] ** 2
    bits = constraint_bits(params)
    inside = pidx() > 0
    total = per_parcel_sum(inside)
    free = per_parcel_sum(inside & (bits == 0))
    fc, lc, npch, mask = patches(bits)
    elig = eligible(params)

    df = pd.DataFrame(index=pd.RangeIndex(1, n_parcels() + 1, name="pid"))
    k = f"_{name[:3]}"
    df["eligible" + k] = elig[1:]
    df["naive_m2" + k] = baseline_naive(params, bits)[1:]
    df["net_m2" + k] = free[1:] * cell_a
    df["cleaned_m2" + k] = fc[1:] * cell_a
    df["largest_m2" + k] = lc[1:] * cell_a
    df["n_patches" + k] = npch[1:]
    df["qualifying" + k] = elig[1:] & (lc[1:] * cell_a >= C.MIN_PATCH_M2)
    for cat, b in BITS.items():
        df[f"c_{cat}_m2{k}"] = per_parcel_sum(inside & ((bits & b) != 0))[1:] * cell_a
    df["cells_in_raster"] = total[1:]

    if write:
        C.OUT.mkdir(parents=True, exist_ok=True)
        write_raster(C.OUT / f"patches_{name}.tif", mask, grid(), None)
        write_raster(C.OUT / f"constraints_{name}.tif", bits, grid(), None)
    return df, bits


def leave_one_out(params: dict, bits: np.ndarray, largest: np.ndarray) -> pd.DataFrame:
    """Relief = gain in largest patch (m2) if one constraint category is dropped."""
    cell_a = grid()["cell_m"] ** 2
    out = {}
    for cat, b in BITS.items():
        if cat == "no_data":
            continue
        _, lc, _, _ = patches(bits, ignore=b)
        out[f"relief_{cat}_m2"] = lc[1:] * cell_a - largest
    return pd.DataFrame(out, index=pd.RangeIndex(1, n_parcels() + 1, name="pid"))


def slope_stats() -> pd.DataFrame:
    p, s = pidx(), slope()
    m = (p > 0) & (s != NODATA)
    d = pd.DataFrame({"pid": p[m], "s": s[m]})
    g = d.groupby("pid")["s"]
    return pd.DataFrame({"slope_mean_pct": g.mean(), "slope_p90_pct": g.quantile(0.9), "slope_max_pct": g.max()})


@cache
def vacancy() -> pd.DataFrame:
    """Vacant = no structure on the parcel. A parcel has a structure if at least half of some
    mapped building footprint lies inside it (so a neighbour's footprint spilling over an
    assessor line does not count) or the assessor records a year built (catches buildings
    newer than the mostly-2011 footprints). The assessor vacant-land class is reported but
    does not override a structure; such conflicts are flagged for review."""
    p = parcels()[["pid", "geometry", "use_code", "year_built"]]
    b = vec("buildings")[["geometry"]].reset_index(drop=True)
    b["b_area"] = b.area
    ov = gpd.overlay(b, p[["pid", "geometry"]], how="intersection", keep_geom_type=True)
    own = ov.loc[ov.area >= 0.5 * ov["b_area"], "pid"].value_counts()
    own_footprint = own.reindex(p["pid"], fill_value=0).to_numpy() > 0
    assessor_building = (p["year_built"].fillna(0) > 0).to_numpy()
    code = p["use_code"].fillna("").str[:2].isin(C.VACANT_LAND_CLASSES).to_numpy()
    has_structure = own_footprint | assessor_building
    return pd.DataFrame(
        {
            "has_building": own_footprint,
            "assessor_building": assessor_building,
            "vacant_land_code": code,
            "vacant": ~has_structure,
            "vacancy_conflict": code & has_structure,
        },
        index=pd.RangeIndex(1, n_parcels() + 1, name="pid"),
    )


def sensitivity() -> list[dict]:
    """One-at-a-time: from the moderate scenario, swap one parameter group to its
    conservative / aggressive value. Morphology size varied separately."""
    base = C.SCENARIOS["moderate"]
    groups = {
        "slope threshold": ["slope_pct"],
        "wetland & stream setbacks": ["wetland_buffer_m", "perennial_stream_buffer_m", "other_stream_buffer_m"],
        "flood definition": ["flood"],
        "open-space protection levels": ["protection_levels"],
        "priority habitat": ["exclude_priority_habitat"],
        "yard setback": ["yard_m"],
        "chapter 61 land": ["exclude_chapter_land"],
    }
    cell_a = grid()["cell_m"] ** 2

    def town_stats(params, open_size=C.OPEN_SIZE_CELLS):
        bits = constraint_bits(params)
        _, lc, _, _ = patches(bits, open_size=open_size)
        elig = eligible(params)[1:]
        area = lc[1:] * cell_a
        vac = vacancy()["vacant"].to_numpy()
        q = elig & (area >= C.MIN_PATCH_M2)
        return {
            "qualifying_vacant": int((q & vac).sum()),
            "qualifying_parcels": int(q.sum()),
            "largest_patch_vacant_ha": round(float(area[elig & vac].sum()) / 1e4, 1),
            "largest_patch_total_ha": round(float(area[elig].sum()) / 1e4, 1),
        }

    rows = [{"group": "moderate (reference)", "variant": "moderate", **town_stats(base)}]
    for gname, keys in groups.items():
        for variant in ("conservative", "aggressive"):
            p = dict(base)
            for key in keys:
                p[key] = C.SCENARIOS[variant][key]
            if all(p[key] == base[key] for key in keys):
                continue
            rows.append({"group": gname, "variant": variant, **town_stats(p)})
    for size, variant in ((3, "6 m square"), (7, "14 m square")):
        rows.append({"group": "minimum patch width (opening)", "variant": variant, **town_stats(base, size)})
    return rows


def robustness(df: pd.DataFrame) -> pd.Series:
    con, mod, agg = df["qualifying_con"], df["qualifying_mod"], df["qualifying_agg"]
    cls = np.select(
        [~df["eligible_agg"], con & mod & agg, mod & agg, agg],
        ["not screened", "robust", "assumption-dependent", "only aggressive"],
        default="constrained",
    )
    return pd.Series(cls, index=df.index)


def main() -> None:
    t0 = time.perf_counter()
    frames, bits_by = [], {}
    for name in C.SCENARIO_ORDER:
        df, bits = run_scenario(name, C.SCENARIOS[name])
        frames.append(df.drop(columns="cells_in_raster") if frames else df)
        bits_by[name] = bits
        print(f"{name:12s} qualifying parcels {int(df[f'qualifying_{name[:3]}'].sum()):5d}")
    m = pd.concat(frames, axis=1)

    # nesting check: conservative <= moderate <= aggressive (monotone constraints + opening)
    for a, b in (("con", "mod"), ("mod", "agg")):
        bad = (m[f"largest_m2_{a}"] > m[f"largest_m2_{b}"] + 1e-9).sum()
        if bad:
            raise AssertionError(f"{bad} parcels violate scenario nesting {a} <= {b}")

    loo = leave_one_out(C.SCENARIOS["moderate"], bits_by["moderate"], m["largest_m2_mod"].to_numpy())
    m = m.join(loo)
    # The uniform yard setback always "binds" (dropping it always adds a ring of cells) and
    # removing existing development means demolition, so neither is a site constraint here;
    # the binding constraint is chosen among site-specific categories only (both reported).
    relief_cols = [c for c in loo.columns if c not in NOT_SITE_RELIEF]
    best = loo[relief_cols].to_numpy().argmax(axis=1)
    has = loo[relief_cols].to_numpy().max(axis=1) > 0
    names = np.array([c.removeprefix("relief_").removesuffix("_m2") for c in relief_cols])
    m["binding_constraint_mod"] = np.where(has, names[best], "none")
    area_cols = [f"c_{c}_m2_mod" for c in BITS if c != "no_data"]
    dom = m[area_cols].to_numpy()
    m["dominant_constraint_mod"] = np.where(
        dom.max(axis=1) > 0, np.array([c.removeprefix("c_").removesuffix("_m2_mod") for c in area_cols])[dom.argmax(axis=1)], "none"
    )
    m["robustness"] = robustness(m)
    m = m.join(vacancy()).join(slope_stats())
    m.reset_index().to_parquet(C.OUT / "parcel_metrics.parquet")

    sens = sensitivity()
    (C.OUT / "sensitivity.json").write_text(json.dumps(sens, indent=2))

    cell_a = grid()["cell_m"] ** 2
    summary = {"runtime_s": round(time.perf_counter() - t0, 1), "parcels": n_parcels(), "scenarios": {}}
    for name in C.SCENARIO_ORDER:
        k = name[:3]
        e = m[f"eligible_{k}"]
        q = m[f"qualifying_{k}"]
        summary["scenarios"][name] = {
            "eligible_parcels": int(e.sum()),
            "eligible_vacant": int((e & m["vacant"]).sum()),
            "eligible_built": int((e & ~m["vacant"]).sum()),
            "qualifying_parcels": int(q.sum()),
            "qualifying_vacant": int((q & m["vacant"]).sum()),
            "qualifying_built": int((q & ~m["vacant"]).sum()),
            "largest_patch_vacant_ha": round(float(m.loc[e & m["vacant"], f"largest_m2_{k}"].sum()) / 1e4, 1),
            "naive_pass_parcels": int((e & (m[f"naive_m2_{k}"] > 0)).sum()),
            "naive_area_ha": round(float(m.loc[e, f"naive_m2_{k}"].sum()) / 1e4, 1),
            "net_area_ha": round(float(m.loc[e, f"net_m2_{k}"].sum()) / 1e4, 1),
            "cleaned_area_ha": round(float(m.loc[e, f"cleaned_m2_{k}"].sum()) / 1e4, 1),
            "largest_patch_area_ha": round(float(m.loc[e, f"largest_m2_{k}"].sum()) / 1e4, 1),
            "constraint_area_ha": {
                c: round(float((per_parcel_sum((pidx() > 0) & ((bits_by[name] & b) != 0))[1:][e.to_numpy()]).sum() * cell_a) / 1e4, 1)
                for c, b in BITS.items()
            },
        }
    summary["robustness"] = m["robustness"].value_counts().to_dict()
    summary["robustness_vacant"] = m.loc[m["vacant"], "robustness"].value_counts().to_dict()
    summary["robustness_built"] = m.loc[~m["vacant"], "robustness"].value_counts().to_dict()
    summary["vacant_parcels"] = int(m["vacant"].sum())
    summary["vacant_definition"] = (
        "no structure: no mapped building footprint at least half inside the parcel and no assessor year built"
    )
    summary["vacancy_conflicts"] = int(m["vacancy_conflict"].sum())
    em = m["eligible_mod"]
    summary["binding_constraint_mod"] = m.loc[em, "binding_constraint_mod"].value_counts().to_dict()
    summary["binding_constraint_mod_vacant"] = m.loc[em & m["vacant"], "binding_constraint_mod"].value_counts().to_dict()
    (C.OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print(pd.DataFrame(sens).to_string(index=False))


if __name__ == "__main__":
    main()
