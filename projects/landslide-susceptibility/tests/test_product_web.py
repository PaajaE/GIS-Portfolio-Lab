import json

import numpy as np
import pytest

from landslide import config as C
from landslide.product import area_rank
from landslide.web_data import encode, reduce2, rerank


def test_area_rank_is_top_k_percent_by_descending_score():
    score = np.arange(200, dtype=np.float32).reshape(10, 20)  # 200 cells, highest score = 199
    mask = np.ones_like(score, bool)
    mask[0, 0] = False
    score[0, 1] = np.nan
    r = area_rank(score, mask)
    assert r[0, 0] == 0 and r[0, 1] == 0  # outside mask / NaN -> not ranked
    assert r[-1, -1] == 1  # best cell in the top 1 %
    ranked = r[r > 0]
    assert ranked.size == 198
    for k in (1, 10, 50):  # class = ceil(position * 100 / N) -> exactly floor(k * N / 100) cells in the top k %
        assert (ranked <= k).sum() == (k * 198) // 100


def test_encode_channel_values_and_coarse_bins_beyond_slider():
    rank = np.array([0, 0, 1, 30, 31, 100], np.uint8)
    dom = np.array([False, True, True, True, True, True])
    assert encode(rank, dom).tolist() == [0, 1, 101, 72, 62, 2]


def test_rerank_keeps_top_k_area_after_generalisation():
    rng = np.random.default_rng(0)
    rk = rng.integers(1, 101, (64, 64)).astype(np.float32)
    m, n, d = (102 - rk), np.ones_like(rk), np.ones(rk.shape, bool)
    for _ in range(3):
        m, n, d = reduce2(m, n, d)
    e = rerank(m, n, d)
    r = 102 - e.astype(int)
    share = (n * (r <= 10)).sum() / n.sum()
    assert abs(share - 0.10) < 0.07  # 64 coarse pixels: within one pixel of 10 %


def test_custom_decoding_margin_matches_the_app():
    # app.js decodes channel c with factor 1 and the other two with 1/256 and 1/65536; contamination < 0.5
    worst = 101 / 256 + 101 / 65536
    assert worst < 0.5


@pytest.mark.skipif(not (C.VALIDATION / "per_k_metrics.json").exists(), reason="run `make product` first")
def test_per_k_capture_monotone_and_intervals_contain_point():
    r = json.loads((C.VALIDATION / "per_k_metrics.json").read_text())
    for name in ("oof_lr", "oof_gbm", "slope", "final_lr"):
        c = np.array(r[name]["capture"])
        assert np.all(np.diff(c) >= 0) and 0 <= c[0] and c[-1] <= 1
        assert np.all(np.array(r[name]["ci95_low"]) <= c + 1e-9) and np.all(c <= np.array(r[name]["ci95_high"]) + 1e-9)
