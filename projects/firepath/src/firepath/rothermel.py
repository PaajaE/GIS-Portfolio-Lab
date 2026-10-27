"""Wind/slope part of the spread-rate model (METHOD.md equation audit E2-E7) and the D3 parameterisation.

R0 (E1, no-wind no-slope ROS from the fuel table) is an input here; the full fuel table is M1a work still
open. English units inside (ft/min), SI at the boundary. Horizontal-plane vector combination; the
slope-plane projection (METHOD "Slope-plane geometry") is applied by the field builder, not here.

D3 (CRITICAL_REVIEW P0-3): the wind sensitivity is a multiplier `a_u` on the 20-ft wind speed, applied
before WAF, so it acts through the published phi_w and LB functions only. `wind_factor` (lambda) is the
separate *input-uncertainty* multiplier used in scenarios; the effective speed is lambda * a_u * U20.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, exp, hypot, sin

from .ellipse import MS_TO_MPH, eccentricity, lb_anderson_ms

FT_PER_M = 3.280839895
MS_TO_FTMIN = FT_PER_M * 60.0  # 196.85


def wind_coefficients(sigma: float) -> tuple[float, float, float]:
    """Rothermel (1972) C, B, E from characteristic SAV sigma (1/ft)."""
    c = 7.47 * exp(-0.133 * sigma**0.55)
    b = 0.02526 * sigma**0.54
    e = 0.715 * exp(-3.59e-4 * sigma)
    return c, b, e


def phi_wind(u_ftmin: float, sigma: float, beta_ratio: float) -> float:
    """phi_w = C U^B (beta/beta_op)^-E, U = midflame wind (ft/min)."""
    c, b, e = wind_coefficients(sigma)
    return c * u_ftmin**b * beta_ratio ** (-e)


def phi_wind_inverse(phi: float, sigma: float, beta_ratio: float) -> float:
    """Effective midflame wind (ft/min) that would produce phi alone (E5)."""
    c, b, e = wind_coefficients(sigma)
    return (phi * beta_ratio**e / c) ** (1.0 / b) if phi > 0 else 0.0


def phi_slope(beta: float, tan_slope: float) -> float:
    """phi_s = 5.275 beta^-0.3 tan^2(theta)."""
    return 5.275 * beta ** (-0.3) * tan_slope * tan_slope


@dataclass(frozen=True)
class Spread:
    r_head: float      # m/min
    ecc: float
    theta: float       # direction of max spread, rad (CCW from east)
    u_eff_ms: float    # effective midflame wind, m/s
    lb: float


def head_and_shape(r0_mmin: float, sigma: float, beta: float, beta_op: float, u20_ms: float, waf: float,
                   wind_to: float, tan_slope: float = 0.0, upslope: float = 0.0, *, k: float = 1.0,
                   a_u: float = 1.0, a_s: float = 1.0, wind_factor: float = 1.0, lb_model: str = "farsite",
                   ros_cap: str = "andrews2013") -> Spread:
    """Head ROS, eccentricity and direction for one cell (E2-E8).

    wind_to: direction the wind blows toward (rad, CCW from east). upslope: upslope direction.
    lb_model: "farsite" (Finney 1998 / Anderson 1983, effective midflame wind in m/s, cap 8) or
        "behaveplus" (1 + 0.25 U_E, U_E in mi/h; BehavePlus source code).
    ros_cap: "andrews2013" (R_head <= U_E), "rothermel1972" (U_E <= 0.9 I_R; needs I_R, not implemented
        here), or "none".
    """
    beta_ratio = beta / beta_op
    u_mid = wind_factor * a_u * u20_ms * waf * MS_TO_FTMIN
    pw = phi_wind(u_mid, sigma, beta_ratio) if u_mid > 0 else 0.0
    ps = a_s * phi_slope(beta, tan_slope)
    vx = pw * cos(wind_to) + ps * cos(upslope)
    vy = pw * sin(wind_to) + ps * sin(upslope)
    phi_e = hypot(vx, vy)
    theta = atan2(vy, vx) if phi_e > 0 else (upslope if ps > 0 else 0.0)
    u_e_ftmin = phi_wind_inverse(phi_e, sigma, beta_ratio)
    r_head = k * r0_mmin * (1.0 + phi_e)
    if ros_cap == "andrews2013":
        u_e_mmin = u_e_ftmin / FT_PER_M
        if u_e_mmin > 0:
            r_head = min(r_head, max(u_e_mmin, k * r0_mmin))
    elif ros_cap != "none":
        raise ValueError(ros_cap)
    u_e_ms = u_e_ftmin / MS_TO_FTMIN
    if lb_model == "farsite":
        lb = float(lb_anderson_ms(u_e_ms))
    elif lb_model == "behaveplus":
        lb = 1.0 + 0.25 * u_e_ms * MS_TO_MPH
    else:
        raise ValueError(lb_model)
    return Spread(r_head, float(eccentricity(lb)), theta, u_e_ms, lb)
