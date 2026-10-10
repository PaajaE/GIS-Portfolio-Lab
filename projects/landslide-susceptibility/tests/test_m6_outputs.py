"""Stage-boundary assertions on the M6 outputs (skipped until `make m6` has run)."""

import json

import pytest
import rasterio

from landslide import config as C

pytestmark = pytest.mark.skipif(not (C.VALIDATION / "m6_watauga_diagnostics.json").exists(),
                                reason="run `make m6` first")


def j(name):
    return json.loads((C.VALIDATION / name).read_text())


def test_trigger_verdict_follows_the_pre_registered_rule():
    t = j("m6_trigger.json")
    for k, v in t["verdict"].items():
        t1 = t["T1_units_trigger_alone_pooled_auc"][f"delta_{k}_minus_72h"]["ci95"][0] > 0
        t2 = t["T2_cells_within_watershed_auc"][f"delta_{k}_minus_72h"]["ci95"][0] > 0
        assert v == {"T1": t1, "T2": t2, "meaningful_benefit": t1 and t2}


def test_sensitivity_primary_matches_m5_cells():
    s, m5 = j("m6_sensitivity.json"), j("m5_advanced.json")
    # same design; the 1:10 negative draws differ (M5 also drew permutations from the same generator)
    assert abs(s["primary"]["auc_within_huc"] - m5["pixels"]["scores"]["lr"]["auc_within_huc"]["value"]) < 0.003


def test_uncertainty_layers_and_shares():
    u = j("m6_uncertainty.json")
    for k, v in u["ensemble"].items():
        if k.startswith("final_"):
            assert 0 <= v <= 1
    assert 0 <= u["area_of_applicability"]["share_outside_aoa"] <= 1
    with rasterio.open(C.INTERIM / "scores_aoi" / "ens_rank_p10.tif") as a, \
            rasterio.open(C.INTERIM / "scores_aoi" / "ens_rank_p90.tif") as b:
        x, y = a.read(1, window=((7000, 7200), (7000, 7200))), b.read(1, window=((7000, 7200), (7000, 7200)))
    assert ((x == 0) == (y == 0)).all() and (x <= y).all()  # p10 class never worse than p90 class


def test_watauga_counts_and_intervals():
    w = j("m6_watauga.json")
    assert w["helene_test_outlines_with_cells"] <= w["helene_test_outlines"]
    for k in ("transfer_aoi_model", "slope_alone", "temporal_1940_model", "recurrence_baseline"):
        lo, hi = w[k]["ci95"]
        assert lo <= w[k]["auc"] <= hi
