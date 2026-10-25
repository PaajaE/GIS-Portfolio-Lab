"""Spread-field builder: fuels, terrain and hourly wind -> per-hour head ROS, eccentricity, direction
(METHOD E1–E12, "Slope-plane geometry"; vectorised over cells).

Per cell and hour, in slope-plane coordinates (e1 = upslope, e2 = contour; slopeplane.py):
  midflame wind  U_mid = lambda * a_u * U20 * WAF,  U20 = U10 / 1.15 (E12),
  the horizontal wind vector is projected orthogonally onto the slope plane (its magnitude shrinks by
  the projection; as in pyretechnics), giving speed U_mid*m and direction w_w;
  phi_w = C (U_mid m)^B (beta/beta_op)^-E (E2),  phi_s = a_s 5.275 beta^-0.3 tan^2 s (E3), along e1;
  phi_E = phi_w w_w + phi_s e1 (E4);  U_E = phi_w^-1(|phi_E|) (E5);
  R_head = k R0 (1 + |phi_E|), capped at max(U_E, k R0) (E6);  LB(U_E) FARSITE, cap 8 (E7).
theta is stored as the horizontal image of the slope-plane direction of phi_E (SpreadField convention).

WAF (E11, Andrews 2012, GTR-266 eqs. 1, 2, 9, 10): crown fill f = CR * CC/3 with CR = 1 (FARSITE
convention, GTR-266 p. 10); sheltered if f > 0.05, WAF = 0.555 / (sqrt(f H_c) ln((20 + 0.36 H_c)/(0.13 H_c))),
H_c canopy height (ft); otherwise unsheltered WAF = 1.83 / ln((20 + 0.36 H)/(0.13 H)), H fuel-bed depth (ft).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .ellipse import lb_anderson_ms
from .fuels import NONBURNABLE, SB40, fuel_bed
from .moisture import Moisture
from .rothermel import FT_PER_M, MS_TO_FTMIN
from .slopeplane import frame, vec_to_horizontal

U10_TO_U20 = 1.0 / 1.15


@dataclass(frozen=True)
class Params:
    k: float = 1.0
    a_u: float = 1.0
    a_s: float = 1.0
    wind_factor: float = 1.0      # lambda: input-uncertainty scenario multiplier, 1 in calibration


def waf(fuel: np.ndarray, cc_pct: np.ndarray, ch_m: np.ndarray, crown_ratio: float = 1.0) -> np.ndarray:
    depth = np.zeros(fuel.shape)
    for code, row in SB40.items():
        depth[fuel == code] = row[10]
    unsheltered = np.where(depth > 0, 1.83 / np.log((20 + 0.36 * np.maximum(depth, 1e-6))
                                                    / (0.13 * np.maximum(depth, 1e-6))), 0.0)
    f = crown_ratio * (cc_pct / 100.0) / 3.0
    hc = ch_m * FT_PER_M
    with np.errstate(divide="ignore", invalid="ignore"):
        sheltered = 0.555 / (np.sqrt(f * hc) * np.log((20 + 0.36 * hc) / (0.13 * hc)))
    use_sheltered = (f > 0.05) & (hc > 0)
    return np.where(use_sheltered, sheltered, unsheltered)


def fuel_tables(fuel: np.ndarray, m: Moisture):
    """Per-cell R0 (m/min), sigma, beta, beta_op from one Rothermel evaluation per fuel code."""
    r0, sig, beta, bop = (np.zeros(fuel.shape) for _ in range(4))
    for code in np.unique(fuel):
        if int(code) not in SB40:
            continue
        b = fuel_bed(int(code), m)
        sel = fuel == code
        r0[sel], sig[sel], beta[sel], bop[sel] = b.r0_mmin, b.sigma, b.beta, b.beta_op
    burnable = (r0 > 0) & ~np.isin(fuel, NONBURNABLE)
    return r0, sig, beta, bop, burnable


@dataclass
class Static:
    """Per-fire, per-moisture static part of the field (computed once)."""
    r0: np.ndarray
    sigma: np.ndarray
    beta: np.ndarray
    beta_op: np.ndarray
    burnable: np.ndarray
    waf: np.ndarray
    tan_slope: np.ndarray
    upslope: np.ndarray

    @classmethod
    def build(cls, fuel, cc, ch, tan_slope, upslope, m: Moisture):
        r0, sig, beta, bop, burnable = fuel_tables(fuel, m)
        return cls(r0, sig, beta, bop, burnable, waf(fuel, cc, ch), tan_slope, upslope)


def hour(st: Static, u10: np.ndarray, v10: np.ndarray, p: Params):
    """(r_head m/min, ecc, theta rad) for one hour; u10, v10 = UTM-grid-relative 10 m wind (m/s) per cell."""
    b = st.burnable
    out_r = np.zeros(b.shape)
    out_e = np.zeros(b.shape)
    out_t = np.zeros(b.shape)
    sig, beta, bop = st.sigma[b], st.beta[b], st.beta_op[b]
    ratio = beta / bop
    c = 7.47 * np.exp(-0.133 * sig ** 0.55)
    bb = 0.02526 * sig ** 0.54
    ee = 0.715 * np.exp(-3.59e-4 * sig)
    cs, ux, uy = frame(st.tan_slope[b], st.upslope[b])
    # horizontal wind -> orthogonal projection onto the slope plane, in slope coordinates
    u, v = u10[b], v10[b]
    w1 = cs * (u * ux + v * uy)
    w2 = -u * uy + v * ux
    speed_plane = np.hypot(w1, w2)                                  # m/s at 10 m, in the plane
    u_mid = p.wind_factor * p.a_u * U10_TO_U20 * speed_plane * st.waf[b] * MS_TO_FTMIN
    with np.errstate(divide="ignore", invalid="ignore"):
        phi_w = np.where(u_mid > 0, c * u_mid ** bb * ratio ** (-ee), 0.0)
        dw1, dw2 = np.where(speed_plane > 0, w1 / speed_plane, 0.0), np.where(speed_plane > 0, w2 / speed_plane, 0.0)
    phi_s = p.a_s * 5.275 * beta ** (-0.3) * st.tan_slope[b] ** 2
    e1, e2 = phi_w * dw1 + phi_s, phi_w * dw2
    phi_e = np.hypot(e1, e2)
    with np.errstate(divide="ignore", invalid="ignore"):
        u_e = np.where(phi_e > 0, (phi_e * ratio ** ee / c) ** (1.0 / bb), 0.0)   # ft/min
    r0 = p.k * st.r0[b]
    r_head = r0 * (1.0 + phi_e)
    cap = np.maximum(u_e / FT_PER_M, r0)                                         # E6 (andrews2013)
    r_head = np.where(u_e > 0, np.minimum(r_head, cap), r_head)
    lb = lb_anderson_ms(u_e / MS_TO_FTMIN)
    ecc = np.sqrt(1.0 - 1.0 / lb ** 2)
    # direction: slope-plane (e1, e2) -> horizontal image; upslope when phi_E = 0 (then ecc = 0 anyway)
    d1 = np.where(phi_e > 0, e1, 1.0)
    d2 = np.where(phi_e > 0, e2, 0.0)
    hx, hy = vec_to_horizontal(d1, d2, cs, ux, uy)
    out_r[b], out_e[b], out_t[b] = r_head, ecc, np.arctan2(hy, hx)
    return out_r, out_e, out_t
