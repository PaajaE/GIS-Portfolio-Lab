"""Eulerian level-set candidate for the D1 bake-off (METHOD.md, "Propagation", option B).

phi < 0 is burned. The front moves with the Huygens envelope of focus-anchored ellipses, i.e. the
Hamilton-Jacobi equation  phi_t + H(grad phi) = 0  with H(p) = support function of the unit-time spread set:

    H(p) = a [ e (p.w) + sqrt( (p.w)^2 + (1 - e^2) (p.w_perp)^2 ) ],   a = R_head / (1 + e)

(w = max-spread direction). H is convex and positively 1-homogeneous; |dH/dp| <= R_head.
Discretisation: local Lax-Friedrichs numerical Hamiltonian, second-order ENO one-sided differences,
Heun (RK2) time stepping, CFL-limited dt, steps aligned to weather-interval boundaries.
Barriers: H = 0 and phi frozen; derivatives are taken only from the 4-neighbour ENO stencil, which never
reaches across a one-cell wall into burned cells beyond it (tested).
Arrival time per cell = linear interpolation of the zero crossing within a step.

Same SpreadField as the label-setting reference, so both schemes see identical inputs.
"""

from __future__ import annotations

from math import inf

import numpy as np

from .reference import BARRIER, INITIAL, NOT_REACHED, REACHED, Result, SpreadField
from .slopeplane import cov_to_slope, frame, vec_to_horizontal, w_in_slope


def _hamiltonian(px, py, a, e, wx, wy):
    pw = px * wx + py * wy
    pp = -px * wy + py * wx
    return a * (e * pw + np.sqrt(pw * pw + (1.0 - e * e) * pp * pp))


def _grad_hamiltonian(px, py, a, e, wx, wy):
    """Signed (dH/dpx, dH/dpy) of the support-function Hamiltonian."""
    pw = px * wx + py * wy
    pp = -px * wy + py * wx
    s = np.sqrt(pw * pw + (1.0 - e * e) * pp * pp)
    s = np.where(s > 0, s, 1.0)
    hw = a * (e + pw / s)
    hp = a * (1.0 - e * e) * pp / s
    return hw * wx - hp * wy, hw * wy + hp * wx


def _dhamiltonian(px, py, a, e, wx, wy):
    """(|dH/dpx|, |dH/dpy|) of the support-function Hamiltonian."""
    gx, gy = _grad_hamiltonian(px, py, a, e, wx, wy)
    return np.abs(gx), np.abs(gy)


class _Ham:
    """H(p) and |dH/dp| for planar or slope-plane cells (slopeplane.py): H(p) = h_E(P^T p),
    dH/dp = P grad h_E(P^T p)."""

    def __init__(self, a, e, wx, wy, slope=None):
        self.a, self.e, self.slope = a, e, slope
        if slope is None:
            self.w = (wx, wy)
        else:
            cs, ux, uy = slope
            self.w = w_in_slope(np.arctan2(wy, wx), cs, ux, uy)

    def __call__(self, px, py):
        if self.slope is not None:
            px, py = cov_to_slope(px, py, *self.slope)
        return _hamiltonian(px, py, self.a, self.e, *self.w)

    def dabs(self, px, py):
        if self.slope is None:
            return _dhamiltonian(px, py, self.a, self.e, *self.w)
        q1, q2 = cov_to_slope(px, py, *self.slope)
        g1, g2 = _grad_hamiltonian(q1, q2, self.a, self.e, *self.w)
        gx, gy = vec_to_horizontal(g1, g2, *self.slope)
        return np.abs(gx), np.abs(gy)

    def half_extents(self):
        """Extent of the horizontal spread set from the focus along x and y: max(H(+-x)), max(H(+-y))."""
        one, zero = np.ones_like(self.a), np.zeros_like(self.a)
        ax = np.maximum(self(one, zero), self(-one, zero))
        ay = np.maximum(self(zero, one), self(zero, -one))
        return ax, ay


