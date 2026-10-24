import numpy as np
import pytest
from sklearn.metrics import average_precision_score, roc_auc_score

from landslide.baseline import vif_prune
from landslide.metrics import Ranked, block_bootstrap, ci


def test_auc_hand_case_with_ties():
    # positives 3, 2; negatives 2, 1: pairs (3>2) 1, (3>1) 1, (2=2) 0.5, (2>1) 1 -> 3.5 / 4
    r = Ranked(np.array([3, 2, 2, 1]), np.array([1, 1, 0, 0]))
    assert r.auc() == pytest.approx(0.875)


def test_auc_and_ap_match_sklearn_with_weights():
    rng = np.random.default_rng(0)
    s = rng.normal(size=2000).round(1)  # rounding creates ties
    y = (rng.random(2000) < 1 / (1 + np.exp(-2 * s))).astype(int)
    w = rng.uniform(0.5, 3, 2000)
    r = Ranked(s, y)
    assert r.auc(w) == pytest.approx(roc_auc_score(y, s, sample_weight=w), abs=1e-12)
    s2 = rng.normal(size=2000)  # no ties: AP identical to sklearn's step definition
    assert Ranked(s2, y).average_precision(w) == pytest.approx(average_precision_score(y, s2, sample_weight=w))


def test_stratified_auc_is_positive_weighted_mean_of_strata():
    s = np.array([1, 2, 3, 4, 10, 20, 30, 40.0])
    y = np.array([0, 1, 0, 1, 0, 0, 1, 1])
    g = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    r = Ranked(s, y, g)
    a0 = Ranked(s[:4], y[:4]).auc()
    a1 = Ranked(s[4:], y[4:]).auc()
    assert r.stratified_auc() == pytest.approx((2 * a0 + 2 * a1) / 4)
    # strata without both classes are skipped
    r2 = Ranked(np.r_[s, 5], np.r_[y, 1], np.r_[g, 2])
    assert r2.stratified_auc() == pytest.approx(r.stratified_auc())
    # a between-stratum shift (positives concentrated in the high-score stratum) inflates the pooled AUC:
    # within AUCs 1/3 (1 positive) and 2/3 (3 positives) -> stratified 7/12; pooled 12/16
    r3 = Ranked(np.array([1, 2, 3, 4, 11, 12, 13, 14.0]), np.array([0, 1, 0, 0, 1, 0, 1, 1]), g)
    assert r3.stratified_auc() == pytest.approx(7 / 12)
    assert r3.auc() == pytest.approx(0.75)


def test_capture_interpolates_area():
    # areas 1,1,2 (score order 3,2,1) -> cumulative 25/50/100 %; hits 2,0,2 -> 50/50/100 %.
    # 12.5 % of the area is half of the first row -> half of its 2 hits = 1 of 4
    r = Ranked(np.array([3, 2, 1.0]), np.array([1, 0, 1]))
    cap = r.capture(np.array([2, 0, 2.0]), np.array([1, 1, 2.0]), [0.125, 0.25, 0.5, 0.75, 1.0])
    assert cap == pytest.approx([0.25, 0.5, 0.5, 0.75, 1.0])


def test_block_bootstrap_resamples_whole_groups():
    groups = np.array([0, 0, 1, 1, 1])
    reps = block_bootstrap(groups, lambda w: np.array([w[0] == w[1], w[2] == w[4], w.sum()]), 200, 1)
    assert reps[:, 0].all() and reps[:, 1].all()
    assert set(np.unique(reps[:, 2])) <= {4.0, 5.0, 6.0}  # 2+2, 2+3, 3+3 rows
    lo, hi = ci(reps)[2]
    assert 4 <= lo <= hi <= 6


def test_vif_prune_drops_collinear_but_keeps_protected():
    rng = np.random.default_rng(1)
    a = rng.normal(size=500)
    X = np.column_stack([a, a + 0.01 * rng.normal(size=500), rng.normal(size=500)])
    keep = vif_prune(X, ["a", "a2", "b"], protected=("a",))
    assert keep == [0, 2]
    # without protection the listed (priority) order decides which of the collinear pair stays
    assert vif_prune(X[:, [1, 0, 2]], ["a2", "a", "b"], protected=()) == [0, 2]
