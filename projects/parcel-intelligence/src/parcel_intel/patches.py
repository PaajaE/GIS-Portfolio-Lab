"""Per-parcel morphological cleanup and connected components.

Semantics shared by the reference (this module) and the Rust kernel
(`parcel_kernels.screen_patches`); both must return identical integers.

Inputs
- parcel: int32 (H, W). 0 = no parcel (roads, water, outside AOI); 1..N = parcel index.
- feasible: bool/uint8 (H, W). 1 = cell passes every hard constraint of the scenario.
  Nodata (e.g. missing DEM) must already be encoded as 0.
- open_size: odd k >= 1. Opening by a k x k square: a cell survives only if some
  k x k square of feasible cells *of its own parcel* contains it. Cells outside the
  raster or in another parcel count as infeasible. k = 1 is the identity.
- connectivity: 4 or 8. Cells connect only within the same parcel.
- min_cells: components smaller than this are not counted as patches
  (they still count towards `feasible_cells`).

Outputs (per parcel index 0..N, index 0 unused)
- feasible_cells: cells remaining after opening
- largest_cells: size of the largest component (0 if none)
- n_patches: number of components with size >= min_cells
- mask: uint8 (H, W): 0 = not feasible, 1 = feasible after opening, 2 = in the
  largest component of its parcel. Ties are broken by the component whose first
  cell in row-major order comes first.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage


def _structure(connectivity: int) -> np.ndarray:
    if connectivity == 4:
        return ndimage.generate_binary_structure(2, 1)
    if connectivity == 8:
        return ndimage.generate_binary_structure(2, 2)
    raise ValueError("connectivity must be 4 or 8")


def _check(parcel, feasible, open_size):
    if parcel.shape != feasible.shape or parcel.ndim != 2:
        raise ValueError("parcel and feasible must be 2-D arrays of equal shape")
    if open_size < 1 or open_size % 2 == 0:
        raise ValueError("open_size must be a positive odd integer")


def screen_patches_reference(parcel, feasible, n_parcels, open_size=1, connectivity=4, min_cells=1):
    """Oracle: loop over parcels, crop to the bounding box, use scipy.ndimage."""
    parcel = np.asarray(parcel, dtype=np.int32)
    feasible = np.asarray(feasible).astype(bool)
    _check(parcel, feasible, open_size)
    structure = _structure(connectivity)
    se = np.ones((open_size, open_size), dtype=bool)
    r = open_size // 2

    feasible_cells = np.zeros(n_parcels + 1, dtype=np.int64)
    largest_cells = np.zeros(n_parcels + 1, dtype=np.int64)
    n_patches = np.zeros(n_parcels + 1, dtype=np.int64)
    out = np.zeros(parcel.shape, dtype=np.uint8)

    slices = ndimage.find_objects(parcel, max_label=n_parcels)
    for idx, sl in enumerate(slices, start=1):
        if sl is None:
            continue
        # Pad by r so the erosion sees the raster edge / neighbours as infeasible.
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        m = (parcel[y0:y1, x0:x1] == idx) & feasible[y0:y1, x0:x1]
        if not m.any():
            continue
        if open_size > 1:
            mp = np.pad(m, r, constant_values=False)
            eroded = ndimage.binary_erosion(mp, structure=se, border_value=0)
            opened = ndimage.binary_dilation(eroded, structure=se) & mp
            m = opened[r:-r, r:-r]
        if not m.any():
            continue
        labels, n = ndimage.label(m, structure=structure)
        sizes = np.bincount(labels.ravel())[1:]
        feasible_cells[idx] = int(sizes.sum())
        largest_cells[idx] = int(sizes.max())
        n_patches[idx] = int((sizes >= min_cells).sum())
        # scipy numbers labels in row-major order of first pixel, so argmax picks
        # the first-in-raster-order component among ties.
        best = int(np.argmax(sizes)) + 1
        region = out[y0:y1, x0:x1]
        region[m] = 1
        region[labels == best] = 2
    return feasible_cells, largest_cells, n_patches, out
