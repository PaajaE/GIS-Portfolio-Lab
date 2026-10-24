"""Extra cell samples for the M4 checks (PLAN §6, §8), from the M3 label rasters.

* domain_sample.parquet: a seeded uniform sample of the whole triggered domain, *including* excluded cells
  (near mapped features or roads) and positives, with their flags. It gives the negative-sample bias check:
  the model is also scored against unrestricted domain cells, not only against the exclusion-filtered pool.
* positives_runoff.parquet: cells of the natural-slope, runoff-modified Helene source areas (the 380 polygons
  that separate the primary rule from the slope-only variant). Primary + these = the variant positives; the
  M3 negative pool already excludes them (+30 m), so the pool serves both rules.
"""

from __future__ import annotations

import json

import numpy as np
from rasterio.features import rasterize

from . import config as C
from .inventory import positive_mask
from .labels import REGION, counties, dem_grid, inventory, positives_raster, read, sample_tables

DOMAIN_SAMPLE = 200_000


def run() -> dict:
    tr, shape = dem_grid()
    d = C.INTERIM / f"labels_{REGION}"
    dom = read(d / "domain.tif").astype(bool)
    flags = {"positive": read(d / "positive.tif"), "exclusion": read(d / "exclusion.tif"),
             "hillslope": read(d / "hillslope.tif")}
    cty = counties()
    flags["county"] = rasterize(((g, i + 1) for i, g in enumerate(cty.geometry)),
                               out_shape=shape, transform=tr, fill=0, dtype=np.uint8)
    inv = inventory()
    in_cty = inv.geometry.representative_point().within(cty.union_all())
    runoff = inv[positive_mask(inv, require_natural_runoff=False) & ~positive_mask(inv) & in_cty]
    rmask, fallback = positives_raster(runoff, tr, shape)
    rmask &= dom & ~flags["positive"].astype(bool)
    rng = np.random.default_rng(C.SEED + 4)
    dom_idx = np.sort(rng.choice(np.flatnonzero(dom.ravel()), size=DOMAIN_SAMPLE, replace=False))
    run_idx = np.flatnonzero(rmask.ravel())
    del dom, rmask
    tables = sample_tables({"domain_sample": (dom_idx, -1), "positives_runoff": (run_idx, 1)}, flags, tr, shape)
    for name, df in tables.items():
        df.to_parquet(d / f"{name}.parquet", index=False)
    rep = {"domain_sample": int(dom_idx.size), "domain_sample_seed": C.SEED + 4,
           "runoff_polygons": int(len(runoff)), "runoff_polygons_fallback": int(fallback),
           "runoff_cells_in_domain": int(run_idx.size),
           "domain_sample_shares": {k: float(tables["domain_sample"][k].astype(bool).mean())
                                    for k in ("positive", "exclusion", "hillslope")}}
    (d / "samples_report.json").write_text(json.dumps(rep, indent=1))
    print(rep, flush=True)
    return rep


if __name__ == "__main__":
    run()
