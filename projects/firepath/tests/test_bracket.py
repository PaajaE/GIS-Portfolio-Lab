import numpy as np

from firepath.bracket import evaluate


def _setup(n=21):
    inside = np.zeros((n, n), bool)
    inside[9:12, 9:12] = True
    lower = np.zeros((n, n))
    return inside, lower


def test_exact_reference_passes_and_categories(monkeypatch):
    import firepath.mosaic as m
    monkeypatch.setattr(m, "CENTER", (10, 10))
    monkeypatch.setattr(m, "RADIUS_CELLS", 1.5)
    inside, lower = _setup()
    truth = np.full(inside.shape, 100.0)
    # LS converging at order 1 from above towards the truth; bound slightly above the truth
    ls2, ls4, ls8 = truth * 1.04, truth * 1.02, truth * 1.01
    g = truth * 1.01
    r = evaluate("iso", truth.copy(), ls2, ls4, ls8, g, g * 1.1, inside, lower)
    assert r["reference_categories"]["estimate"] == 1.0
    assert r["error"]["median"] < 1e-9 and r["outcome"] == "PASS"


def test_wide_spread_is_inconclusive_and_lateness_detected(monkeypatch):
    import firepath.mosaic as m
    monkeypatch.setattr(m, "CENTER", (10, 10))
    monkeypatch.setattr(m, "RADIUS_CELLS", 1.5)
    inside, lower = _setup()
    truth = np.full(inside.shape, 100.0)
    ls = truth * 1.05                    # no convergence: Richardson does not apply
    g = truth * 1.10
    hy = truth * 1.2                     # later than the upper bound everywhere
    r = evaluate("iso", hy, ls, ls, ls, g, g, inside, lower)
    assert r["reference_categories"]["fallback"] == 1.0
    assert r["provably_late_share"] == 1.0
    assert r["outcome"] == "INCONCLUSIVE"
