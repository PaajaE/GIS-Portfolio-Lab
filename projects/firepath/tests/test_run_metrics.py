import numpy as np

from firepath.maps import classify
from firepath.run import step_metrics


def test_step_metrics_growth_scores():
    burnable = np.ones((1, 6), bool)
    mask_k = np.array([[1, 0, 0, 0, 0, 0]], bool)
    mask_next = np.array([[1, 1, 1, 0, 0, 0]], bool)
    arr = np.array([[0.0, 50.0, 150.0, 80.0, np.inf, np.inf]])     # t_k = 0, t_next = 100
    m = step_metrics(arr, 0.0, 100.0, mask_k, mask_next, burnable)
    assert (m["obs_growth"], m["model_growth"]) == (2, 2)
    assert m["recall"] == 0.5 and m["precision"] == 0.5 and m["dice"] == 0.5
    assert m["share_late"] == 0.5 and m["median_late_h"] == 50 / 60


def test_classify_bins():
    h = np.array([-30, -24, -13, -3, -0.1, 0, 0.1, 3, 3.1, 12.5, 30]) * 60.0
    assert classify(h).tolist() == [0, 0, 1, 2, 3, 4, 5, 5, 6, 7, 8]
