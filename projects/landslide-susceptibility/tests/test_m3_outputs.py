"""Stage-boundary assertions on the M3 outputs (skipped until the stages have run)."""

import numpy as np
import pandas as pd
import pytest
import rasterio

from landslide import config as C
from landslide.labels import REGION

LAB = C.INTERIM / f"labels_{REGION}"
pytestmark = pytest.mark.skipif(not (LAB / "positives.parquet").exists(), reason="run `make labels` first")


def grid_of(path):
    with rasterio.open(path) as s:
        return s.crs, s.transform, s.shape


@pytest.fixture(scope="module")
def dem_grid():
    return grid_of(C.INTERIM / f"dem_5m_{REGION}.tif")


def test_stack_and_hydro_on_dem_grid(dem_grid):
    for p in list((C.INTERIM / f"stack_{REGION}").glob("*.tif")) + [
            C.INTERIM / f"hydro_{REGION}" / f"{k}.tif" for k in ("log_area", "hand", "dist_channel")]:
        assert grid_of(p) == dem_grid, p.name


def test_sample_tables():
    pos = pd.read_parquet(LAB / "positives.parquet")
    neg = pd.read_parquet(LAB / "negatives.parquet")
    assert len(pos) == 16421 and len(neg) == 400_000  # frozen snapshot + seed
    assert pos["label"].eq(1).all() and neg["label"].eq(0).all()
    for df in (pos, neg):
        assert df["rain_mm"].ge(C.TRIGGER_MM).all()  # triggered domain
        assert df["county"].isin([1, 2]).all()
        assert df["canopy"].between(0, 100).all()
        assert df["lc_group"].between(1, 5).all()  # never open water
        assert df["geology"].between(1, 4).all() and df["huc12"].notna().all()
        assert (df["unit_0.1"] > 0).all()
    # negatives never fall in exclusion zones or on positive cells
    with rasterio.open(LAB / "exclusion.tif") as s:
        excl = s.read(1)
    with rasterio.open(LAB / "positive.tif") as s:
        posr = s.read(1)
    assert excl[neg["row"], neg["col"]].sum() == 0 and posr[neg["row"], neg["col"]].sum() == 0
    assert not set(zip(pos["row"], pos["col"])) & set(zip(neg["row"], neg["col"]))


@pytest.mark.parametrize("a", ["0.05", "0.1", "0.2"])
def test_unit_tables(a):
    p = C.OUT / f"units_{a}.parquet"
    if not p.exists():
        pytest.skip("run `make aggregate` first")
    u = pd.read_parquet(p)
    assert u["unit"].is_unique and u["domain_share"].between(0, 1).all()
    m = u[u["in_model_domain"]]
    assert m["huc12"].notna().all() and m["slope_deg_mean"].notna().all()
    # p90 may be below the mean for very skewed units (a few cliff cells), so only the range is checked
    assert m["slope_deg_p90"].between(0, 90).all()
    assert u["n_sources"].sum() == 2582  # every in-county primary positive lies in exactly one unit
    frac = m[[c for c in m if c.startswith("lc_group_")]].sum(axis=1)
    assert np.allclose(frac, 1.0)
