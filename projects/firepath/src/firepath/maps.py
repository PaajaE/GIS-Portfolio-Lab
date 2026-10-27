"""M1b error maps (static PNG for the validation record; the web maps are M8).

  uv run python -m firepath.maps <fire> [--cell 90] [--scheme HY]

One panel per model/baseline from the Mode A run: interval-censored arrival error per scored cell
(the cells run.metrics scores), diverging blue (early) <-> gray (inside the observed interval) <-> red
(late), binned in hours, with the observed perimeters of the evaluation window as thin outlines.
Writes validation/figures/m1b_<fire>_<cell>m_<scheme>_error.png. matplotlib is a dev dependency.
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from .harvest import PROJECT
from .observed import CONSISTENT, NEVER, interval_error
from .run import CAP_MIN

# diverging pair from the dataviz reference palette: blue arm, gray midpoint, red arm (light -> dark)
EARLY = ["#1c4f8f", "#2a78d6", "#7fb0ea", "#c9def6"]
MID = "#f0efec"
LATE = ["#f6cfcf", "#ee8f8e", "#e34948", "#9b2525"]
EDGES_H = [-48, -24, -12, -3, 0, 0, 3, 12, 24, 48]          # 0..0 = the inside bin
LABELS = [">24 h early", "12–24 h early", "3–12 h early", "0–3 h early", "inside observed interval",
          "0–3 h late", "3–12 h late", "12–24 h late", ">24 h late (capped at 48 h)"]


def classify(err_min):
    """Bin index 0..8 for each error (minutes); inside (0) is bin 4."""
    h = err_min / 60.0
    out = np.full(h.shape, 4, int)
    out[h < 0] = 3
    out[h <= -3] = 2
    out[h <= -12] = 1
    out[h <= -24] = 0
    out[h > 0] = 5
    out[h > 3] = 6
    out[h > 12] = 7
    out[h > 24] = 8
    return out


def main(argv=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    ap = argparse.ArgumentParser()
    ap.add_argument("fire")
    ap.add_argument("--cell", type=int, default=90)
    ap.add_argument("--scheme", default="HY")
    a = ap.parse_args(argv)
    kinds = ["model", "B0", "B1"]
    od = PROJECT / "data" / "out" / a.fire
    runs = {k: np.load(od / f"run_{a.fire}_{a.cell}m_{a.scheme}_{k}.npz") for k in kinds}
    z = runs["model"]
    flag, rel, lo, hi = z["flag"], z["rel_scans_min"], z["lo"], z["hi"]
    first_in = np.full(flag.shape, -1)
    for k in range(len(rel)):        # first scan time at or after hi = the perimeter that first contains the cell
        first_in[(first_in < 0) & (hi <= rel[k])] = k
    cmap = ListedColormap(EARLY + [MID] + LATE)
    cmap.set_bad("white")
    report = json.loads((PROJECT / "validation" / f"m1b_{a.fire}_{a.cell}m_{a.scheme}_model.json").read_text())

    fig, axes = plt.subplots(1, 3, figsize=(13, 5.6), constrained_layout=True)
    for ax, kind in zip(axes, kinds):
        arr = runs[kind][kind].astype(float)
        err = np.clip(interval_error(arr, lo, hi), -CAP_MIN, CAP_MIN)
        burned = np.isfinite(arr) & (arr <= rel[-1])
        scored = (flag == CONSISTENT) | ((flag == NEVER) & burned)
        img = np.ma.masked_array(classify(err), ~scored)
        ax.imshow(img, cmap=cmap, vmin=-0.5, vmax=8.5, interpolation="nearest")
        ax.imshow(np.ma.masked_array(np.ones(flag.shape), runs[kind]["burnable"]), cmap=ListedColormap(["#8f8f8a"]),
                  interpolation="nearest")
        for k in range(len(rel)):
            ax.contour((first_in >= 0) & (first_in <= k), levels=[0.5], colors="#222222", linewidths=0.4)
        e = err[scored] / 60.0
        ax.set_title(f"{kind}: mean |error| {np.mean(np.abs(e)):.1f} h, {100 * (e < 0).mean():.0f} % early, "
                     f"{100 * (e > 0).mean():.0f} % late", fontsize=9.5, loc="left")
        ax.set_xticks([])
        ax.set_yticks([])
    handles = [Patch(color=c, label=lab) for c, lab in zip(EARLY + [MID] + LATE, LABELS)]
    handles += [Patch(facecolor="#8f8f8a", label="non-burnable"),
                Patch(facecolor="white", edgecolor="#222222", linewidth=0.6, label="observed perimeters (scans)")]
    fig.legend(handles=handles, loc="outside lower center", ncol=4, fontsize=8.5, frameon=False)
    w = report["window"]
    fig.suptitle(f"{a.fire.title()}: interval-censored arrival error, Mode A from {w['t0_utc'][:16]} UTC, "
                 f"{w['scans']} scans, {a.cell} m, {a.scheme}. Hand-set parameters (pipeline check, not skill)",
                 fontsize=10.5)
    out = PROJECT / "validation" / "figures"
    out.mkdir(exist_ok=True)
    p = out / f"m1b_{a.fire}_{a.cell}m_{a.scheme}_error.png"
    fig.savefig(p, dpi=110)
    print("wrote", p)


if __name__ == "__main__":
    main()
