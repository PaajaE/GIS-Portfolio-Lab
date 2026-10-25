"""Scott & Burgan (2005) 40 fuel models and Rothermel's no-wind, no-slope spread rate (METHOD E1, E9, E10).

The parameter table is transcribed from GTR-153 Table 7 (Scott & Burgan 2005, RMRS-GTR-153, p. 18; text
extracted from the published PDF, sha256 prefix 0013d052f867c6de). Loads in tons/acre, SAV in 1/ft,
depth in ft, dead extinction moisture in percent, heat content in BTU/lb (live and dead). 9999 marks an
empty class. Fixed particle constants as in Rothermel (1972) / Albini (1976): particle density 32 lb/ft³,
total mineral content 0.0555, effective mineral content 0.010; 10-h SAV 109 and 100-h SAV 30 1/ft.

The multi-class fuel bed follows Rothermel (1972) with Albini's (1976) weighting: surface-area weights
within and between the dead and live categories, and size-class weights (SAV bins) for the net loads.
English units inside; `r0_mmin` returns m/min.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp

from .moisture import Moisture, cured_fraction

# code: (name, w1h, w10h, w100h, w_live_herb, w_live_woody, dynamic, sav1h, sav_herb, sav_woody,
#        depth_ft, mx_dead_pct, heat_btu_lb)   -- GTR-153 Table 7
SB40 = {
    101: ("GR1", 0.10, 0.00, 0.00, 0.30, 0.00, True, 2200, 2000, 9999, 0.4, 15, 8000),
    102: ("GR2", 0.10, 0.00, 0.00, 1.00, 0.00, True, 2000, 1800, 9999, 1.0, 15, 8000),
    103: ("GR3", 0.10, 0.40, 0.00, 1.50, 0.00, True, 1500, 1300, 9999, 2.0, 30, 8000),
    104: ("GR4", 0.25, 0.00, 0.00, 1.90, 0.00, True, 2000, 1800, 9999, 2.0, 15, 8000),
    105: ("GR5", 0.40, 0.00, 0.00, 2.50, 0.00, True, 1800, 1600, 9999, 1.5, 40, 8000),
    106: ("GR6", 0.10, 0.00, 0.00, 3.40, 0.00, True, 2200, 2000, 9999, 1.5, 40, 9000),
    107: ("GR7", 1.00, 0.00, 0.00, 5.40, 0.00, True, 2000, 1800, 9999, 3.0, 15, 8000),
    108: ("GR8", 0.50, 1.00, 0.00, 7.30, 0.00, True, 1500, 1300, 9999, 4.0, 30, 8000),
    109: ("GR9", 1.00, 1.00, 0.00, 9.00, 0.00, True, 1800, 1600, 9999, 5.0, 40, 8000),
    121: ("GS1", 0.20, 0.00, 0.00, 0.50, 0.65, True, 2000, 1800, 1800, 0.9, 15, 8000),
    122: ("GS2", 0.50, 0.50, 0.00, 0.60, 1.00, True, 2000, 1800, 1800, 1.5, 15, 8000),
    123: ("GS3", 0.30, 0.25, 0.00, 1.45, 1.25, True, 1800, 1600, 1600, 1.8, 40, 8000),
    124: ("GS4", 1.90, 0.30, 0.10, 3.40, 7.10, True, 1800, 1600, 1600, 2.1, 40, 8000),
    141: ("SH1", 0.25, 0.25, 0.00, 0.15, 1.30, True, 2000, 1800, 1600, 1.0, 15, 8000),
    142: ("SH2", 1.35, 2.40, 0.75, 0.00, 3.85, False, 2000, 9999, 1600, 1.0, 15, 8000),
    143: ("SH3", 0.45, 3.00, 0.00, 0.00, 6.20, False, 1600, 9999, 1400, 2.4, 40, 8000),
    144: ("SH4", 0.85, 1.15, 0.20, 0.00, 2.55, False, 2000, 1800, 1600, 3.0, 30, 8000),
    145: ("SH5", 3.60, 2.10, 0.00, 0.00, 2.90, False, 750, 9999, 1600, 6.0, 15, 8000),
    146: ("SH6", 2.90, 1.45, 0.00, 0.00, 1.40, False, 750, 9999, 1600, 2.0, 30, 8000),
    147: ("SH7", 3.50, 5.30, 2.20, 0.00, 3.40, False, 750, 9999, 1600, 6.0, 15, 8000),
    148: ("SH8", 2.05, 3.40, 0.85, 0.00, 4.35, False, 750, 9999, 1600, 3.0, 40, 8000),
    149: ("SH9", 4.50, 2.45, 0.00, 1.55, 7.00, True, 750, 1800, 1500, 4.4, 40, 8000),
    161: ("TU1", 0.20, 0.90, 1.50, 0.20, 0.90, True, 2000, 1800, 1600, 0.6, 20, 8000),
    162: ("TU2", 0.95, 1.80, 1.25, 0.00, 0.20, False, 2000, 9999, 1600, 1.0, 30, 8000),
    163: ("TU3", 1.10, 0.15, 0.25, 0.65, 1.10, True, 1800, 1600, 1400, 1.3, 30, 8000),
    164: ("TU4", 4.50, 0.00, 0.00, 0.00, 2.00, False, 2300, 9999, 2000, 0.5, 12, 8000),
    165: ("TU5", 4.00, 4.00, 3.00, 0.00, 3.00, False, 1500, 9999, 750, 1.0, 25, 8000),
    181: ("TL1", 1.00, 2.20, 3.60, 0.00, 0.00, False, 2000, 9999, 9999, 0.2, 30, 8000),
    182: ("TL2", 1.40, 2.30, 2.20, 0.00, 0.00, False, 2000, 9999, 9999, 0.2, 25, 8000),
    183: ("TL3", 0.50, 2.20, 2.80, 0.00, 0.00, False, 2000, 9999, 9999, 0.3, 20, 8000),
    184: ("TL4", 0.50, 1.50, 4.20, 0.00, 0.00, False, 2000, 9999, 9999, 0.4, 25, 8000),
    185: ("TL5", 1.15, 2.50, 4.40, 0.00, 0.00, False, 2000, 9999, 1600, 0.6, 25, 8000),
    186: ("TL6", 2.40, 1.20, 1.20, 0.00, 0.00, False, 2000, 9999, 9999, 0.3, 25, 8000),
    187: ("TL7", 0.30, 1.40, 8.10, 0.00, 0.00, False, 2000, 9999, 9999, 0.4, 25, 8000),
    188: ("TL8", 5.80, 1.40, 1.10, 0.00, 0.00, False, 1800, 9999, 9999, 0.3, 35, 8000),
    189: ("TL9", 6.65, 3.30, 4.15, 0.00, 0.00, False, 1800, 9999, 1600, 0.6, 35, 8000),
    201: ("SB1", 1.50, 3.00, 11.00, 0.00, 0.00, False, 2000, 9999, 9999, 1.0, 25, 8000),
    202: ("SB2", 4.50, 4.25, 4.00, 0.00, 0.00, False, 2000, 9999, 9999, 1.0, 25, 8000),
    203: ("SB3", 5.50, 2.75, 3.00, 0.00, 0.00, False, 2000, 9999, 9999, 1.2, 25, 8000),
    204: ("SB4", 5.25, 3.50, 5.25, 0.00, 0.00, False, 2000, 9999, 9999, 2.7, 25, 8000),
}
NONBURNABLE = (91, 92, 93, 98, 99)
TONS_AC_TO_LB_FT2 = 2000.0 / 43560.0
RHO_P, S_T, S_E = 32.0, 0.0555, 0.010
SAV_10H, SAV_100H = 109.0, 30.0
FT_PER_M = 3.280839895


@dataclass(frozen=True)
class Particle:
    load: float        # lb/ft²
    sav: float         # 1/ft
    moisture: float    # fraction
    heat: float        # BTU/lb


@dataclass(frozen=True)
class FuelBed:
    r0_ftmin: float    # no-wind, no-slope ROS (ft/min)
    sigma: float       # characteristic SAV (1/ft)
    beta: float        # packing ratio
    beta_op: float
    ir: float          # reaction intensity (BTU/ft²/min)
    mx_live: float     # live extinction moisture (fraction)

    @property
    def r0_mmin(self) -> float:
        return self.r0_ftmin / FT_PER_M


def particles(code: int, m: Moisture) -> tuple[list[Particle], list[Particle], float, float]:
    """Dead and live particles for a fuel model and moisture, with the dynamic herbaceous transfer (E10)."""
    (_, w1, w10, w100, wh, ww, dynamic, s1, sh, sw, depth, mx, heat) = SB40[code]
    k = TONS_AC_TO_LB_FT2
    cured = cured_fraction(m.live_herb) if dynamic and wh > 0 else 0.0
    dead = [Particle(w1 * k, s1, m.d1 / 100, heat), Particle(w10 * k, SAV_10H, m.d10 / 100, heat),
            Particle(w100 * k, SAV_100H, m.d100 / 100, heat), Particle(wh * cured * k, sh, m.d1 / 100, heat)]
    live = [Particle(wh * (1 - cured) * k, sh, m.live_herb / 100, heat),
            Particle(ww * k, sw, m.live_woody / 100, heat)]
    return [p for p in dead if p.load > 0], [p for p in live if p.load > 0], depth, mx / 100


def _size_class(sav: float) -> int:
    for k, lo in enumerate((1200.0, 192.0, 96.0, 48.0, 16.0)):
        if sav >= lo:
            return k
    return 5


def fuel_bed(code: int, m: Moisture) -> FuelBed:
    """Rothermel (1972) R0 for a Scott & Burgan model under moisture `m` (E1, E9, E10)."""
    dead, live, depth, mx_dead = particles(code, m)
    cats = [c for c in (dead, live) if c]
    area = [[p.load * p.sav / RHO_P for p in c] for c in cats]
    a_cat = [sum(a) for a in area]
    a_tot = sum(a_cat)
    f_i = [[a / ac for a in al] for al, ac in zip(area, a_cat)]
    f_c = [ac / a_tot for ac in a_cat]
    sig_c = [sum(f * p.sav for f, p in zip(fi, c)) for fi, c in zip(f_i, cats)]
    sigma = sum(f * s for f, s in zip(f_c, sig_c))
    w_tot = sum(p.load for c in cats for p in c)
    rho_b = w_tot / depth
    beta = rho_b / RHO_P
    beta_op = 3.348 * sigma ** -0.8189
    ratio = beta / beta_op
    a_exp = 133.0 * sigma ** -0.7913
    gamma_max = sigma ** 1.5 / (495.0 + 0.0594 * sigma ** 1.5)
    gamma = gamma_max * ratio ** a_exp * exp(a_exp * (1.0 - ratio))
    xi = exp((0.792 + 0.681 * sigma ** 0.5) * (ratio * beta_op + 0.1)) / (192.0 + 0.2595 * sigma)

    # live extinction moisture (E9): Rothermel 1972 / Albini 1976
    mx_live = mx_dead
    if live:
        wd = sum(p.load * exp(-138.0 / p.sav) for p in dead)
        wl = sum(p.load * exp(-500.0 / p.sav) for p in live)
        mf_dead = sum(p.load * exp(-138.0 / p.sav) * p.moisture for p in dead) / wd if wd > 0 else 0.0
        mx_live = max(mx_dead, 2.9 * (wd / wl) * (1.0 - mf_dead / mx_dead) - 0.226) if wl > 0 else mx_dead

    ir = 0.0
    for c, fi, is_dead in zip(cats, f_i, [cats[0] is dead] + [False]):
        # size-class weights g_i: sum of f_i of particles in the same SAV class (Albini 1976)
        cls = [_size_class(p.sav) for p in c]
        g = [sum(f for f, k in zip(fi, cls) if k == ci) for ci in cls]
        w_net = sum(gi * p.load * (1.0 - S_T) for gi, p in zip(g, c))
        mc = sum(f * p.moisture for f, p in zip(fi, c))
        mxc = mx_dead if is_dead else mx_live
        r = min(mc / mxc, 1.0)
        eta_m = 0.0 if r >= 1.0 else max(0.0, 1.0 - 2.59 * r + 5.11 * r ** 2 - 3.52 * r ** 3)  # exact 0 at extinction
        eta_s = min(0.174 * S_E ** -0.19, 1.0)
        h = sum(f * p.heat for f, p in zip(fi, c))
        ir += gamma * w_net * h * eta_m * eta_s
    heat_sink = rho_b * sum(fc * sum(f * exp(-138.0 / p.sav) * (250.0 + 1116.0 * p.moisture)
                                     for f, p in zip(fi, c)) for fc, fi, c in zip(f_c, f_i, cats))
    r0 = ir * xi / heat_sink if heat_sink > 0 else 0.0
    return FuelBed(r0, sigma, beta, beta_op, ir, mx_live)
