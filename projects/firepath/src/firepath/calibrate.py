"""M3 calibration objective (PLAN §8): arrival-time interval error, equal weight per fire.

Per fire: Mode A from the first usable perimeter over the evaluation window (run.setup). Per cell the
interval error is 0 inside the observed arrival interval, else the distance to it, capped at 48 h (never
reached = cap). Scored cells: observed to burn in the window (CONSISTENT) or burned by the model by the
last scan although never observed (NEVER); INITIAL and INCONSISTENT cells and cells whose observed
interval is a masked interval (validation/masked_intervals.json) are excluded. The fire score is the mean
absolute error in hours; the objective is the mean over fires. Secondary (reported, not optimised):
growth-only Dice per step.

Parameter vectors (log space for the search, see BOUNDS):
  model: k, a_u, a_s, g      B0: c      B1: c, b
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from .ellipse import lb_anderson_ms
from .field import Params, hour
from .harvest import PROJECT
from .observed import CONSISTENT, NEVER, interval_error
from .reference import SpreadField
from .run import CAP_MIN, setup

# PLAN §8 / METHOD "Free parameters": bounds of the search (all searched in log space)
BOUNDS = {"model": {"k": (0.2, 5.0), "a_u": (0.5, 2.0), "a_s": (0.3, 3.0), "g": (0.3, 3.0)},
          "B0": {"c": (0.05, 20.0)},
          "B1": {"c": (0.02, 10.0), "b": (0.0005, 1.0)}}


@dataclass
class Case:
    fire: str
    S: dict
    scored_obs: np.ndarray      # CONSISTENT and not in a masked interval
    never: np.ndarray           # NEVER (scored only where the model burns them)


def _masked_rel(fire: str, t0: float) -> list[tuple[float, float]]:
    d = json.loads((PROJECT / "validation" / "masked_intervals.json").read_text())["fires"].get(fire, {})
    out = []
    for m in d.get("masked", []):
        a, b = (datetime.strptime(x, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp() for x in
                m["interval_utc"])
        out.append(((a - t0) / 60.0, (b - t0) / 60.0))
    return out


def load_case(fire: str, cell: int = 90) -> Case:
    S = setup(fire, cell)
    flag, lo, hi = S["audit"]["flag"], S["lo"], S["hi"]
    masked = np.zeros(flag.shape, bool)
    for a, b in _masked_rel(fire, S["t0"]):
        # observed interval (lo, hi] equals the masked scan interval (scan times are minutes apart at most)
        masked |= (np.abs(lo - a) < 1.0) & (np.abs(hi - b) < 1.0)
    return Case(fire, S, (flag == CONSISTENT) & ~masked, flag == NEVER)


def params_of(kind: str, x) -> dict:
    return dict(zip(BOUNDS[kind], (float(v) for v in x)))


def field_for(case: Case, kind: str, theta: dict) -> SpreadField:
    S, st = case.S, case.S["st"]
    H = len(S["hrs"])
    r, e, th = (np.zeros((H, *st.burnable.shape)) for _ in range(3))
    for j, h in enumerate(S["hrs"]):
        u, v = S["u"][h], S["v"][h]
        if kind == "model":
            r[j], e[j], th[j] = hour(st, u, v, Params(**theta))
        elif kind == "B0":
            r[j] = np.where(st.burnable, theta["c"], 0.0)
        else:                       # B1: uniform fuel, no slope, ellipse from U10 (run.fields)
            s10 = np.hypot(u, v)
            r[j] = np.where(st.burnable, theta["c"] * (1 + theta["b"] * s10 ** 1.5), 0.0)
            e[j] = np.where(st.burnable, np.sqrt(1 - 1 / lb_anderson_ms(s10 / 1.15 * 0.4) ** 2), 0.0)
            th[j] = np.arctan2(v, u)
    terrain = {"tan_slope": S["tan_s"], "upslope": S["up"]} if kind == "model" else {}
    return SpreadField(S["t_change"], r, e, th, st.burnable, S["cell"], **terrain)


def score(case: Case, arrival: np.ndarray) -> dict:
    S = case.S
    rel, masks = S["rel"], S["masks_w"]
    burned = np.isfinite(arrival) & (arrival <= rel[-1])
    scored = case.scored_obs | (case.never & burned)
    err = np.clip(interval_error(arrival[scored], S["lo"][scored], S["hi"][scored]), -CAP_MIN, CAP_MIN) / 60.0
    out = S["st"].burnable
    dice = []
    for k in range(1, len(rel)):
        obs = masks[k] & ~masks[k - 1] & out
        mod = np.isfinite(arrival) & (arrival > rel[k - 1]) & (arrival <= rel[k]) & ~masks[k - 1] & out
        dice.append(float(2 * (obs & mod).sum() / max(obs.sum() + mod.sum(), 1)))
    return {"primary_h": float(np.mean(np.abs(err))), "signed_h": float(np.mean(err)), "n": int(err.size),
            "growth_dice": dice}


def evaluate(case: Case, kind: str, theta: dict, scheme: str = "HY") -> dict:
    from .run import run_scheme

    f = field_for(case, kind, theta)
    res = run_scheme(scheme, f, case.S["inside"], 0.0, case.S["t_stop"])
    return score(case, res.arrival)
