"""Rust kernel vs the scipy reference, plus hand-computed fixtures."""

import numpy as np
import pytest
from parcel_kernels import screen_patches

from parcel_intel.patches import screen_patches_reference


def random_case(seed, h=60, w=80, n_parcels=12, p_feasible=0.8):
    rng = np.random.default_rng(seed)
    # Voronoi-style parcels with a few holes (parcel 0 = road / no parcel)
    ys, xs = rng.integers(0, h, n_parcels), rng.integers(0, w, n_parcels)
    yy, xx = np.mgrid[0:h, 0:w]
    d = (yy[..., None] - ys) ** 2 + (xx[..., None] - xs) ** 2
    parcel = (np.argmin(d, axis=2) + 1).astype(np.int32)
    parcel[rng.random((h, w)) < 0.03] = 0
    parcel[:, w // 2] = 0  # a "road" splitting the raster
    # spatially clustered feasibility
    noise = rng.random((h // 4 + 1, w // 4 + 1))
    noise = np.kron(noise, np.ones((4, 4)))[:h, :w] + 0.3 * rng.random((h, w))
    feasible = noise < np.quantile(noise, p_feasible)
    return parcel, feasible, n_parcels


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("open_size", [1, 3, 5])
@pytest.mark.parametrize("connectivity", [4, 8])
def test_rust_matches_reference(seed, open_size, connectivity):
    parcel, feasible, n = random_case(seed)
    ref = screen_patches_reference(parcel, feasible, n, open_size, connectivity, min_cells=5)
    got = screen_patches(parcel, feasible, n, open_size, connectivity, 5)
    for r, g in zip(ref, got):
        np.testing.assert_array_equal(r, g)


def test_hand_computed_opening():
    # 4x4 feasible block plus a 1-cell tail; 3x3 opening keeps exactly the block.
    parcel = np.ones((5, 6), dtype=np.int32)
    feasible = np.zeros((5, 6), dtype=bool)
    feasible[0:4, 0:4] = True
    feasible[1, 4:6] = True
    for impl in (screen_patches_reference, screen_patches):
        fc, lc, npch, mask = impl(parcel, feasible, 1, 3, 4, 1)
        assert fc[1] == 16 and lc[1] == 16 and npch[1] == 1
        assert (mask == 2).sum() == 16 and mask[1, 4] == 0


def test_raster_edge_counts_as_infeasible():
    parcel = np.ones((3, 3), dtype=np.int32)
    feasible = np.ones((3, 3), dtype=bool)
    # a 5x5 opening cannot fit into a 3x3 raster
    for impl in (screen_patches_reference, screen_patches):
        fc, lc, _, _ = impl(parcel, feasible, 1, 5, 4, 1)
        assert fc[1] == 0 and lc[1] == 0


def test_all_infeasible_and_missing_parcels():
    parcel = np.array([[0, 0], [2, 2]], dtype=np.int32)  # parcel 1 absent
    feasible = np.zeros((2, 2), dtype=bool)
    for impl in (screen_patches_reference, screen_patches):
        fc, lc, npch, mask = impl(parcel, feasible, 3, 1, 4, 1)
        assert fc.tolist() == [0, 0, 0, 0] and mask.sum() == 0
