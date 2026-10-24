"""Stage-boundary assertions on the terrain predictors (skipped until `make terrain` has run)."""

import geopandas as gpd
import numpy as np
import pytest
import rasterio
import rasterio.features

from landslide import config as C
from landslide.terrain import LAYERS

# plausible bounds inside the counties (5 m cells, Blue Ridge terrain)
BOUNDS = {"slope_deg": (0, 90), "northness": (-1, 1), "eastness": (-1, 1), "tri": (0, 200),
          "profc_5": (-5, 5), "planc_5": (-5, 5), "profc_15": (-2, 2), "planc_15": (-2, 2),
          "relief_50": (0, 300), "tpi_50": (-100, 100), "relief_250": (0, 900), "tpi_250": (-300, 300),
          "rough_25": (0, 45)}


@pytest.mark.parametrize("region", list(C.REGIONS))
def test_terrain_layers(region):
    d = C.INTERIM / f"terrain_{region}"
    if not (d / "run.json").exists():
        pytest.skip("run `make terrain` first")
    with rasterio.open(C.INTERIM / f"dem_5m_{region}.tif") as dem:
        grid = (dem.crs, dem.transform, dem.shape)
        sl = (slice(None, None, 7), slice(None, None, 7))  # every 7th cell: enough for bounds and nodata
        cty = gpd.read_parquet(C.RAW / "counties.parquet").to_crs(C.CRS)
        poly = cty[cty["NAME"].isin(C.REGIONS[region])].union_all()
        inside = (~rasterio.features.geometry_mask([poly], dem.shape, dem.transform))[sl]
    for k in LAYERS:
        with rasterio.open(d / f"{k}.tif") as s:
            assert (s.crs, s.transform, s.shape) == grid, k
            assert s.nodata == C.OUT_NODATA
            a = s.read(1)[sl][inside]
        assert (a == C.OUT_NODATA).mean() < 1e-4, k
        v = a[a != C.OUT_NODATA]
        lo, hi = BOUNDS[k]
        assert lo <= v.min() and v.max() <= hi, (k, v.min(), v.max())
