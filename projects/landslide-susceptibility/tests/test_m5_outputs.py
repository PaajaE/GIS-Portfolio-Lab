"""Stage-boundary assertions on the M5 outputs (skipped until `make advanced` has run)."""

import json

import pandas as pd
import pytest
import rasterio

from landslide import config as C

RES = C.VALIDATION / "m5_advanced.json"
pytestmark = pytest.mark.skipif(not RES.exists(), reason="run `make advanced` first")


@pytest.fixture(scope="module")
def res():
    return json.loads(RES.read_text())


def test_criteria_recomputed_from_numbers(res):
    U, P, K = res["units"], res["pixels"], res["criteria"]
    assert K["C1_units"] == (U["C1_delta_gbm_minus_lr"]["auc_rain_stratified"]["ci95"][0] > 0)
    assert K["C1_pixels"] == (P["C1_delta_gbm_minus_lr"]["auc_rain_stratified"]["ci95"][0] > 0)
    passing = [c for c, d in U["C2_delta_vs_slope"].items()
               if d["auc_rain_stratified"]["ci95"][0] > 0 and d["auc_within_huc"]["value"] > 0]
    assert K["C2_passing"] == passing
    assert K["stop_for_owner_decision"] == (not passing)


def test_candidates_scored_on_the_same_units(res):
    u = pd.read_parquet(C.OUT / "oof_units_m5.parquet")
    assert len(u) == res["units"]["n_units"]
    for c in ("a_unit_lr", "b_unit_gbm", "c_cell_lr_agg", "d_cell_gbm_agg", "slope_p90"):
        assert u[c].notna().all(), c


def test_oof_rasters_on_dem_grid():
    with rasterio.open(C.INTERIM / "dem_5m_aoi.tif") as d:
        grid = (d.crs, d.transform, d.shape)
    for k in ("lr", "gbm"):
        with rasterio.open(C.INTERIM / "scores_aoi" / f"oof_{k}_5m.tif") as s:
            assert (s.crs, s.transform, s.shape) == grid