def _eno2(phi, dx):
    """One-sided second-order ENO derivatives (backward '-', forward '+') along columns (x, east) and rows.

    Returns (dx_minus, dx_plus, dy_minus, dy_plus) with y pointing north (rows grow southward).
    Ghost cells by edge replication.
    """
    g = np.pad(phi, 2, mode="edge")
    c = g[2:-2, 2:-2]

    def along(axis):
        def s(k):  # shifted array by k cells along axis
            if axis == 1:
                return g[2:-2, 2 + k: g.shape[1] - 2 + k]
            return g[2 + k: g.shape[0] - 2 + k, 2:-2]
        d1m = (c - s(-1)) / dx
        d1p = (s(1) - c) / dx
        d2c = (s(1) - 2 * c + s(-1)) / dx**2
        d2m = (c - 2 * s(-1) + s(-2)) / dx**2
        d2p = (s(2) - 2 * s(1) + c) / dx**2
        minus = d1m + 0.5 * dx * np.where(np.abs(d2m) < np.abs(d2c), d2m, d2c)
        plus = d1p - 0.5 * dx * np.where(np.abs(d2p) < np.abs(d2c), d2p, d2c)
        return minus, plus

    xm, xp = along(1)
    rm, rp = along(0)          # derivative w.r.t. row index (southward)
    return xm, xp, -rp, -rm    # d/dy = -d/drow: backward-in-y = -(forward-in-row)


def _weno5(phi, dx):
    """Fifth-order WENO one-sided derivatives for Hamilton-Jacobi (Jiang & Peng 2000; Osher & Fedkiw
    2003, ch. 3). Returns (dx_minus, dx_plus, dy_minus, dy_plus), y north. Ghost cells: edge replication."""
    g = np.pad(phi, 3, mode="edge")

    def w5(v1, v2, v3, v4, v5):
        s1 = 13 / 12 * (v1 - 2 * v2 + v3) ** 2 + 0.25 * (v1 - 4 * v2 + 3 * v3) ** 2
        s2 = 13 / 12 * (v2 - 2 * v3 + v4) ** 2 + 0.25 * (v2 - v4) ** 2
        s3 = 13 / 12 * (v3 - 2 * v4 + v5) ** 2 + 0.25 * (3 * v3 - 4 * v4 + v5) ** 2
        # pointwise epsilon (Osher & Fedkiw 2003, eq. 3.39 form): local, so distant data (e.g. unclamped
        # phi at barriers) cannot change the weights at the front (2026-10-25; was a global max)
        eps = 1e-6 * np.maximum.reduce([v1 * v1, v2 * v2, v3 * v3, v4 * v4, v5 * v5]) + 1e-99
        a1, a2, a3 = 0.1 / (eps + s1) ** 2, 0.6 / (eps + s2) ** 2, 0.3 / (eps + s3) ** 2
        tot = a1 + a2 + a3
        return (a1 * (v1 / 3 - 7 * v2 / 6 + 11 * v3 / 6) + a2 * (-v2 / 6 + 5 * v3 / 6 + v4 / 3)
                + a3 * (v3 / 3 + 5 * v4 / 6 - v5 / 6)) / tot

    def along(axis):
        n = g.shape[axis]

        def d(k):  # forward difference D+ phi_{i+k} = (phi_{i+k+1} - phi_{i+k}) / dx on the interior
            sl1 = [slice(3, -3), slice(3, -3)]
            sl0 = [slice(3, -3), slice(3, -3)]
            sl1[axis] = slice(3 + k + 1, n - 3 + k + 1)
            sl0[axis] = slice(3 + k, n - 3 + k)
            return (g[tuple(sl1)] - g[tuple(sl0)]) / dx

        minus = w5(d(-3), d(-2), d(-1), d(0), d(1))
        plus = w5(d(2), d(1), d(0), d(-1), d(-2))
        return minus, plus

    xm, xp = along(1)
    rm, rp = along(0)
    return xm, xp, -rp, -rm


