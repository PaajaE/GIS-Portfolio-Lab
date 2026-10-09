"""Stage-boundary assertions on the harvested M1 data (skipped until `make harvest` has run)."""

import json

import geopandas as gpd
import numpy as np
import pytest
import rasterio
import rasterio.features

from landslide import config as C
from landslide.inventory import normalise, positive_mask

MANIFEST = C.PROVENANCE / "harvest_manifest.json"
pytestmark = pytest.mark.skipif(not (C.RAW / "ncgs_features.parquet").exists(), reason="run `make harvest` first")


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST.read_text())


def test_manifest_checksums_present(manifest):
    for key, rec in manifest["sources"].items():
        if key.startswith("dem_tiles_"):
            assert all(t["sha256_1m"] and t["sha256_5m"] for t in rec["tiles"].values())
        else:
            assert len(rec["sha256"]) == 64 and (C.ROOT / rec["path"]).exists(), key


def test_counties_and_regions():
    cty = gpd.read_parquet(C.RAW / "counties.parquet")
    assert sorted(cty["NAME"]) == sorted(n for r in C.REGIONS.values() for n in r)
    assert cty.is_valid.all()
    km2 = cty.to_crs(C.CRS).set_index("NAME").area / 1e6
    assert 1600 < km2["Buncombe County"] < 1800 and 750 < km2["Yancey County"] < 850


def test_inventory_snapshot_positive_counts():
    inv = normalise(gpd.read_parquet(C.RAW / "ncgs_features.parquet")).to_crs(C.CRS)
    cty = gpd.read_parquet(C.RAW / "counties.parquet").to_crs(C.CRS)
    aoi = cty[cty["NAME"].isin(C.REGIONS["aoi"])].union_all()
    pos = inv[positive_mask(inv)]
    n = int(pos.geometry.representative_point().within(aoi).sum())
    assert n == 2962  # frozen snapshot 2026-10-08 (PLAN §0b); a change means the service was re-queried
    assert pos.is_valid.all()


def test_huc12_cover_aoi():
    h = gpd.read_parquet(C.RAW / "huc12.parquet").to_crs(C.CRS)
    cty = gpd.read_parquet(C.RAW / "counties.parquet").to_crs(C.CRS)
    aoi = cty[cty["NAME"].isin(C.REGIONS["aoi"])].union_all()
    assert h["huc12"].str.len().eq(12).all()
    assert h.union_all().intersection(aoi).area / aoi.area > 0.999


def test_mrms_grids():
    for f in C.MRMS_FILES:
        with rasterio.open(C.RAW / f.removesuffix(".gz")) as s:
            assert s.driver == "GRIB" and s.tags(1).get("GRIB_UNIT") == "[mm]"
            a = s.read(1)
            assert 0 < a.max() < 1500


def test_mrlc_native_grid():
    for key in C.MRLC_COVERAGES:
        for r in C.REGIONS:
            with rasterio.open(C.RAW / f"{key}_{r}.tif") as s:
                assert s.crs.to_epsg() == 5070 and s.res == (30.0, 30.0)
                assert (s.transform.c + 2493045) % 30 == 0 and (3310005 - s.transform.f) % 30 == 0
                a = s.read(1)
                if key == "nlcd2021":
                    assert set(np.unique(a)) <= {0, 11, 12, 21, 22, 23, 24, 31, 41, 42, 43, 52, 71, 81, 82, 90, 95}
                else:  # canopy %: declared nodata 0 is a valid 0 %; 254 is the product's no-data flag (M3)
                    assert set(np.unique(a[a > 100])) <= {254} and (a == 254).mean() < 1e-3


@pytest.mark.skipif(not (C.INTERIM / "dem_5m_aoi.tif").exists(), reason="run `make harvest-dem` first")
@pytest.mark.parametrize("region", list(C.REGIONS))
def test_dem_mosaic(region, manifest):
    p = C.INTERIM / f"dem_5m_{region}.tif"
    if not p.exists():
        pytest.skip(f"{region} mosaic not built")
    rec = manifest["sources"][f"dem_tiles_{region}"]
    ends = [t["lidar_enddate"] for t in rec["tiles"].values()]
    assert all(e and e < "20240925" for e in ends), "every tile must be pre-event"
    with rasterio.open(p) as s:
        assert s.crs.to_epsg() == 26917 and s.res == (5.0, 5.0)
        assert s.transform.c % 5 == 0 and s.transform.f % 5 == 0
        assert s.nodata == C.OUT_NODATA
        cty = gpd.read_parquet(C.RAW / "counties.parquet").to_crs(C.CRS)
        poly = cty[cty["NAME"].isin(C.REGIONS[region])].union_all()
        inside = ~rasterio.features.geometry_mask([poly], (s.height, s.width), s.transform)
        a = s.read(1)
        v = a[inside]
        assert (v == C.OUT_NODATA).mean() < 1e-3
        v = v[v != C.OUT_NODATA]
        assert 150 < v.min() and v.max() < 2040
    # Overlaps between tiles (incl. different pre-event projects: NC Phase 5 2017, Phase 4 2016-17, TN 2016)
    # must show no vertical offset and only local differences; checked 2026-10-09: |median| <= 0.09 m,
    # p99 |diff| <= 0.9 m, share > 1 m <= 0.8 %
    seams = [sd for sd in rec["mosaic"]["seams"] if sd["overlap_cells"]]
    assert all(abs(sd["median_m"]) < 0.15 for sd in seams)
    assert all(sd["p99_abs_m"] < 1.0 and sd["share_gt_1m"] < 0.01 for sd in rec["mosaic"]["seams"] if sd["overlap_cells"])
