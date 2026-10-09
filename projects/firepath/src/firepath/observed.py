"""Observed-perimeter sequence audit and interval-censored arrival error (METHOD.md, "Observations").

Perimeters are never forced to be nested. Each cell's inclusion history decides its observed arrival
interval and a flag; inconsistent cells are reported and excluded from the primary metric.
"""

from __future__ import annotations

from math import inf

import numpy as np

# per-cell flags
CONSISTENT, INITIAL, NEVER, INCONSISTENT = 0, 1, 2, 3


def _dilate(mask: np.ndarray, k: int) -> np.ndarray:
    """Chebyshev (square) dilation by k cells, no SciPy needed."""
    out = mask.copy()
    for _ in range(k):
        m = out.copy()
        m[1:, :] |= out[:-1, :]
        m[:-1, :] |= out[1:, :]
        m[:, 1:] |= out[:, :-1]
        m[:, :-1] |= out[:, 1:]
        m[1:, 1:] |= out[:-1, :-1]
        m[:-1, :-1] |= out[1:, 1:]
        m[1:, :-1] |= out[:-1, 1:]
        m[:-1, 1:] |= out[1:, :-1]
        out = m
    return out


def audit_sequence(times, masks, jitter_cells: int = 1) -> dict:
    """Audit a time-ordered sequence of rasterized perimeters (cell-centre rule).

    times: observation (scan) times, must be strictly increasing (raises otherwise).
    masks: list of bool arrays, same shape.
    jitter_cells: a cell dropped at step k counts as boundary jitter if it lies within this many cells
        (Chebyshev) of perimeter k; otherwise as a retraction (a possible correction of earlier mapping).

    Returns per-step counts and per-cell arrays:
      first_in: index of the first perimeter containing the cell (-1 if never)
      flag: CONSISTENT (enters once, never leaves), INITIAL (in perimeter 0, never leaves),
            NEVER (in no perimeter), INCONSISTENT (leaves after entering, at any later step)
      lo, hi: observed arrival interval (lo, hi] in the same units as `times`; INITIAL -> (-inf, t0],
            NEVER -> (t_last, inf); INCONSISTENT -> interval of first entry (reported, not scored)
    """
    times = [float(t) for t in times]
    if len(times) != len(masks) or len(times) < 2:
        raise ValueError("need >= 2 perimeters with one time each")
    if any(b <= a for a, b in zip(times[:-1], times[1:])):
        raise ValueError("observation times must be strictly increasing")
    stack = np.stack([np.asarray(m, bool) for m in masks])
    steps = []
    for k in range(1, len(times)):
        new = stack[k] & ~stack[k - 1]
        removed = stack[k - 1] & ~stack[k]
        jitter = removed & _dilate(stack[k], jitter_cells)
        steps.append({
            "k": k, "t": times[k], "cells": int(stack[k].sum()), "new": int(new.sum()),
            "removed_jitter": int(jitter.sum()), "removed_retraction": int((removed & ~jitter).sum()),
        })
    ever = stack.any(0)
    first_in = np.where(ever, stack.argmax(0), -1)
    # leaves after entering: some later perimeter does not contain it
    k_idx = np.arange(len(times))[:, None, None]
    after_entry = (k_idx >= first_in[None]) & ever[None]
    left = (after_entry & ~stack).any(0)
    flag = np.full(first_in.shape, CONSISTENT, np.uint8)
    flag[~ever] = NEVER
    flag[ever & (first_in == 0) & ~left] = INITIAL
    flag[left] = INCONSISTENT
    t = np.array(times)
    lo = np.where(first_in > 0, t[np.maximum(first_in - 1, 0)], -inf)
    hi = np.where(ever, t[np.maximum(first_in, 0)], inf)
    lo = np.where(~ever, t[-1], lo)
    return {"steps": steps, "first_in": first_in, "flag": flag, "lo": lo, "hi": hi}


def interval_error(t_model, lo, hi):
    """Signed interval-censored arrival error: 0 if lo < t <= hi; negative (early) = t - lo if t <= lo;
    positive (late) = t - hi if t > hi. Unreached model cells (inf) give +inf (cap downstream)."""
    t = np.asarray(t_model, float)
    lo = np.asarray(lo, float)
    hi = np.asarray(hi, float)
    with np.errstate(invalid="ignore"):
        err = np.where(t <= lo, t - lo, np.where(t > hi, t - hi, 0.0))
    return err