def _near(mask, axis, k):
    """Cells within k cells of a True cell along one axis (inclusive)."""
    out = mask.copy()
    for d in range(1, k + 1):
        if axis == 1:
            out[:, d:] |= mask[:, :-d]
            out[:, :-d] |= mask[:, d:]
        else:
            out[d:, :] |= mask[:-d, :]
            out[:-d, :] |= mask[d:, :]
    return out


def _first_order_neumann(ph, dx, barrier):
    """One-sided first differences with zero flux across barrier faces (ghost value = own value)."""
    g = np.pad(ph, 1, mode="edge")
    b = np.pad(barrier, 1, mode="constant", constant_values=False)
    left, right = g[1:-1, :-2], g[1:-1, 2:]
    up, down = g[:-2, 1:-1], g[2:, 1:-1]
    left = np.where(b[1:-1, :-2], ph, left)
    right = np.where(b[1:-1, 2:], ph, right)
    up = np.where(b[:-2, 1:-1], ph, up)
    down = np.where(b[2:, 1:-1], ph, down)
    xm, xp = (ph - left) / dx, (right - ph) / dx
    ym, yp = -(down - ph) / dx, -(ph - up) / dx
    return xm, xp, ym, yp


def _interface_points(phi, barrier, offset=(0, 0)):
    """Zero crossings of phi on grid edges (linear interpolation), densified inside each grid square.

    Coordinates in cell units (row, col) of cell centres, shifted by the integer `offset` of a work
    window (added before the fractional part, so coordinates equal the whole-grid ones bit for bit).
    Pairs touching a barrier cell are ignored.
    Returns (points[N, 2], mask of cells adjacent to a crossing).
    """
    neg = phi <= 0
    adj = np.zeros(phi.shape, bool)
    pts = []
    # horizontal edges (r, c)-(r, c+1)
    a, b = phi[:, :-1], phi[:, 1:]
    ok = (neg[:, :-1] != neg[:, 1:]) & ~barrier[:, :-1] & ~barrier[:, 1:]
    hx = np.where(ok, a / np.where(ok, a - b, 1.0), np.nan)
    # vertical edges (r, c)-(r+1, c)
    a2, b2 = phi[:-1, :], phi[1:, :]
    ok2 = (neg[:-1, :] != neg[1:, :]) & ~barrier[:-1, :] & ~barrier[1:, :]
    vy = np.where(ok2, a2 / np.where(ok2, a2 - b2, 1.0), np.nan)
    o0, o1 = offset
    r, c = np.nonzero(ok)
    pts.append(np.stack([r + o0, (c + o1) + hx[r, c]], 1))
    adj[r, c] = adj[r, c + 1] = True
    r2, c2 = np.nonzero(ok2)
    pts.append(np.stack([(r2 + o0) + vy[r2, c2], c2 + o1], 1))
    adj[r2, c2] = adj[r2 + 1, c2] = True
    # densify: in each grid square with exactly two crossings, add 3 points on the chord between them
    top, bot = hx[:-1, :], hx[1:, :]          # square (r, c): top edge row r, bottom edge row r+1
    lef, rig = vy[:, :-1], vy[:, 1:]          # left edge col c, right edge col c+1
    rr, cc = np.mgrid[0:phi.shape[0] - 1, 0:phi.shape[1] - 1]
    rr, cc = rr + o0, cc + o1
    cand = [(rr, cc + top), (rr + 1, cc + bot), (rr + lef, cc), (rr + rig, cc + 1)]
    have = np.stack([np.isfinite(top), np.isfinite(bot), np.isfinite(lef), np.isfinite(rig)])
    two = have.sum(0) == 2
    if two.any():
        ys = np.stack([q[0] for q in cand])
        xs = np.stack([q[1] for q in cand])
        order_ = np.argsort(~have, axis=0, kind="stable")[:2]   # indices of the two crossings
        sel = two
        y0 = np.take_along_axis(ys, order_[:1], 0)[0][sel]
        x0 = np.take_along_axis(xs, order_[:1], 0)[0][sel]
        y1 = np.take_along_axis(ys, order_[1:2], 0)[0][sel]
        x1 = np.take_along_axis(xs, order_[1:2], 0)[0][sel]
        for w in (0.25, 0.5, 0.75):
            pts.append(np.stack([y0 + w * (y1 - y0), x0 + w * (x1 - x0)], 1))
    return np.concatenate(pts) if pts else np.zeros((0, 2)), adj


