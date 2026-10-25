import struct

import numpy as np

from firepath.harvest import _hrrr_ranges, parse_polygon, read_dbf, shx_offsets


def _poly_record(rings):
    pts = [p for r in rings for p in r]
    parts, k = [], 0
    for r in rings:
        parts.append(k)
        k += len(r)
    xy = np.array(pts, float)
    box = [xy[:, 0].min(), xy[:, 1].min(), xy[:, 0].max(), xy[:, 1].max()]
    return (struct.pack("<i4d2i", 5, *box, len(rings), len(pts)) + struct.pack(f"<{len(parts)}i", *parts)
            + struct.pack(f"<{2 * len(pts)}d", *xy.ravel()))


def test_polygon_with_hole_and_second_shell():
    shell = [(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)]          # clockwise = shell (shapefile rule)
    hole = [(2, 2), (4, 2), (4, 4), (2, 4), (2, 2)]               # counter-clockwise = hole
    shell2 = [(20, 0), (20, 5), (25, 5), (25, 0), (20, 0)]
    g = parse_polygon(_poly_record([shell, hole, shell2]))
    assert g.geom_type == "MultiPolygon" and abs(g.area - (100 - 4 + 25)) < 1e-9
    assert parse_polygon(struct.pack("<i", 0)) is None


def test_dbf_and_shx_readers():
    fields = [(b"Incident_C", 20), (b"UTC", 19)]
    hl = 32 + 32 * len(fields) + 1
    rl = 1 + sum(n for _, n in fields)
    head = struct.pack("<BBBBIHH20x", 3, 126, 1, 1, 2, hl, rl)
    desc = b"".join(name.ljust(11, b"\0") + b"C" + b"\0" * 4 + bytes([n]) + b"\0" * 15 for name, n in fields)
    recs = b"".join(b" " + a.ljust(20) + b.ljust(19) for a, b in
                    [(b"AZ-KNF-000359_Magnum", b"2020-06-10 07:13:00"), (b"X", b"2021-01-01 00:00:00")])
    rows = read_dbf(head + desc + b"\r" + recs)
    assert rows[0] == {"Incident_C": "AZ-KNF-000359_Magnum", "UTC": "2020-06-10 07:13:00"} and len(rows) == 2
    shx = b"\0" * 100 + struct.pack(">ii", 50, 10) + struct.pack(">ii", 64, 20)
    assert shx_offsets(shx) == [(100, 20), (128, 40)]


def test_hrrr_index_ranges():
    idx = ("1:0:d=2020061000:REFC:entire atmosphere:anl:\n"
           "71:100:d=2020061000:UGRD:10 m above ground:anl:\n"
           "72:250:d=2020061000:VGRD:10 m above ground:anl:\n"
           "73:400:d=2020061000:UGRD:10 m above ground:1 hour fcst:\n")
    assert _hrrr_ranges(idx) == {"UGRD:10 m above ground": (100, 249), "VGRD:10 m above ground": (250, 399)}
