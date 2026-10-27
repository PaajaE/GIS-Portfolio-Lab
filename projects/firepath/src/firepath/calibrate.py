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
from .field import Params
from .harvest import PROJECT
from .kernels import field_hours
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
    u: np.ndarray = None        # wind for the run's hours (H, nr, nc) float64, shared by all evaluations
    v: np.ndarray = None


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
    u = np.ascontiguousarray(S["u"][S["hrs"]], dtype=np.float64)
    v = np.ascontiguousarray(S["v"][S["hrs"]], dtype=np.float64)
    return Case(fire, S, (flag == CONSISTENT) & ~masked, flag == NEVER, u, v)


def params_of(kind: str, x) -> dict:
    return dict(zip(BOUNDS[kind], (float(v) for v in x)))


def field_for(case: Case, kind: str, theta: dict) -> SpreadField:
    S, st = case.S, case.S["st"]
    H = len(S["hrs"])
    if kind == "model":                 # Rust builder, same as field.hour (tests/test_kernels.py)
        r, e, th = field_hours(st, case.u, case.v, Params(**theta))
        return SpreadField(S["t_change"], r, e, th, st.burnable, S["cell"], tan_slope=S["tan_s"], upslope=S["up"])
    r, e, th = (np.zeros((H, *st.burnable.shape)) for _ in range(3))
    for j in range(H):
        u, v = case.u[j], case.v[j]
        if kind == "B0":
            r[j] = np.where(st.burnable, theta["c"], 0.0)
        else:                       # B1: uniform fuel, no slope, ellipse from U10 (run.fields)
            s10 = np.hypot(u, v)
            r[j] = np.where(st.burnable, theta["c"] * (1 + theta["b"] * s10 ** 1.5), 0.0)
            e[j] = np.where(st.burnable, np.sqrt(1 - 1 / lb_anderson_ms(s10 / 1.15 * 0.4) ** 2), 0.0)
            th[j] = np.arctan2(v, u)
    return SpreadField(S["t_change"], r, e, th, st.burnable, S["cell"])


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


# ----------------------------------------------------------------------------- search (PLAN §8 rev. 5)

CAL_FIRES = ("bush", "mangum", "telegraph")
OUT = PROJECT / "validation" / "calibration"


class Objective:
    """Mean over fires of the primary error, evaluated with G8 (revision 5); every call is logged."""

    def __init__(self, cases, kind, scheme="G8", workers=1, fixed=None):
        self.cases, self.kind, self.scheme, self.workers = cases, kind, scheme, workers
        self.fixed = fixed or {}                         # parameters held fixed (profiles)
        self.free = [p for p in BOUNDS[kind] if p not in self.fixed]
        self.log = []

    def theta(self, x_log):
        th = dict(self.fixed)
        th.update(zip(self.free, np.exp(np.asarray(x_log, float))))
        return {p: float(th[p]) for p in BOUNDS[self.kind]}

    def one(self, x_log):
        th = self.theta(x_log)
        per = {c.fire: evaluate(c, self.kind, th, self.scheme) for c in self.cases}
        obj = float(np.mean([r["primary_h"] for r in per.values()]))
        self.log.append({"theta": th, "objective_h": obj,
                         "per_fire": {f: {"primary_h": r["primary_h"], "signed_h": r["signed_h"],
                                          "median_growth_dice": float(np.median(r["growth_dice"]))}
                                      for f, r in per.items()}})
        return obj

    def __call__(self, X):
        """Vectorised for scipy (X has shape (n_free, S)); members run on threads (kernels drop the GIL),
        each member's result is independent of the thread count."""
        cols = [X[:, j] for j in range(X.shape[1])] if X.ndim == 2 else [X]
        if self.workers == 1 or len(cols) == 1:
            return np.array([self.one(x) for x in cols])
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(self.workers) as ex:
            return np.array(list(ex.map(self.one, cols)))