def _redistance(phi, dx, barrier, band):
    """Geometric reinitialization to a signed distance (clamped at +-band cells).

    Distance from every cell centre (including cells adjacent to the interface) to the densified zero
    crossings (KD-tree), signed by the current phi. Using the distance for the adjacent cells too keeps the
    crossing positions to first order (straight interface: both neighbours scale alike) and avoids the
    gradient jump of the keep-adjacent variant, which was measured to be less accurate (M1a-3).
    """
    from scipy.spatial import cKDTree

    pts, adj = _interface_points(phi, barrier)
    if len(pts) == 0:
        return np.clip(phi, -band * dx, band * dx)
    nr, nc = phi.shape
    rr, cc = np.mgrid[0:nr, 0:nc]
    d, _ = cKDTree(pts).query(np.stack([rr.ravel(), cc.ravel()], 1), distance_upper_bound=band + 1)
    d = np.minimum(d.reshape(nr, nc), band) * dx
    new = np.where(phi <= 0, -d, d)
    new = np.where(barrier, phi, new)
    return np.clip(new, -band * dx, np.maximum(band * dx, phi * barrier))


def _extension_index(phi, barrier, offset=(0, 0)):
    """Flat index of the cell containing each cell's nearest interface point (extension velocities,
    Adalsteinsson & Sethian 1999): spread parameters are taken from the front's own location, so the
    field away from the front does not see the speed jumps of cells the front has not reached."""
    from scipy.spatial import cKDTree

    nr, nc = phi.shape
    o0, o1 = offset
    pts, _ = _interface_points(phi, barrier, offset)
    if len(pts) == 0:
        return np.arange(nr * nc).reshape(nr, nc)
    rr, cc = np.mgrid[0:nr, 0:nc]
    _, j = cKDTree(pts).query(np.stack([(rr + o0).ravel(), (cc + o1).ravel()], 1))
    cell_r = np.clip(np.rint(pts[j, 0]).astype(int) - o0, 0, nr - 1)
    cell_c = np.clip(np.rint(pts[j, 1]).astype(int) - o1, 0, nc - 1)
    idx = (cell_r * nc + cell_c).reshape(nr, nc)
    return np.where(barrier, np.arange(nr * nc).reshape(nr, nc), idx)


