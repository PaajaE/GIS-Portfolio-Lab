"""Python entry points to the Rust kernels (`rust/`, crate firepath_kernels; PLAN §12).

`propagate_graph` has the signature and semantics of `firepath.reference.propagate` (Mode A `inside`,
Mode B `points`, `seed`); the reference stays the oracle (tests/test_kernels.py).
"""

from __future__ import annotations

from functools import lru_cache
from math import inf

import numpy as np
from firepath_kernels import propagate_graph as _rust_graph

from .reference import Result, SpreadField
from .slopeplane import frame
from .stencil import traversals


@lru_cache(maxsize=8)
def stencil_tables(radius: int):
    """Flatten the exact traversals (fractions -> float, as the reference does) for the Rust kernel."""
    meta, geom, pieces, sides = [], [], [], []
    for t in traversals(radius):
        meta.append((t.dr, t.dc, len(pieces), len(t.pieces), len(sides), len(t.vertex_sides)))
        geom.append((t.length, t.phi))
        pieces += [(dr, dc, float(fr)) for dr, dc, fr in t.pieces]
        sides += [(a[0], a[1], b[0], b[1]) for a, b in t.vertex_sides]
    return (np.array(meta, np.int64), np.array(geom, np.float64), np.array(pieces, np.float64),
            np.array(sides, np.int64).reshape(-1, 4))


def propagate_graph(f: SpreadField, radius: int = 8, *, points=(), inside=None, t0: float = 0.0,
                    t_stop: float = inf, seed=None) -> Result:
    c = lambda a, dt=np.float64: np.ascontiguousarray(a, dtype=dt)  # noqa: E731
    slope = None
    if f.tan_slope is not None:
        cs, ux, uy = (np.broadcast_to(v, f.shape) for v in frame(f.tan_slope, f.upslope))
        slope = (c(cs), c(ux), c(uy))
    pts = np.array([(r, cc, t) for r, cc, t in points], np.float64).reshape(-1, 3) if len(points) else None
    arr, st = _rust_graph(c(f.t_change), c(f.r_head), c(f.ecc), c(f.theta), c(f.burnable, bool), float(f.cell_m),
                          *stencil_tables(radius), slope=slope,
                          inside=None if inside is None else c(inside, bool), points=pts,
                          seed=None if seed is None else c(seed), t0=float(t0), t_stop=float(t_stop))
    return Result(arr.reshape(f.shape), st.reshape(f.shape))