def safe_workers(cases, requested: int) -> int:
    """Threads that fit in memory: each evaluation holds three float64 fields (H, nr, nc) plus the graph's
    per-cell arrays; keep the total under 60 % of physical RAM."""
    import os

    per_eval = max(c.u.size for c in cases) * 8 * 3 * 1.3
    ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    shared = sum(c.u.nbytes + c.v.nbytes for c in cases)
    return max(1, min(requested, int((0.6 * ram - shared) // per_eval)))


def search(cases, kind, seed, workers, popsize=15, maxiter=60, fixed=None, checkpoint=None):
    """DE in log space. With `checkpoint` (a path), the population and the evaluation log are written
    after every generation, and a later call with the same path resumes from them (the run then records
    `resumed_at_generation`; the resumed path differs from an uninterrupted one only in RNG state)."""
    import time

    from scipy.optimize import differential_evolution

    obj = Objective(cases, kind, workers=workers, fixed=fixed)
    bounds = [tuple(np.log(BOUNDS[kind][p])) for p in obj.free]
    init, done, t0 = "latinhypercube", 0, time.perf_counter()
    if checkpoint is not None and checkpoint.exists():
        ck = json.loads(checkpoint.read_text())
        init, done, obj.log = np.array(ck["population"]), ck["generation"], ck["evaluations"]
        print(f"resuming at generation {done} ({len(obj.log)} evaluations)", flush=True)
    state = {"gen": done}

    def progress(intermediate_result):
        state["gen"] += 1
        r = intermediate_result
        print(f"gen {state['gen']}: best {r.fun:.3f} h, evaluations {len(obj.log)}, "
              f"{(time.perf_counter() - t0) / 60:.1f} min", flush=True)
        if checkpoint is not None:
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            checkpoint.write_text(json.dumps({"generation": state["gen"], "population": r.population.tolist(),
                                              "evaluations": obj.log}))

    res = differential_evolution(obj, bounds, seed=seed, popsize=popsize, maxiter=max(1, maxiter - done),
                                 polish=False, vectorized=True, updating="deferred", init=init,
                                 callback=progress)
    res.resumed_at_generation = done
    return obj, res


def _save(name, payload):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(payload, indent=1))
    print("wrote", OUT / f"{name}.json", flush=True)


def main(argv=None):
    import argparse
    import os
    import platform
    import subprocess
    import time

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["search", "hy", "lofo", "profile"])
    ap.add_argument("--kind", default="model", choices=list(BOUNDS))
    ap.add_argument("--seed", type=int, default=20261009)
    ap.add_argument("--fires", default=",".join(CAL_FIRES))
    ap.add_argument("--workers", type=int, default=int(os.environ.get("FIREPATH_THREADS", os.cpu_count() or 1)))
    ap.add_argument("--popsize", type=int, default=15)
    ap.add_argument("--maxiter", type=int, default=60)
    ap.add_argument("--param", help="profile: parameter to fix")
    ap.add_argument("--points", type=int, default=7, help="profile: grid points over the bound")
    a = ap.parse_args(argv)
    fires = a.fires.split(",")
    if set(fires) - set(CAL_FIRES):
        raise SystemExit(f"calibration uses only {CAL_FIRES}; validation fires are opened once, in M4")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=PROJECT).stdout.strip()
    meta = {"kind": a.kind, "seed": a.seed, "fires": fires, "popsize": a.popsize, "maxiter": a.maxiter,
            "workers": a.workers, "scheme": "G8 radius 8 at 90 m (PLAN §8 rev. 5)", "bounds": BOUNDS[a.kind],
            "commit": commit, "host": platform.platform(), "started_utc": datetime.now(timezone.utc).isoformat()}
    t = time.perf_counter()
    cases = [load_case(f) for f in fires]
    w = safe_workers(cases, a.workers)
    if w < a.workers:
        print(f"workers {a.workers} -> {w} (memory)", flush=True)
    a.workers = meta["workers"] = w
    print(f"cases loaded in {time.perf_counter() - t:.0f}s, workers {w}", flush=True)

    if a.command == "search":
        ck = OUT / "checkpoints" / f"{a.kind}_seed{a.seed}.json"
        obj, res = search(cases, a.kind, a.seed, a.workers, a.popsize, a.maxiter, checkpoint=ck)
        best = obj.theta(res.x)
        _save(f"{a.kind}_seed{a.seed}", {**meta, "best_theta": best, "best_objective_h": float(res.fun),
                                          "nit": int(res.nit), "nfev": int(res.nfev), "message": res.message,
                                          "resumed_at_generation": res.resumed_at_generation,
                                          "seconds": time.perf_counter() - t, "evaluations": obj.log})
        ck.unlink(missing_ok=True)              # finished: a rerun starts afresh
    elif a.command == "hy":
        # re-evaluate the behavioural set (within 5 % of the best G8 objective, all seeds) with HY
        runs = [json.loads(p.read_text()) for p in sorted(OUT.glob(f"{a.kind}_seed*.json"))]
        evals = [e for r in runs for e in r["evaluations"]]
        best = min(e["objective_h"] for e in evals)
        beh = sorted((e for e in evals if e["objective_h"] <= 1.05 * best), key=lambda e: e["objective_h"])
        uniq = list({json.dumps(e["theta"], sort_keys=True): e for e in beh}.values())
        # HY costs 5-15x G8: the best vector plus up to 29 more spread evenly over the behavioural set by rank
        idx = sorted(set([0] + np.linspace(0, len(uniq) - 1, min(30, len(uniq))).round().astype(int).tolist()))
        uniq = {i: uniq[i] for i in idx}
        hy = Objective(cases, a.kind, scheme="HY", workers=a.workers)
        X = np.log(np.array([[e["theta"][p] for p in BOUNDS[a.kind]] for e in uniq.values()])).T
        vals = hy(X)
        _save(f"{a.kind}_behavioural_HY", {**meta, "scheme": "HY at 90 m", "best_G8_h": best,
                                           "n_behavioural": len(beh), "n_reevaluated": len(uniq),
                                           "evaluations": hy.log,
                                           "g8_objective_h": [e["objective_h"] for e in uniq.values()],
                                           "hy_objective_h": vals.tolist(), "seconds": time.perf_counter() - t})
    elif a.command == "lofo":
        out = {}
        for left in fires:
            train = [c for c in cases if c.fire != left]
            obj, res = search(train, a.kind, a.seed, a.workers, a.popsize, a.maxiter)
            th = obj.theta(res.x)
            test = next(c for c in cases if c.fire == left)
            out[left] = {"theta": th, "in_sample_h": float(res.fun),
                         "left_out_G8": evaluate(test, a.kind, th, "G8"),
                         "left_out_HY": evaluate(test, a.kind, th, "HY")}
            print(left, out[left]["theta"], out[left]["left_out_G8"]["primary_h"], flush=True)
        _save(f"{a.kind}_lofo_seed{a.seed}", {**meta, "folds": out, "seconds": time.perf_counter() - t})
    else:
        lo, hi = BOUNDS[a.kind][a.param]
        rows = []
        for val in np.exp(np.linspace(np.log(lo), np.log(hi), a.points)):
            obj, res = search(cases, a.kind, a.seed, a.workers, a.popsize, a.maxiter, fixed={a.param: float(val)})
            rows.append({"value": float(val), "objective_h": float(res.fun), "theta": obj.theta(res.x)})
            print(a.param, val, res.fun, flush=True)
        _save(f"{a.kind}_profile_{a.param}", {**meta, "param": a.param, "rows": rows,
                                              "seconds": time.perf_counter() - t})


if __name__ == "__main__":
    main()
