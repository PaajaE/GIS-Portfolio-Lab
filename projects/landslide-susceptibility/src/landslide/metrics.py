"""Evaluation metrics for ranked susceptibility (PLAN §8), with case weights so that block-bootstrap resamples
and prevalence-weighted negative samples use the same code.

All functions take a score (higher = more susceptible), a 0/1 label and non-negative weights. Ties in the
score count one half (Mann-Whitney). `Ranked` sorts once, so a bootstrap only re-weights (O(n) per resample).
"""

from __future__ import annotations

import numpy as np


class Ranked:
    """Score ranks (dense, ties share a rank) and an optional stratum per row."""

    def __init__(self, score: np.ndarray, y: np.ndarray, strata: np.ndarray | None = None):
        self.y = np.asarray(y).astype(np.float64)
        _, self.rank = np.unique(np.asarray(score, np.float64), return_inverse=True)
        self.n_rank = int(self.rank.max()) + 1
        if strata is None:
            strata = np.zeros(len(self.y), np.int64)
        self.strata_values, self.stratum = np.unique(strata, return_inverse=True)
        self.order_desc = np.argsort(-np.asarray(score, np.float64), kind="stable")

    def auc_by_stratum(self, w: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Per-stratum AUC (NaN without both classes), positive weight and negative weight."""
        w = np.ones(len(self.y)) if w is None else np.asarray(w, np.float64)
        s = len(self.strata_values)
        key = self.stratum * self.n_rank + self.rank
        wp = np.bincount(key, w * self.y, s * self.n_rank).reshape(s, self.n_rank)
        wn = np.bincount(key, w * (1 - self.y), s * self.n_rank).reshape(s, self.n_rank)
        neg_below = np.cumsum(wn, axis=1) - wn  # negative weight strictly below each rank
        tp, tn = wp.sum(1), wn.sum(1)
        num = (wp * (neg_below + 0.5 * wn)).sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            auc = np.where((tp > 0) & (tn > 0), num / (tp * tn), np.nan)
        return auc, tp, tn

    def auc(self, w=None) -> float:
        """Pooled AUC (ignores strata)."""
        w = np.ones(len(self.y)) if w is None else np.asarray(w, np.float64)
        wp = np.bincount(self.rank, w * self.y, self.n_rank)
        wn = np.bincount(self.rank, w * (1 - self.y), self.n_rank)
        tp, tn = wp.sum(), wn.sum()
        if tp == 0 or tn == 0:
            return np.nan
        return float((wp * (np.cumsum(wn) - wn + 0.5 * wn)).sum() / (tp * tn))

    def stratified_auc(self, w=None) -> float:
        """Average of per-stratum AUCs weighted by each stratum's positive weight."""
        auc, tp, _ = self.auc_by_stratum(w)
        ok = np.isfinite(auc)
        return float(np.average(auc[ok], weights=tp[ok])) if ok.any() and tp[ok].sum() > 0 else np.nan

    def average_precision(self, w=None) -> float:
        """Weighted average precision (area under the precision-recall step curve), ties grouped."""
        w = np.ones(len(self.y)) if w is None else np.asarray(w, np.float64)
        wp = np.bincount(self.rank, w * self.y, self.n_rank)[::-1]
        wa = np.bincount(self.rank, w, self.n_rank)[::-1]
        tp = np.cumsum(wp)
        if tp[-1] == 0:
            return np.nan
        prec = tp / np.maximum(np.cumsum(wa), 1e-300)
        return float((prec * wp).sum() / tp[-1])

    def capture(self, hits: np.ndarray, area: np.ndarray, ks, w=None) -> np.ndarray:
        """Share of `hits` (e.g. mapped initiations) inside the top-k share of `area`, by descending score.

        Rows are taken whole in score order; the value at k is linearly interpolated between rows.
        """
        w = np.ones(len(self.y)) if w is None else np.asarray(w, np.float64)
        o = self.order_desc
        a = np.cumsum((area * w)[o])
        h = np.cumsum((hits * w)[o])
        if a[-1] == 0 or h[-1] == 0:
            return np.full(len(ks), np.nan)
        return np.interp(np.asarray(ks, np.float64), np.r_[0, a / a[-1]], np.r_[0, h / h[-1]])


def brier(p: np.ndarray, y: np.ndarray, w=None) -> float:
    w = np.ones(len(y)) if w is None else w
    return float(np.average((p - y) ** 2, weights=w))


def reliability(p: np.ndarray, y: np.ndarray, bins: int = 10) -> list[dict]:
    """Observed vs mean predicted per equal-count bin of p."""
    edges = np.unique(np.quantile(p, np.linspace(0, 1, bins + 1)))
    b = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, len(edges) - 2)
    return [{"p_mean": float(p[b == i].mean()), "observed": float(y[b == i].mean()), "n": int((b == i).sum())}
            for i in range(len(edges) - 1) if (b == i).any()]


def block_bootstrap(groups: np.ndarray, stat, n: int, seed: int) -> np.ndarray:
    """Resample whole groups with replacement; `stat(weights)` -> 1-D array. Returns (n, k) replicates."""
    ug, gi = np.unique(groups, return_inverse=True)
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        mult = np.bincount(rng.integers(0, len(ug), len(ug)), minlength=len(ug)).astype(np.float64)
        out.append(np.atleast_1d(stat(mult[gi])))
    return np.asarray(out, np.float64)


def ci(reps: np.ndarray, level: float = 0.95) -> np.ndarray:
    """Percentile interval per column, ignoring NaN replicates; shape (k, 2)."""
    a = (1 - level) / 2
    if np.isnan(reps).all(axis=0).any():  # columns without a defined value (e.g. capture without area)
        out = np.full((reps.shape[1], 2), np.nan)
        ok = ~np.isnan(reps).all(axis=0)
        out[ok] = np.nanquantile(reps[:, ok], [a, 1 - a], axis=0).T
        return out
    return np.nanquantile(reps, [a, 1 - a], axis=0).T
