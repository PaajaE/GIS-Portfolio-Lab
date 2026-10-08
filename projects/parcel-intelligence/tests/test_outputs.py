"""Stage-boundary assertions on the real pipeline outputs (skipped if not yet built)."""

import json

import numpy as np
import pandas as pd
import pytest

from parcel_intel import config as C

pytestmark = pytest.mark.skipif(not (C.OUT / "parcels.parquet").exists(), reason="run `make all` first")


@pytest.fixture(scope="module")
def parcels():
    import geopandas as gpd

    return gpd.read_parquet(C.OUT / "parcels.parquet")


def test_crs_and_geometry(parcels):
    assert parcels.crs.to_epsg() == 26986
    assert parcels.is_valid.all()
    assert parcels["pid"].is_unique and parcels["loc_id"].is_unique


def test_town_area_plausible(parcels):
    # Amherst land area is ~71 km2 including roads and water; parcels must be below that
    assert 60 < parcels.area.sum() / 1e6 < 72


def test_area_accounting(parcels):
    for k in ("con", "mod", "agg"):
        assert (parcels[f"largest_m2_{k}"] <= parcels[f"cleaned_m2_{k}"] + 1e-6).all()
        assert (parcels[f"cleaned_m2_{k}"] <= parcels[f"net_m2_{k}"] + 1e-6).all()
        # raster parcel area vs vector area: within one cell ring of the boundary
        ring = parcels.length * C.CELL_M
        assert (parcels[f"net_m2_{k}"] <= parcels.area + ring).all()


def test_scenarios_nested(parcels):
    assert (parcels.largest_m2_con <= parcels.largest_m2_mod).all()
    assert (parcels.largest_m2_mod <= parcels.largest_m2_agg).all()


def test_robustness_consistent(parcels):
    r = parcels.robustness
    assert set(r) <= {"robust", "assumption-dependent", "only aggressive", "constrained", "not screened"}
    assert (parcels.loc[r == "robust", "usable_con"]).all()
    assert not parcels.loc[r == "constrained", "usable_agg"].any()
    assert not parcels.loc[r == "not screened", "eligible_agg"].any()


def test_value_ranges(parcels):
    assert parcels.sewer_share.between(0, 1).all()
    assert (parcels.frontage_public_m >= 0).all()
    s = parcels.slope_mean_pct.dropna()
    assert (s >= 0).all() and s.max() < 200


def test_patch_polygons_match_raster(parcels):
    import geopandas as gpd

    patches = gpd.read_parquet(C.OUT / "patches.parquet")
    mod = patches[patches.scenario == "moderate"].set_index("pid")["area_m2"]
    raster = parcels.set_index("pid")["largest_m2_mod"]
    raster = raster[raster > 0]
    assert set(mod.index) == set(raster.index)
    np.testing.assert_allclose(mod.loc[raster.index], raster, rtol=1e-9, atol=1e-6)


def test_validation_kernel_identical():
    v = json.loads((C.OUT / "validation.json").read_text())
    assert v["kernel_full_town_moderate"]["identical_outputs"] is True


def test_no_owner_fields(parcels):
    assert not any(c.upper().startswith("OWN") for c in parcels.columns)
