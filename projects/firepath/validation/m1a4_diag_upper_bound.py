import json, sys, numpy as np
from firepath.canonical import solve
from firepath.mosaic import build, CENTER, RADIUS_CELLS, T_END, T_STOP
from firepath.confirm import _block_mean
case = sys.argv[1]
f1, in1 = build(case, 1)
hy, _ = solve("HY", f1, in1, T_STOP)
f4, in4 = build(case, 4)
ls4, _ = solve("LS", f4, in4, T_STOP)
g4, t = solve("G8", f4, in4, T_STOP)
ls, g = _block_mean(ls4, 4), _block_mean(g4, 4)
n = f1.shape[0]; rr, cc = np.mgrid[0:n, 0:n]
dist = np.hypot(rr - CENTER[0], cc - CENTER[1]) - RADIUS_CELLS
s = (~in1) & (dist >= 5) & np.isfinite(hy) & np.isfinite(ls) & np.isfinite(g) & (ls <= T_END)
q = lambda a: {"median": float(np.median(a)), "p95": float(np.percentile(a, 95, method="inverted_cdf"))}
out = {"case": case, "n": int(s.sum()), "g8_7p5_seconds": t,
       "share_LS7p5_above_G8_7p5": float((ls[s] > g[s] * 1.001).mean()),
       "LS7p5_minus_G8_rel": q(((ls - g) / g)[s]),
       "HY30_minus_G8_7p5_rel": q(((hy - g) / g)[s]),
       "share_HY30_above_G8_7p5": float((hy[s] > g[s] * 1.001).mean()),
       "abs_HY30_vs_G8_7p5": q((np.abs(hy - g) / g)[s])}
print(json.dumps(out))
