"""Pure-Python reference propagation: the oracle for the future Rust kernel (METHOD.md, "Propagation").

Deliberately simple and slow. It implements exactly the semantics specified in METHOD.md:

* spread field: piecewise constant in time on intervals [T_h, T_{h+1}); the field supplies, per cell and
  interval, the horizontal-plane speed along any direction (SpreadField.speed);
* edge-arrival function A_e(t_u): sequential exact integration over the crossed cells and the interval
  boundaries met during traversal (edge_arrival);
* label-setting (time-dependent Dijkstra) with heap key (time, cell index);
* Mode A initial perimeter: burnable inside cells are burned at t0 and traversing them costs nothing;
  inside barrier cells are never sources and stay barriers.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from math import cos, inf

import numpy as np

from .stencil import Traversal, edge_valid, traversals

# status codes of the output raster (METHOD.md, output schema)
NOT_REACHED, REACHED, INITIAL, BARRIER = 0, 1, 2, 3


@dataclass
class SpreadField:
    """Per-interval elliptical spread field on one grid.

    t_change: increasing times (min) at which interval h switches to h+1 (len H-1). Interval 0 also covers
        all t < t_change[0]; the last interval extends to +inf.
    r_head: (H, nr, nc) head rate of spread in the horizontal plane (m/min), > 0 on burnable cells.
    ecc: (H, nr, nc) ellipse eccentricity in [0, 1).
    theta: (H, nr, nc) direction of maximum spread (rad, counter-clockwise from east).
    burnable: (nr, nc) bool. Non-burnable cells are barriers.
    cell_m: cell size (m).
    """

    t_change: np.ndarray
    r_head: np.ndarray
    ecc: np.ndarray
    theta: np.ndarray
    burnable: np.ndarray
    cell_m: float
    _starts: list = field(init=False, repr=False)

    def __post_init__(self):
        h = self.r_head.shape[0]
        assert self.ecc.shape == self.theta.shape == self.r_head.shape
        assert self.r_head.shape[1:] == self.burnable.shape
        assert len(self.t_change) == h - 1 and np.all(np.diff(self.t_change) > 0)
        assert np.all(self.ecc >= 0) and np.all(self.ecc < 1)
        # zero spread is time-invariant: a burnable cell must spread in every interval
        assert np.all(self.r_head[:, self.burnable] > 0), "burnable cell with zero head ROS"
        self._starts = list(map(float, self.t_change))

    @property
    def shape(self):
        return self.burnable.shape

    def interval(self, t: float) -> tuple[int, float]:
        """(interval index containing t, end time of that interval)."""
        h = 0
        while h < len(self._starts) and t >= self._starts[h]:
            h += 1
        end = self._starts[h] if h < len(self._starts) else inf
        return h, end

    def speed(self, h: int, r: int, c: int, phi: float) -> float:
        e = self.ecc[h, r, c]
        return float(self.r_head[h, r, c] * (1.0 - e) / (1.0 - e * cos(phi - self.theta[h, r, c])))


def edge_arrival(f: SpreadField, r: int, c: int, t: Traversal, t_u: float,
                 inside: np.ndarray | None = None) -> float:
    """A_e(t_u): arrival time at the centre of v when leaving the centre of u at t_u.

    Pieces are traversed in order; inside a piece the speed is constant until the next interval boundary,
    where the remaining length continues at the new speed. Pieces in initial-perimeter cells cost nothing.
    Caller guarantees edge validity (no barrier crossed).
    """
    tau = t_u
    seg = t.length * f.cell_m
    for dr, dc, frac in t.pieces:
        rr, cc = r + dr, c + dc
        if inside is not None and inside[rr, cc]:
            continue
        rem = float(frac) * seg
        while rem > 0.0:
            h, end = f.interval(tau)
            s = f.speed(h, rr, cc, t.phi)
            dt = rem / s
            if tau + dt <= end:
                tau += dt
                rem = 0.0
            else:
                rem -= s * (end - tau)
                tau = end
    return tau


@dataclass
class Result:
    arrival: np.ndarray  # minutes; inf where not reached or barrier
    status: np.ndarray   # NOT_REACHED / REACHED / INITIAL / BARRIER


def propagate(f: SpreadField, radius: int = 2, *, points=(), inside: np.ndarray | None = None,
              t0: float = 0.0, t_stop: float = inf, boundary_sources_only: bool = False) -> Result:
    """Time-dependent label-setting propagation.

    points: iterable of (r, c, t) point ignitions (Mode B); each must be a burnable cell.
    inside: bool mask of cells whose centre lies inside the initial perimeter (Mode A) at time t0.
    boundary_sources_only: seed only inside cells that have at least one valid edge to a burnable
        outside cell. Must give identical arrivals to seeding all inside cells (tested).
    """
    nr, nc = f.shape
    barrier = ~f.burnable
    trs = traversals(radius)
    arrival = np.full((nr, nc), inf)
    status = np.where(barrier, BARRIER, NOT_REACHED).astype(np.uint8)
    done = np.zeros((nr, nc), bool)
    heap: list[tuple[float, int]] = []
    if inside is not None:
        inside = inside.astype(bool)
        src = inside & f.burnable
        done |= inside  # inside cells are fixed (burned at t0, or inside barriers)
        arrival[src] = t0
        status[src] = INITIAL
        for r, c in zip(*np.nonzero(src)):
            if boundary_sources_only and not any(
                edge_valid(barrier, r, c, t) and not inside[r + t.dr, c + t.dc] for t in trs
            ):
                continue
            heapq.heappush(heap, (t0, int(r) * nc + int(c)))
            done[r, c] = False  # re-opened only to be popped once as a source
    for r, c, t in points:
        if barrier[r, c]:
            raise ValueError(f"ignition on a barrier cell {(r, c)}")
        if t < arrival[r, c]:
            arrival[r, c] = t
            heapq.heappush(heap, (float(t), r * nc + c))
    while heap:
        t_u, k = heapq.heappop(heap)
        r, c = divmod(k, nc)
        if done[r, c] or t_u > arrival[r, c]:
            continue
        if t_u > t_stop:
            break
        done[r, c] = True
        for tr in trs:
            rv, cv = r + tr.dr, c + tr.dc
            if not (0 <= rv < nr and 0 <= cv < nc) or done[rv, cv] or barrier[rv, cv]:
                continue
            if inside is not None and inside[rv, cv]:
                continue
            if not edge_valid(barrier, r, c, tr):
                continue
            t_v = edge_arrival(f, r, c, tr, t_u, inside)
            if t_v < arrival[rv, cv]:
                arrival[rv, cv] = t_v
                heapq.heappush(heap, (t_v, rv * nc + cv))
    reached = np.isfinite(arrival) & (arrival <= t_stop) & (status == NOT_REACHED)
    status[reached] = REACHED
    arrival[(status == NOT_REACHED)] = inf
    return Result(arrival, status)


def uniform_field(shape, r_head, ecc=0.0, theta=0.0, *, t_change=(), cell_m=30.0, burnable=None):
    """Convenience constructor: scalars or per-interval sequences broadcast over the grid."""
    h = len(t_change) + 1
    def per_interval(v):
        v = np.asarray(v, dtype=float)
        if v.ndim == 0:
            v = np.full(h, float(v))
        if v.ndim == 1:
            v = v[:, None, None] * np.ones((1, *shape))
        return v
    b = np.ones(shape, bool) if burnable is None else burnable
    return SpreadField(np.asarray(t_change, float), per_interval(r_head), per_interval(ecc),
                       per_interval(theta), b, cell_m)
