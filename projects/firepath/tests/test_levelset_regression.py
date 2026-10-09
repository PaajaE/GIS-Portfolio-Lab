"""Regression: level set must never burn a cell before its hard physical lower bound.

Found in M1a-2 (isotropic two-fuel mosaic): without narrow band + reinitialization, the level-set field
far ahead of the front distorted until spurious zero crossings appeared (537 cells burned before
distance / max speed allowed). Lower bound: Euclidean distance from the initial *raster* region (the
cells both schemes start from) divided by the maximum spread speed anywhere on the grid; no slack.
"""

import numpy as np
import pytest

from firepath.canonical import raster_lower_bound
from firepath.levelset import propagate_levelset
from firepath.mosaic import T_STOP, build


@pytest.mark.parametrize("case", ["iso", "lb2", "lb4"])
def test_no_arrival_before_physical_lower_bound(case):
    f, inside = build(case, 1)
    lower = raster_lower_bound(inside, f.cell_m, float(f.r_head.max()))
    a = propagate_levelset(f, inside=inside, t_stop=T_STOP, order=5).arrival
    bad = np.isfinite(a) & ~inside & (a < lower * (1 - 1e-9))
    assert bad.sum() == 0, f"{bad.sum()} cells burned before their physical lower bound"
