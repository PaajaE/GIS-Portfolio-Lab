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


def _hamiltonian(px, py, a, e, wx, wy):
    pw = px * wx + py * wy
    pp = -px * wy + py * wx
    return a * (e * pw + np.sqrt(pw * pw + (1.0 - e * e) * pp * pp))


def _dhamiltonian(px, py, a, e, wx, wy):
    """(|dH/dpx|, |dH/dpy|) of the support-function Hamiltonian."""
    pw = px * wx + py * wy
    pp = -px * wy + py * wx
    s = np.sqrt(pw * pw + (1.0 - e * e) * pp * pp)
    s = np.where(s > 0, s, 1.0)
    hw = a * (e + pw / s)
    hp = a * (1.0 - e * e) * pp / s
    return np.abs(hw * wx - hp * wy), np.abs(hw * wy + hp * wx)


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
        eps = 1e-6 * max(float(np.max(v1 * v1)), float(np.max(v5 * v5)), 1e-12) + 1e-99
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


def propagate_levelset(f: SpreadField, *, points=(), inside=None, t0=0.0, t_stop=inf,
                       r0_cells=2.0, cfl=0.4, first_order=False, dissipation="local",
                       order: int = 2) -> Result:
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

    radius = {5: 3}.get(order, 2)
    near_x = _near(barrier, 1, radius)
    near_y = _near(barrier, 0, radius)
    t = t_start
    while t < t_stop and np.any(~np.isfinite(arrival) & ~barrier):
        h, end = f.interval(t)
        a = f.r_head[h] / (1.0 + f.ecc[h])
        e = f.ecc[h]
        wx, wy = np.cos(f.theta[h]), np.sin(f.theta[h])
        # direction-specific LF bounds: half-extent of the unit-time spread set E along x and y,
        # measured from the focus: |a e w_i| + sqrt(a^2 w_i^2 + b^2 w_perp_i^2)  (<= R_head)
        b2 = (a * a) * (1.0 - e * e)
        ax = np.abs(a * e * wx) + np.sqrt(a * a * wx * wx + b2 * wy * wy)
        ay = np.abs(a * e * wy) + np.sqrt(a * a * wy * wy + b2 * wx * wx)
        if not np.isscalar(ax):
            g_ax, g_ay = np.pad(ax, 1, mode="edge"), np.pad(ay, 1, mode="edge")
            ax = np.maximum.reduce([g_ax[1:-1, 1:-1], g_ax[1:-1, :-2], g_ax[1:-1, 2:]])
            ay = np.maximum.reduce([g_ay[1:-1, 1:-1], g_ay[:-2, 1:-1], g_ay[2:, 1:-1]])
        ax = np.where(frozen, 0.0, ax)
        ay = np.where(frozen, 0.0, ay)
        amax = float((ax + ay).max())
        if amax == 0:
            break
        dt = cfl * dx / amax
        dt = min(dt, end - t, t_stop - t)
        if dt <= 0:
            t = end
            continue

        def rhs(ph):
            fm = _first_order_neumann(ph, dx, barrier)
            if first_order:
                xm, xp, ym, yp = fm
            else:
                hi = _weno5(ph, dx) if order == 5 else _eno2(ph, dx)
                # barrier faces: zero flux; high-order stencils touching a barrier fall back to first order
                xm, xp = (np.where(near_x, fm[i], hi[i]) for i in (0, 1))
                ym, yp = (np.where(near_y, fm[i], hi[i]) for i in (2, 3))
            px, py = 0.5 * (xm + xp), 0.5 * (ym + yp)
            ham = _hamiltonian(px, py, a, e, wx, wy)
            if dissipation == "local":  # |dH/dp| at the corners of the local gradient box (SLLF)
                cx = np.zeros_like(ph)
                cy = np.zeros_like(ph)
                for gx in (xm, xp):
                    for gy in (ym, yp):
                        hx, hy = _dhamiltonian(gx, gy, a, e, wx, wy)
                        cx = np.maximum(cx, hx)
                        cy = np.maximum(cy, hy)
                cx = np.minimum(cx, ax)
                cy = np.minimum(cy, ay)
            else:
                cx, cy = ax, ay
            diss = cx * 0.5 * (xp - xm) + cy * 0.5 * (yp - ym)
            out = -(ham - diss)
            out[frozen] = 0.0
            return out

        if order == 5:  # TVD RK3 (Shu & Osher)
            p1 = phi + dt * rhs(phi)
            p2 = 0.75 * phi + 0.25 * (p1 + dt * rhs(p1))
            new = phi / 3 + 2 / 3 * (p2 + dt * rhs(p2))
        else:           # Heun (TVD RK2)
            mid = phi + dt * rhs(phi)
            new = 0.5 * (phi + mid + dt * rhs(mid))
        cross = (phi > 0) & (new <= 0) & ~np.isfinite(arrival)
        frac = np.where(cross, phi / np.where(cross, phi - new, 1.0), 0.0)
        arrival[cross] = t + dt * frac[cross]
        phi = new
        t += dt

    status = np.where(barrier, BARRIER, NOT_REACHED).astype(np.uint8)
    status[init] = INITIAL
    reached = np.isfinite(arrival) & (arrival <= t_stop) & (status == NOT_REACHED)
    status[reached] = REACHED
    arrival[status == NOT_REACHED] = inf
    return Result(arrival, status)
