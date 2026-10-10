"""Positive rasterization rule on a hand-made fixture."""

import geopandas as gpd
import rasterio
from shapely.geometry import box

from landslide.labels import positives_raster


def test_small_polygon_falls_back_to_its_cell():
    tr = rasterio.transform.from_origin(0, 50, 5, 5)  # 10 x 10 cells of 5 m
    big = box(10, 30, 20, 40)  # contains the centres of 2 x 2 cells
    tiny = box(26, 21, 27, 22)  # 1 m x 1 m, contains no cell centre
    g = gpd.GeoDataFrame(geometry=[big, tiny], crs="EPSG:26917")
    m, fallback = positives_raster(g, tr, (10, 10))
    assert m[2:4, 2:4].all() and m.sum() == 5 and fallback == 1
    assert m[5, 5]  # cell containing (26.5, 21.5): col 5, row (50 - 21.5) / 5 = 5
