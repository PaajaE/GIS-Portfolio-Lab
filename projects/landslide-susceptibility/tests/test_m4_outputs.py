"""Stage-boundary assertions on the M4 outputs (skipped until `make baseline` has run)."""

import json

import numpy as np
import pandas as pd
import pytest

from landslide import config as C
from landslide.baseline import GATE_G1, GATE_G2, REPLICATE_MIN_POS
from landslide.labels import REGION

RES = C.VALIDATION / "m4_baseline.json"
pytestmark = pytest.mark.skipif(not RES.exists(), reason="run `make baseline` first")


@pytest.fixture(scope="module")
def res():
    return json.loads(RES.read_text())


@pytest.fixture(scope="module")
def oof():
    return pd.read_parquet(C.OUT / "oof_units.parquet")


def test_every_unit_scored_out_of_fold_once(oof):
    units = pd.read_parquet(C.OUT / "units_0.1.parquet")
    assert len(oof) == int(units["in_model_domain"].sum())
    assert oof["unit"].is_unique
    assert oof[["oof_ref", "oof_ref_variant", "oof_p_actual", "final_ref"]].notna().all().all()
    assert oof["oof_p_actual"].between(0, 1).all()


def test_labels_trace_to_unit_table(res, oof):
    p = res["units"]["primary"]
    assert p["positive_units"] == int(oof["label"].sum())
    assert p["sources"] == int(oof["n_sources"].sum())
    # the variant rule only adds sources (runoff-modified natural slopes)
    assert (oof["label_variant"] >= oof["label"]).all()


def test_folds_table_matches_results(res):
    f = pd.read_csv(C.VALIDATION / "folds_huc12.csv", dtype={"huc12": str})
    assert f["huc12"].is_unique and f["huc12"].str.len().eq(12).all()
    assert f["units"].sum() == res["units"]["n_units"]
    assert f["positive_units"].sum() == res["units"]["primary"]["positive_units"]
    assert f["replicate"].sum() == res["units"]["primary"]["replicates"]["n"]
    assert (f.loc[f["replicate"], "positive_units"] >= REPLICATE_MIN_POS).all()


def test_gates_recomputed_from_numbers(res):
    s = res["units"]["primary"]["scores"]["lr_at_reference_rain"]["auc_rain_stratified"]
    g1 = s["value"] >= GATE_G1[0] and s["ci95"][0] >= GATE_G1[1]
    ph = pd.DataFrame(res["units"]["primary"]["per_huc"])
    g2 = int((ph.loc[ph["positive_units"] >= REPLICATE_MIN_POS, "auc"] > GATE_G2[0]).sum()) >= GATE_G2[1]
    assert res["gates"]["G1"]["pass"] == g1 and res["gates"]["G2"]["pass"] == g2
    assert res["gates"]["proceed_to_M5"] == (g1 and g2)


def test_metric_ranges_and_intervals(res):
    for score in res["units"]["primary"]["scores"].values():
        for k, v in score.items():
            if "ci95" in v:
                lo, hi = v["ci95"]
                assert 0 <= lo <= hi <= 1, k
        caps = [score[f"capture_top{k}"]["value"] for k in (5, 10, 20)]
        assert caps == sorted(caps)  # capture is monotone in k


def test_rainfall_alone_is_near_chance_within_bins(res):
    # rainfall bins remove the trigger contrast by construction; a large value would mean the strata are too wide
    assert res["units"]["primary"]["scores"]["rain_only"]["auc_rain_stratified"]["value"] < 0.6


def test_no_probability_wording_in_report():
    text = (C.VALIDATION / "M4_BASELINE.md").read_text().lower()
    assert "not probabilities of future landslides" in text
    for bad in ("probability of landslide", "landslide probability", "chance of a landslide"):
        assert bad not in text


def test_extra_samples(res):
    d = C.INTERIM / f"labels_{REGION}"
    rep = json.loads((d / "samples_report.json").read_text())
    dom = pd.read_parquet(d / "domain_sample.parquet", columns=["positive", "exclusion", "rain_mm"])
    assert len(dom) == rep["domain_sample"]
    assert (dom["rain_mm"] >= C.TRIGGER_MM).all()
    assert np.isclose(res["rain_reference_mm"], dom["rain_mm"].median())
    run = pd.read_parquet(d / "positives_runoff.parquet", columns=["label"])
    assert len(run) == rep["runoff_cells_in_domain"]
