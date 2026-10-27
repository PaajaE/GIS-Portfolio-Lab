"""Elliptical fire shape (METHOD.md, equation audit rows E5–E6).

Published relations only; units are explicit in every name (M1A_RESULTS.md, D2):
* FARSITE form (Finney 1998, RMRS-RP-4: Anderson 1983 minus 0.397 so that LB(0) = 1, single ellipse,
  U = effective midflame wind in m/s, capped at 8)  -> lb_anderson_ms (default)
* BehavePlus surface form 1 + 0.25 U_E (U_E in mi/h; BehavePlus source code)  -> lb_rothermel1991_mph
  (sensitivity; the name is kept for compatibility, the attribution to Rothermel 1991 was not confirmed).
"""

from __future__ import annotations

import numpy as np

MS_TO_MPH = 3600.0 / 1609.344  # 2.236936...


def lb_anderson_mph(u_mph):
    """Anderson (1983)-type relation in the form with wind in mi/h, capped at 8.

    Coefficients 0.1147 / 0.0692 per mi/h are the m/s coefficients 0.2566 / 0.1548 divided by
    2.237 (see test_ellipse.py). Which wind (midflame vs effective) it takes is part of decision P0-2.
    """
    u = np.asarray(u_mph, dtype=float)
    return np.minimum(8.0, 0.936 * np.exp(0.1147 * u) + 0.461 * np.exp(-0.0692 * u) - 0.397)


def lb_anderson_ms(u_ms):
    """The same relation written with wind in m/s (coefficients 0.2566 / 0.1548), capped at 8."""
    u = np.asarray(u_ms, dtype=float)
    return np.minimum(8.0, 0.936 * np.exp(0.2566 * u) + 0.461 * np.exp(-0.1548 * u) - 0.397)


def lb_rothermel1991_mph(u_mph):
    """LB = 1 + 0.25 U_E (U_E = effective wind at the head, mi/h): BehavePlus surface relation (source code).
    Its attribution to Rothermel (1991) was not confirmed: that report's cited equation is a crown-fire
    relation in 20-ft wind with coefficient 0.125."""
    return 1.0 + 0.25 * np.asarray(u_mph, dtype=float)


def eccentricity(lb):
    lb = np.asarray(lb, dtype=float)
    return np.sqrt(np.maximum(lb * lb - 1.0, 0.0)) / lb


def ray_factor(psi, ecc):
    """Distance from the rear focus to the ellipse along angle psi from the major axis, as a fraction of
    the head distance: (1 - e) / (1 - e cos psi). Head (psi=0) -> 1, back (psi=pi) -> (1-e)/(1+e)."""
    return (1.0 - ecc) / (1.0 - ecc * np.cos(psi))
