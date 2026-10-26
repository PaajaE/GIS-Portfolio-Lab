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


def test_landfire_zip_clip(tmp_path, monkeypatch):
    """LF 2020 from a ScienceBase-style CONUS zip: the clip is an exact window of the source (no
    resampling) and covers the fire box."""
    import zipfile

    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds

    from firepath import harvest as H

    box = (-112.30, 36.60, -112.10, 36.80)
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", "EPSG:5070", *box)
    t = from_origin(np.floor(x0 / 30) * 30 - 3000, np.ceil(y1 / 30) * 30 + 3000, 30, 30)
    shape = (int((y1 - y0) / 30) + 220, int((x1 - x0) / 30) + 220)
    src = np.arange(shape[0] * shape[1], dtype="int32").reshape(shape) % 32000
    zdir = tmp_path / "landfire_conus"
    zdir.mkdir()
    for layer in H.LANDFIRE_LAYERS:
        tif = tmp_path / f"LF2020_{layer}_CONUS.tif"
        with rasterio.open(tif, "w", driver="GTiff", height=shape[0], width=shape[1], count=1, dtype="int16",
                           crs="EPSG:5070", transform=t, nodata=-9999) as d:
            d.write(src.astype("int16"), 1)
        with zipfile.ZipFile(zdir / f"LF2020_{layer}_CONUS_20260522.zip", "w") as z:
            z.write(tif, f"LF2020_{layer}_CONUS/Tif/{tif.name}")
    monkeypatch.setattr(H, "LF_ZIPS", zdir)
    monkeypatch.setattr(H, "RAW", tmp_path / "raw")
    monkeypatch.setattr(H, "_lonlat_bbox", lambda fire: box)
    added = []
    H._landfire_zip("x", "LF2020", type("M", (), {"add": lambda self, *a, **k: added.append((a, k))})())
    assert len(added) == 3 and all(k["source_zip_sha256"] for _, k in added)
    with rasterio.open(tmp_path / "raw" / "x" / "landfire" / "LF2020_FBFM40.tif") as c:
        cb = c.bounds
        r0 = int(round((t.f - c.transform.f) / 30))
        c0 = int(round((c.transform.c - t.c) / 30))
        assert np.array_equal(c.read(1), src[r0:r0 + c.height, c0:c0 + c.width].astype("int16"))
        assert c.crs.to_epsg() == 5070
    assert cb.left <= x0 and cb.right >= x1 and cb.bottom <= y0 and cb.top >= y1
