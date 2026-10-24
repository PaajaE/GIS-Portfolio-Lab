"""Half-basin slope units on hand-built D8 fixtures (no pysheds involved)."""

import numpy as np

from landslide.units import half_basins, jump_to_root, merge_small, successor

N, NE, E, SE, S, SW, W, NW = 64, 128, 1, 2, 4, 8, 16, 32


def accumulation(fdir):
    """Brute-force D8 accumulation (cells, including the cell itself)."""
    nxt = successor(fdir)
    acc = np.zeros(nxt.size, np.int64)
    for i in range(nxt.size):
        j = i
        while j >= 0:
            acc[j] += 1
            j = nxt[j]
    return acc.reshape(fdir.shape).astype(np.float32)


def v_valley(h=12, w=9):
    """Valley axis in the middle column flowing south; banks flow towards the axis."""
    f = np.empty((h, w), np.uint8)
    c = w // 2
    f[:, :c] = E
    f[:, c + 1 :] = W
    f[:, c] = S
    return f


def test_successor_and_jump():
    f = np.array([[E, S], [N, S]], np.uint8)  # (1,0) flows north into (0,0); (1,1) leaves the grid
    nxt = successor(f)
    assert nxt.tolist() == [1, 3, 0, -1]
    ptr = np.where(nxt >= 0, nxt, np.arange(4))
    assert jump_to_root(ptr).tolist() == [3, 3, 3, 3]


def test_v_valley_gives_left_and_right_banks():
    f = v_valley()
    acc = accumulation(f)
    lab = half_basins(f, acc, threshold_cells=20, min_cells=1)
    c = f.shape[1] // 2
    rows = slice(4, None)  # below the channel head, cells drain sideways into the channel
    west, east = np.unique(lab[rows, :c]), np.unique(lab[rows, c + 1 :])
    assert len(west) == 1 and len(east) == 1 and west[0] != east[0]
    assert (lab > 0).all()  # every cell reaches the channel


def test_junction_splits_links():
    # two tributary columns joining a trunk row that flows east and leaves the grid
    h, w = 6, 7
    f = np.full((h, w), S, np.uint8)
    f[h - 1, :] = E
    acc = accumulation(f)
    lab = half_basins(f, acc, threshold_cells=3, min_cells=1)
    # columns 1 and 4 drain to different points of the trunk -> different links -> different labels
    assert lab[0, 1] != lab[0, 4]


def test_merge_small_into_longest_boundary():
    lab = np.array([[1, 1, 1, 2, 2], [1, 1, 3, 2, 2], [1, 1, 1, 2, 2]])
    out = merge_small(lab, min_cells=2)
    # unit 3 (one cell) shares 3 edges with unit 1 and 1 edge with unit 2 -> joins unit 1
    assert out[1, 2] == out[0, 0] and len(np.unique(out)) == 2
