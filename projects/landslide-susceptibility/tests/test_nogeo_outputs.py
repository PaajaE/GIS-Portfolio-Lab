"""The no-geology decision must follow the pre-registered rule (skipped until `make nogeo` has run)."""

import json

import pytest

from landslide import config as C

P = C.VALIDATION / "nogeo_test.json"
pytestmark = pytest.mark.skipif(not P.exists(), reason="run `make nogeo` first")


def test_decision_follows_rule():
    r = json.loads(P.read_text())
    a = r["aoi_loho"]["delta_no_geology_minus_current"]
    r1 = all(a[k]["ci95"][0] >= -0.01 for k in ("auc_rain_stratified", "auc_within_huc"))
    r2a = r["leave_one_county_out"]["delta_no_geology_minus_current"]["auc_rain_stratified"]["ci95"][0] > 0
    r2b = r["watauga"]["delta_transfer_no_geology_minus_current"]["ci95"][0] > 0
    assert r["decision"] == {"R1_aoi_non_inferior": r1, "R2a_leave_one_county_out": r2a, "R2b_watauga": r2b,
                             "replace_current_model": r1 and r2a and r2b}


def test_current_model_matches_m6_primary():
    r, s = json.loads(P.read_text()), json.loads((C.VALIDATION / "m6_sensitivity.json").read_text())
    assert abs(r["aoi_loho"]["current"]["auc_within_huc"]["value"] - s["primary"]["auc_within_huc"]) < 1e-9
