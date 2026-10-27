"""Exact asymptotic accuracy of label-setting stencils for focus-anchored ellipses (homogeneous medium).

For each stencil radius and LB: worst forward relative arrival error over wind angles 0-45 deg (2.5 deg
steps; criterion 1 of the D1 bake-off) and the spread of the burned-area ratio hull/ellipse across those
angles (criterion 2). Exact in the asymptotic limit; the full-propagation fixture reproduces criterion 1
to 0.1 % (CRITICAL_REVIEW P0-1). Run: uv run python -m firepath.stencil_table
"""

from __future__ import annotations

import json
from math import atan2, gcd

import numpy as np

from .stencil import _convex_hull, stencil, stencil_error

ANGLES = [2.5 * i for i in range(19)]


def area_ratio(radius: int, lb: float, wind: float) -> float:
    ecc = np.sqrt(lb * lb - 1) / lb
    offs = stencil(radius)
    ang = np.array([atan2(-dr, dc) for dr, dc in offs])
    rad = (1 - ecc) / (1 - ecc * np.cos(ang - wind))
    h = _convex_hull(np.stack([rad * np.cos(ang), rad * np.sin(ang)], 1))
    x, y = h[:, 0], h[:, 1]
    a_hull = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    a = 1 / (1 + ecc)
    return a_hull / (np.pi * a * a * np.sqrt(1 - ecc * ecc))


def table(radii=(2, 8, 12, 16), lbs=(2.0, 3.0, 4.0, 8.0)):
    out = []
    for r in radii:
        for lb in lbs:
            errs = [stencil_error(r, lb, np.radians(a))["forward_max"] for a in ANGLES]
            areas = [area_ratio(r, lb, np.radians(a)) for a in ANGLES]
            out.append({"radius": r, "directions": len(stencil(r)), "lb": lb, "c1_worst_fwd": max(errs),
                        "area_ratio_min": min(areas), "area_ratio_max": max(areas),
                        "c2_area_spread": (max(areas) - min(areas)) / float(np.mean(areas))})
    return out


if __name__ == "__main__":
    print(json.dumps(table(), indent=1))
