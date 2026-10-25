"""Scott & Burgan 40 table and Rothermel R0 (METHOD E1, E9, E10).

Reference values: tests/fixtures/pyretechnics_r0.json, produced by pyretechnics 2026.10.20 in a separate
environment (not a project dependency). Two explained differences:
1. pyretechnics stores loads in lb/ft² rounded to 4 decimals (e.g. GS3 1-h 0.30 t/ac -> 0.0138, exact
   0.013774); FirePath uses the GTR-153 t/ac values exactly. Effect up to 0.9 % on R0.
2. pyretechnics computes in 32-bit floats: with the same rounded loads the agreement is <= 1e-4.
3. At extinction (r = M/Mx = 1) the damping polynomial is 0 only up to rounding; FirePath returns exactly
   0 (the cell becomes a barrier), pyretechnics a value of order 1e-9 m/min.
"""

import json
from pathlib import Path

import pytest

import firepath.fuels as F
from firepath.moisture import DEAD_SCENARIOS, LIVE_SCENARIOS, Moisture

REF = json.loads((Path(__file__).parent / "fixtures" / "pyretechnics_r0.json").read_text())


def _rel(a, b):
    return abs(a - b) / b if b > 1e-6 else abs(a - b) / 1e-6


def _cases():
    for key, v in REF["values"].items():
        c, d, l = key.split("|")
        yield int(c), Moisture(*DEAD_SCENARIOS[d], *LIVE_SCENARIOS[l]), v, key


def test_table_transcription_spot_checks():
    assert len(F.SB40) == 40
    assert F.SB40[101] == ("GR1", 0.10, 0.00, 0.00, 0.30, 0.00, True, 2200, 2000, 9999, 0.4, 15, 8000)
    assert F.SB40[106][-1] == 9000                      # GR6 is the only 9000 BTU/lb model
    assert F.SB40[188] == ("TL8", 5.80, 1.40, 1.10, 0.00, 0.00, False, 1800, 9999, 9999, 0.3, 35, 8000)
    assert F.SB40[204] == ("SB4", 5.25, 3.50, 5.25, 0.00, 0.00, False, 2000, 9999, 9999, 2.7, 25, 8000)
    assert set(REF["values"]) and {int(k.split("|")[0]) for k in REF["values"]} == set(F.SB40)


def test_r0_matches_pyretechnics_with_its_rounded_loads(monkeypatch):
    k = F.TONS_AC_TO_LB_FT2
    rounded = {c: (r[0], *[round(w * k, 4) / k for w in r[1:6]], *r[6:]) for c, r in F.SB40.items()}
    monkeypatch.setattr(F, "SB40", rounded)
    worst = max(_rel(F.fuel_bed(c, m).r0_mmin, v) for c, m, v, _ in _cases())
    assert worst < 1e-4


def test_r0_with_exact_gtr153_loads_differs_only_by_rounding():
    worst = max(_rel(F.fuel_bed(c, m).r0_mmin, v) for c, m, v, _ in _cases())
    assert worst < 0.01


def test_extinction_and_dynamic_transfer():
    wet = Moisture(40, 41, 42, 120, 150)              # above every dead extinction moisture (<= 40 %)
    assert F.fuel_bed(188, wet).r0_ftmin == 0.0       # TL8, dead-only model
    dead, live, _, _ = F.particles(102, Moisture(6, 7, 8, 30, 60))      # GR2 fully cured at L1
    assert not live and abs(sum(p.load for p in dead) - (0.10 + 1.00) * F.TONS_AC_TO_LB_FT2) < 1e-12
    dead, live, _, _ = F.particles(102, Moisture(6, 7, 8, 120, 150))    # uncured at L4
    assert abs(sum(p.load for p in live) - 1.00 * F.TONS_AC_TO_LB_FT2) < 1e-12


@pytest.mark.parametrize("code", [101, 122, 145, 165, 188])
def test_r0_decreases_with_dead_moisture(code):
    r = [F.fuel_bed(code, Moisture(*DEAD_SCENARIOS[d], *LIVE_SCENARIOS["L2"])).r0_ftmin for d in ("D1", "D2", "D3")]
    assert r[0] > r[1] > r[2] >= 0


def test_wind_and_slope_factors_match_pyretechnics(monkeypatch):
    from firepath.rothermel import FT_PER_M, phi_slope, phi_wind

    k = F.TONS_AC_TO_LB_FT2
    monkeypatch.setattr(F, "SB40", {c: (r[0], *[round(w * k, 4) / k for w in r[1:6]], *r[6:])
                                    for c, r in F.SB40.items()})
    worst_w = worst_s = 0.0
    for c, m, _, key in _cases():
        b = F.fuel_bed(c, m)
        pw = phi_wind(134.112 * FT_PER_M, b.sigma, b.beta / b.beta_op)     # 5 mi/h midflame
        worst_w = max(worst_w, abs(pw - REF["phi_w"][key]) / REF["phi_w"][key])
        worst_s = max(worst_s, abs(phi_slope(b.beta, 0.3) - REF["phi_s"][key]) / REF["phi_s"][key])
    assert worst_w < 2e-4 and worst_s < 1e-6