def propagate_levelset(f: SpreadField, *, points=(), inside=None, t0=0.0, t_stop=inf,
                       r0_cells=2.0, cfl=0.4, first_order=False, dissipation="local",
                       order: int = 2, reinit_every: int = 10, band_cells: float = 8.0,
                       extension: bool = True) -> Result:
    """Level-set propagation on the same inputs as `reference.propagate`.

    points: (r, c, t) point ignitions, represented by a disc of radius r0_cells at time t (all points must
        share one t; the level set has no point sources).
    inside: Mode A mask (cells burned at t0); phi0 = signed distance to the cell-centre raster region.
    """
    nr, nc = f.shape
    dx = f.cell_m
    barrier = ~f.burnable
    yy, xx = np.mgrid[0:nr, 0:nc]
    if inside is not None:
        from scipy.ndimage import distance_transform_edt
        ins = inside.astype(bool)
        phi = (distance_transform_edt(~ins) - distance_transform_edt(ins) + 0.5 * (~ins) - 0.5 * ins) * dx
        t_start = t0
        init = ins & f.burnable
    else:
        times = {float(p[2]) for p in points}
        if len(times) != 1:
            raise ValueError("level set needs one common ignition time")
        t_start = times.pop()
        phi = np.full((nr, nc), np.inf)
        for r, c, _ in points:
            if barrier[r, c]:
                raise ValueError(f"ignition on a barrier cell {(r, c)}")
            phi = np.minimum(phi, (np.hypot(yy - r, xx - c) - r0_cells) * dx)
        init = (phi <= 0) & f.burnable
    arrival = np.full((nr, nc), inf)
    arrival[init] = t_start
    phi = np.where(barrier, np.maximum(phi, dx), phi)  # barriers never burn
    frozen = barrier
    if reinit_every:  # narrow band + periodic reinitialization (state of practice; M1a-2 fix)
        phi = _redistance(phi, dx, barrier, band_cells)
    step = 0

    radius = {5: 3}.get(order, 2)
    near_x = _near(barrier, 1, radius)
    near_y = _near(barrier, 0, radius)
    t = t_start
    margin = radius + 2
    while t < t_stop and np.any(~np.isfinite(arrival) & ~barrier):
        h, end = f.interval(t)
        # Work window: every cell that can change this step (non-frozen before and after the band update)
        # plus the widest stencil. Cells outside it are frozen, so the result is identical to a
        # whole-grid step; only the cost changes (performance, 2026-10-25).
        live = ~frozen
        if reinit_every:
            live = live | ((np.abs(phi) < (band_cells - 0.5) * dx) & ~barrier)
        rows = np.flatnonzero(live.any(1))
        cols = np.flatnonzero(live.any(0))
        if rows.size == 0:
            break
        # even start offsets: interface points at exact half-cells round half-to-even (np.rint), so an
        # even shift keeps the extension-velocity cell assignment identical to the whole-grid step
        r0, c0 = max(rows[0] - margin, 0) // 2 * 2, max(cols[0] - margin, 0) // 2 * 2
        W = (slice(r0, min(rows[-1] + margin + 1, nr)), slice(c0, min(cols[-1] + margin + 1, nc)))
        wr, wc = W[0].stop - W[0].start, W[1].stop - W[1].start
        ph_w, bar_w = phi[W], barrier[W]
        a = f.r_head[h][W] / (1.0 + f.ecc[h][W])
        e = f.ecc[h][W]
        wx, wy = np.cos(f.theta[h][W]), np.sin(f.theta[h][W])
        slope = None if f.tan_slope is None else tuple(
            np.broadcast_to(v, (nr, nc))[W] for v in frame(f.tan_slope, f.upslope))
        if extension:
            ix = _extension_index(ph_w, bar_w, (W[0].start, W[1].start))
            a, e = a.ravel()[ix], e.ravel()[ix]
            wx, wy = wx.ravel()[ix], wy.ravel()[ix]
            if slope is not None:
                slope = tuple(v.ravel()[ix] for v in slope)
        ham_fn = _Ham(a, e, wx, wy, slope)
        # direction-specific LF bounds: half-extent of the horizontal unit-time spread set along x and y,
        # measured from the focus (planar: |a e w_i| + sqrt(a^2 w_i^2 + b^2 w_perp_i^2) <= R_head)
        ax, ay = ham_fn.half_extents()
        if not np.isscalar(ax):
            g_ax, g_ay = np.pad(ax, 1, mode="edge"), np.pad(ay, 1, mode="edge")
            ax = np.maximum.reduce([g_ax[1:-1, 1:-1], g_ax[1:-1, :-2], g_ax[1:-1, 2:]])
            ay = np.maximum.reduce([g_ay[1:-1, 1:-1], g_ay[:-2, 1:-1], g_ay[2:, 1:-1]])
        ax = np.where(frozen[W], 0.0, ax)
        ay = np.where(frozen[W], 0.0, ay)
        amax = float((ax + ay).max())
        if amax == 0:
            break
        dt = cfl * dx / amax
        dt = min(dt, end - t, t_stop - t)
        if dt <= 0:
            t = end
            continue

        if reinit_every:
            active = np.abs(phi) < (band_cells - 0.5) * dx
            frozen = barrier | ~active
        else:
            frozen = barrier
        fr_w, nx_w, ny_w = frozen[W], near_x[W], near_y[W]

        def rhs(ph):
            fm = _first_order_neumann(ph, dx, bar_w)
            if first_order:
                xm, xp, ym, yp = fm
            else:
                hi = _weno5(ph, dx) if order == 5 else _eno2(ph, dx)
                # barrier faces: zero flux; high-order stencils touching a barrier fall back to first order
                xm, xp = (np.where(nx_w, fm[i], hi[i]) for i in (0, 1))
                ym, yp = (np.where(ny_w, fm[i], hi[i]) for i in (2, 3))
            px, py = 0.5 * (xm + xp), 0.5 * (ym + yp)
            ham = ham_fn(px, py)
            if dissipation == "local":  # |dH/dp| at the corners of the local gradient box (SLLF)
                cx = np.zeros_like(ph)
                cy = np.zeros_like(ph)
                for gx in (xm, xp):
                    for gy in (ym, yp):
                        hx, hy = ham_fn.dabs(gx, gy)
                        cx = np.maximum(cx, hx)
                        cy = np.maximum(cy, hy)
                cx = np.minimum(cx, ax)
                cy = np.minimum(cy, ay)
            else:
                cx, cy = ax, ay
            diss = cx * 0.5 * (xp - xm) + cy * 0.5 * (yp - ym)
            out = -(ham - diss)
            out[fr_w] = 0.0
            return out

        if order == 5:  # TVD RK3 (Shu & Osher)
            p1 = ph_w + dt * rhs(ph_w)
            p2 = 0.75 * ph_w + 0.25 * (p1 + dt * rhs(p1))
            new = ph_w / 3 + 2 / 3 * (p2 + dt * rhs(p2))
        else:           # Heun (TVD RK2)
            mid = ph_w + dt * rhs(ph_w)
            new = 0.5 * (ph_w + mid + dt * rhs(mid))
        arr_w = arrival[W]
        cross = (ph_w > 0) & (new <= 0) & ~np.isfinite(arr_w)
        frac = np.where(cross, ph_w / np.where(cross, ph_w - new, 1.0), 0.0)
        arr_w[cross] = t + dt * frac[cross]
        phi[W] = new
        t += dt
        step += 1
        if reinit_every and step % reinit_every == 0:
            phi = _redistance(phi, dx, barrier, band_cells)

    status = np.where(barrier, BARRIER, NOT_REACHED).astype(np.uint8)
    status[init] = INITIAL
    reached = np.isfinite(arrival) & (arrival <= t_stop) & (status == NOT_REACHED)
    status[reached] = REACHED
    arrival[status == NOT_REACHED] = inf
    return Result(arrival, status)


