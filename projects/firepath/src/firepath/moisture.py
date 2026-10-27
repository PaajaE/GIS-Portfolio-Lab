"""Fuel-moisture inputs (METHOD.md, "Fuel moisture"). Fractions are percent of oven-dry mass.

FirePath approximation (not a published mapping): the dead 1-h / 10-h moistures are tied to gridMET's
100-h value by the fixed offsets of the Scott & Burgan (2005) dead-moisture scenarios (1-h = 100-h - 2,
10-h = 100-h - 1), so fm100 = 5, 8, 11, 14 reproduce scenarios D1-D4 exactly.
"""

from __future__ import annotations

from dataclasses import dataclass

# Scott & Burgan (2005) moisture scenarios (percent)
DEAD_SCENARIOS = {"D1": (3, 4, 5), "D2": (6, 7, 8), "D3": (9, 10, 11), "D4": (12, 13, 14)}
LIVE_SCENARIOS = {"L1": (30, 60), "L2": (60, 90), "L3": (90, 120), "L4": (120, 150)}  # (herb, woody)
DEAD_FLOOR = 2.0  # percent; keeps the offsets physical for very dry fm100


@dataclass(frozen=True)
class Moisture:
    d1: float
    d10: float
    d100: float
    live_herb: float
    live_woody: float


def from_gridmet(fm100: float, live: str = "L1", m: float = 1.0) -> Moisture:
    """Map a gridMET fm100 value (percent) and a pre-declared live scenario to model moistures.

    m: moisture multiplier applied to the three dead classes only (scenario variable, fixed at 1 in
    calibration). Live moistures are taken from the named Scott & Burgan live scenario.
    """
    if not 1.0 <= fm100 <= 40.0:
        raise ValueError(f"fm100 out of plausible range: {fm100}")
    if m <= 0:
        raise ValueError("m must be positive")
    d100 = fm100
    d10 = max(DEAD_FLOOR, d100 - 1.0)
    d1 = max(DEAD_FLOOR, d100 - 2.0)
    herb, woody = LIVE_SCENARIOS[live]
    return Moisture(d1 * m, d10 * m, d100 * m, float(herb), float(woody))


def cured_fraction(live_herb_pct: float) -> float:
    """Scott & Burgan (2005) dynamic models: share of live herbaceous load transferred to dead.

    Linear from fully cured (1.0) at <= 30 % to uncured (0.0) at >= 120 %; 1/3 cured at 90 %,
    1/2 at 75 %, 2/3 at 60 % (consistent with the IFTDSS moisture table).
    """
    return min(1.0, max(0.0, (120.0 - live_herb_pct) / 90.0))
