import numpy as np
import pytest

from landslide.advanced import GBM, area_percentile, cols_of


def test_area_percentile_is_cumulative_area_share_in_score_order():
    score = np.array([0.1, 0.9, 0.5])
    area = np.array([2.0, 1.0, 1.0])
    # order 0.9 (1), 0.5 (1), 0.1 (2) -> cumulative 25 %, 50 %, 100 %
    assert area_percentile(score, area) == pytest.approx([1.0, 0.25, 0.5])


def test_cols_of_matches_one_hot_columns_but_not_prefixes():
    names = ["hsg_0", "hsg_3", "hsg_cd_frac", "slope_deg", "slope_deg_p90"]
    out = cols_of({"soil": ["hsg"], "slope": ["slope_deg"]}, names)
    assert out == {"soil": [0, 1], "slope": [3]}


def test_gbm_tunes_on_training_groups_only_and_ranks_signal():
    rng = np.random.default_rng(0)
    n = 3000
    x = rng.normal(size=n)
    rain = rng.uniform(250, 500, n)
    y = (rng.random(n) < 1 / (1 + np.exp(-(2 * x - 3)))).astype(int)
    X = np.column_stack([x, rng.normal(size=n), rain])
    groups = np.repeat(np.arange(6), n // 6)
    grid = [{"max_leaf_nodes": 3, "min_samples_leaf": 20, "max_iter": 20},
            {"max_leaf_nodes": 7, "min_samples_leaf": 20, "max_iter": 50}]
    m = GBM(["x", "noise", "rain_mm"], grid, 3, {"rain_mm": 330.0}).fit(X, y, None, groups)
    assert m.params in grid and len(m.inner_scores) == 2
    s = m.linear(np.column_stack([np.linspace(-2, 2, 5), np.zeros(5), np.full(5, 330.0)]))
    assert np.all(np.diff(s) >= -1e-9) and s[-1] > s[0]
