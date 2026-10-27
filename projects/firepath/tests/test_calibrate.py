"""Calibration objective on a hand-checked case (PLAN §8)."""

import numpy as np

from firepath.calibrate import Case, score
from firepath.observed import CONSISTENT, INCONSISTENT, INITIAL, NEVER


class _St:
    burnable = np.ones((1, 6), bool)


def test_primary_scores_consistent_and_model_burned_never_cells_only():
    rel = np.array([0.0, 600.0, 1200.0])
    flag = np.array([[INITIAL, CONSISTENT, CONSISTENT, NEVER, NEVER, INCONSISTENT]])
    lo = np.array([[-np.inf, 0, 600, 1200, 1200, 0]], float)
    hi = np.array([[0, 600, 1200, np.inf, np.inf, 600]], float)
    masks = [flag == INITIAL, (flag == INITIAL) | (np.arange(6) == 1)[None], (flag != NEVER)]
    S = {"rel": rel, "masks_w": masks, "lo": lo, "hi": hi, "st": _St()}
    case = Case("x", S, flag == CONSISTENT, flag == NEVER)
    # cell1 inside, cell2 120 min early, cell3 burned by model at 900 (early by 300), cell4 never reached
    arr = np.array([[0.0, 300.0, 480.0, 900.0, np.inf, 50.0]])
    s = score(case, arr)
    assert s["n"] == 3
    assert np.isclose(s["primary_h"], (0 + 2 + 5) / 3)
    assert np.isclose(s["signed_h"], -(2 + 5) / 3)
    # a masked interval removes cell 2 from scoring
    case_m = Case("x", S, (flag == CONSISTENT) & (np.arange(6) != 2)[None], flag == NEVER)
    assert score(case_m, arr)["n"] == 2
