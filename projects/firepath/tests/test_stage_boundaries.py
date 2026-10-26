"""Stage-boundary checks on the real prepared inputs and run outputs (PLAN M1b): CRS, grid identity, codes,
nodata, time order, provenance hashes. Data are git-ignored, so each test skips when its files are absent.
"""

import hashlib
import json

import numpy as np
import pytest

from firepath.fuels import NONBURNABLE, SB40
from firepath.harvest import INTERIM, PROJECT

FIRE = "mangum"
D = INTERIM / FIRE
OUT = PROJECT / "data" / "out" / FIRE


def need(*paths):
    missing = [p for p in paths if not p.exists()]
    if missing:
        pytest.skip(f"data not present: {missing[0]}")


def test_inputs_grid_identity_codes_nodata():
    need(D / "grid.json", D / "inputs.npz")
    g = json.loads((D / "grid.json").read_text())
    z = np.load(D / "inputs.npz")
    assert int(z["epsg"]) == g["epsg"] == 26912
    assert tuple(z["transform"][:6]) == (g["cell"], 0.0, g["x0"], 0.0, -g["cell"], g["y1"])
    for k in ("fuel", "cc", "ch", "dem", "tan_slope", "upslope", "first_in", "flag"):
        assert z[k].shape == (g["height"], g["width"]), k
    codes = set(np.unique(z["fuel"]).tolist())
    assert codes <= set(SB40) | set(NONBURNABLE), codes - set(SB40) - set(NONBURNABLE)
    for k in ("dem", "ch", "tan_slope", "upslope"):
        assert np.isfinite(z[k]).all(), f"nodata left in {k}"
    assert z["cc"].min() >= 0 and z["cc"].max() <= 100
    assert z["ch"].min() >= 0
    assert (z["tan_slope"] >= 0).all()


def test_scan_and_wind_time_order_and_coverage():
    need(D / "inputs.npz", D / "wind.npz", D / "grid.json")
    g = json.loads((D / "grid.json").read_text())
    s = np.load(D / "inputs.npz")["scan_unix"]
    assert (np.diff(s) > 0).all()
    w = np.load(D / "wind.npz")
    t = w["valid_unix"]
    assert (np.diff(t) == 3600).all(), "HRRR f00 hours must be consecutive"
    assert t[0] <= s[0] and t[-1] >= s[-1], "wind must cover every scan"
    assert w["u"].shape == w["v"].shape == (len(t), len(w["y"]), len(w["x"]))
    assert np.isfinite(w["u"]).all() and np.isfinite(w["v"]).all()
    x0, y0, x1, y1 = g["bounds_utm"]
    half = float(w["cell"]) / 2
    assert w["x"][0] - half <= x0 and w["x"][-1] + half >= x1
    assert w["y"][-1] - half <= y0 and w["y"][0] + half >= y1


def test_provenance_hashes_match_raw_files():
    man = PROJECT / "provenance" / f"harvest_{FIRE}.json"
    need(man)
    files = json.loads(man.read_text())["files"]
    present = {p: v for p, v in files.items() if (PROJECT / p).is_file()}
    if not present:
        pytest.skip("raw files not present")
    for p, v in present.items():
        assert "sha256" in v, p
        if (PROJECT / p).stat().st_size < 50_000_000:     # hash the small ones; large ones by size
            assert hashlib.sha256((PROJECT / p).read_bytes()).hexdigest() == v["sha256"], p
        elif "bytes" in v:
            assert (PROJECT / p).stat().st_size == v["bytes"], p


@pytest.mark.parametrize("kind", ["model", "B0", "B1"])
def test_mode_a_outputs(kind):
    f = OUT / f"run_{FIRE}_90m_HY_{kind}.npz"
    need(f)
    z = np.load(f)
    a = z[kind]
    assert a.shape == z["burnable"].shape == z["fuel"].shape == z["flag"].shape
    rel = z["rel_scans_min"]
    assert rel[0] == 0 and (np.diff(rel) > 0).all()
    assert not np.isnan(a).any()
    fin = np.isfinite(a)
    assert (a[fin] >= 0).all()
    assert not (fin & ~z["burnable"]).any(), "a non-burnable cell was reached"
    assert np.isin(z["fuel"][fin], NONBURNABLE).sum() == 0


def test_landfire_version_precedes_fire_year():
    """Leakage rule (PLAN §3) for the fires whose LANDFIRE comes from the WCS. The conus_2016 workspace
    serves no disturbance (FDist) layer, so the check is structural: the version's last mapped
    disturbance year must be before the year of the first scan."""
    from datetime import datetime, timezone

    from firepath.harvest import FIRES

    need(D / "inputs.npz")
    ws, ver = FIRES[FIRE]["landfire"]
    year = datetime.fromtimestamp(float(np.load(D / "inputs.npz")["scan_unix"][0]), timezone.utc).year
    assert int(ver[2:]) < year, (ver, year)