def propagate_hybrid(f: SpreadField, *, radius: int = 8, points=(), inside=None, t0=0.0, t_stop=inf,
                     r0_cells=2.0, order: int = 5, graph: str = "rust") -> Result:
    """E3 candidate (M1a-2): level set, then a graph correction seeded with the level-set arrivals.

    T = min(T_levelset, earliest graph path from any level-set-labelled cell). Both are physical-path
    upper bounds when the level set is not early, so the minimum keeps the level set where it is better
    (open fuel, changing wind) and the exact graph geometry where it is better (gaps, obstacle corners).
    Cost = one level-set run + one label-setting run. graph: "rust" (kernel) or "python" (reference).
    """
    if graph == "rust":     # same algorithm as reference.propagate, tested to 1e-9 (tests/test_kernels.py)
        from .kernels import propagate_graph as propagate
    else:
        from .reference import propagate

    ls = propagate_levelset(f, points=points, inside=inside, t0=t0, t_stop=t_stop, r0_cells=r0_cells,
                            order=order)
    seed = np.where(np.isfinite(ls.arrival), ls.arrival, inf)
    g = propagate(f, radius=radius, inside=inside, t0=t0, t_stop=t_stop, seed=seed)
    arrival = np.minimum(ls.arrival, g.arrival)
    status = ls.status.copy()
    status[(status == NOT_REACHED) & np.isfinite(arrival)] = REACHED
    return Result(arrival, status)
