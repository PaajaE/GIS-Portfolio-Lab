# Parcel Intelligence — Data sources

Required fields follow spec §3 "Provenance". Machine-readable details (query URLs, feature counts,
service edit dates, SHA-256 of every raw file) are in [`provenance/harvest_manifest.json`](provenance/harvest_manifest.json),
written by `make harvest`. All data were acquired on **2026-10-08** (UTC) for the AOI below.

**AOI (all layers):** Town of Amherst, MA (MassGIS town id 8) plus a 250 m buffer, so that buffers and
neighbourhood kernels near the town line see constraints across it. Parcels: Amherst only.
**Target CRS:** NAD83 / Massachusetts Mainland, EPSG:26986, metres. Vector layers are requested from the
services in EPSG:4326 (GeoJSON) and reprojected locally with PROJ 9.8.1.

**Licence summary.** MassGIS states that, being funded by taxpayers, its data are in the public domain and
may be used for any purpose; it asks for the credit line *MassGIS (Bureau of Geographic Information),
Commonwealth of Massachusetts EOTSS* ([MassGIS FAQ](https://www.mass.gov/info-details/massgis-frequently-asked-questions)).
USGS 3DEP and FEMA NFHL are U.S. Government works (public domain). No share-alike obligations apply to the derived outputs.
The web app credits every provider.

## Assessor parcels (MassGIS Level 3)

| Field | Value |
|---|---|
| Provider | MassGIS, from municipal assessor (Town of Amherst) |
| Official source URL | https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Massachusetts_Property_Tax_Parcels/FeatureServer/0 ([dataset page](https://www.mass.gov/info-details/massgis-data-property-tax-parcels)) |
| Dataset / version / vintage | Level 3 standardized parcels, assessor fiscal year FY2026; service last edited 2026-10-07 |
| Acquisition date | 2026-10-08 |
| License | Public domain (MassGIS); credit requested |
| AOI | `TOWN_ID = 8` |
| Source CRS → target CRS | Web Mercator service, requested as EPSG:4326 → EPSG:26986 |
| Resolution / scale | Assessor tax-map compilation; not survey-grade |
| Preprocessing | `POLY_TYPE = FEE` only (10 ROW polygons dropped); 7,330 polygons → 6,091 parcels by `LOC_ID` (stacked condominium copies verified identical, then merged); use code / description / zoning from one representative record (highest assessed value); `any_exempt` flag if any record is tax-exempt; **owner names and owner addresses are not harvested** |
| Output format / path | `data/interim/parcels.parquet` (GeoParquet); results in `data/out/parcels.parquet`, `web/data/downloads/` |
| Checksum | see manifest (`sources.parcels.sha256`) |
| Known limitations / biases | Assessor maps are not authoritative boundaries; MassGIS notes that only a survey or deed establishes them; assessor use codes and zoning codes are as-is extracts |

## Lidar DEM (USGS 3DEP 1 m)

| Field | Value |
|---|---|
| Provider | U.S. Geological Survey, 3D Elevation Program |
| Official source URL | https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/MA_Western_B24/TIFF/ (tiles `USGS_1M_18_x70y469/470/471_MA_Western_B24.tif`, found via the TNM Access API) |
| Dataset / version / vintage | 1 m DEM, project MA_Western_B24, published 2026-03-20. Lidar collection date not verified here |
| Acquisition date | 2026-10-08 (windowed reads of the COG tiles; only the AOI was transferred) |
| License | Public domain (U.S. Government work) |
| AOI | AOI + 50 m |
| Source CRS → target CRS | EPSG:26918 (NAD83 / UTM 18N), NAVD88 metres → EPSG:26986, 2 m |
| Resolution / scale | 1 m source → 2 m analysis grid (mean of source cells, GDAL warp `average`) |
| Preprocessing | Merge of 3 tiles (`rasterio.merge`), reprojection with averaging; slope by Horn (1981) 3×3 in percent; nodata propagated (any nodata in the window → nodata) |
| Output format / path | `data/raw/dem_1m_utm18.tif`, `data/interim/dem_2m.tif`, `data/interim/slope_pct.tif` (GeoTIFF, deflate) |
| Checksum | manifest `sources.dem.sha256` |
| Known limitations / biases | Bare-earth surface is post-construction (graded pads look flat) and interpolated under buildings; no nodata inside the AOI (verified) |

## FEMA National Flood Hazard Layer

| Field | Value |
|---|---|
| Provider | FEMA; republished by MassGIS |
| Official source URL | https://arcgisserver.digital.mass.gov/arcgisserver/rest/services/FEMA/FEMA_National_Flood_Hazard_Layer/FeatureServer/0 |
| Dataset / version / vintage | `FEMA_NFHL_POLY`, "data published by FEMA as of July 2, 2023"; DFIRM 250156, version 2.3.3.0 |
| Acquisition date | 2026-10-08 |
| License | Public domain (U.S. Government work) |
| AOI | AOI envelope |
| Source CRS → target CRS | EPSG:26986 service, requested as EPSG:4326 → EPSG:26986 |
| Resolution / scale | FIRM database, horizontal spec consistent with 1:12,000 |
| Preprocessing | Floodway = `ZONE_SUBTY = FLOODWAY`; SFHA = `SFHA_TF = 'T'` (zones A, AE); 0.2% = `ZONE_SUBTY` "0.2 PCT ANNUAL CHANCE FLOOD HAZARD" |
| Output format / path | `data/interim/flood.parquet`; `web/data/context.pmtiles` layer `flood` |
| Checksum | manifest `sources.flood.sha256` |
| Known limitations / biases | **Vintage 2023-07-02.** FEMA's own services (hazards.fema.gov, msc.fema.gov) refused connections from the build machine, so later LOMRs/revisions are not included. A regulatory map, not observed flooding |

## MassDEP Wetlands (1:12,000)

| Field | Value |
|---|---|
| Provider | MassDEP Wetlands Conservancy Program, via MassGIS |
| Official source URL | https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/DEP_Wetlands/FeatureServer/1 |
| Dataset / version / vintage | DEP Wetland Areas (photo-interpreted, 1990s–2000s base with updates); service last edited 2026-04-08 |
| Acquisition date | 2026-10-08 |
| License | Public domain (MassGIS) |
| AOI | AOI envelope |
| Source CRS → target CRS | EPSG:26986 → (4326) → EPSG:26986 |
| Resolution / scale | 1:12,000 |
| Preprocessing | All wetland classes incl. open water (`IT_VALC`); buffered by the scenario wetland setback with GEOS |
| Output format / path | `data/interim/wetlands.parquet` |
| Checksum | manifest |
| Known limitations / biases | Mapped wetlands are not field delineations; small or forested wetlands are under-mapped |

## MassDEP Hydrography (1:25,000)

| Field | Value |
|---|---|
| Provider | MassDEP / USGS / MassGIS |
| Official source URL | https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/1_25_000_USGS_MassDEP_Hydrography/FeatureServer (layers 0 arcs, 1 water bodies); codes: [dataset page](https://www.mass.gov/info-details/massgis-data-massdep-hydrography-125000) |
| Dataset / version / vintage | Service last edited 2026-04-09 |
| Acquisition date | 2026-10-08 |
| License | Public domain (MassGIS) |
| AOI | AOI envelope |
| Source CRS → target CRS | EPSG:26986 → (4326) → EPSG:26986 |
| Resolution / scale | 1:25,000 (some local 1:12,000) |
| Preprocessing | Arcs `ARC_CODE` 4 = perennial stream, 5 = intermittent, 6 = ditch/canal, 11 = channel in water; perennial and other streams buffered separately; water bodies buffered like wetlands |
| Output format / path | `data/interim/streams.parquet`, `waterbodies.parquet` |
| Checksum | manifest |
| Known limitations / biases | Streams added from watershed redelineation default to intermittent; perennial status here is not a regulatory determination |

## Protected and Recreational Open Space

| Field | Value |
|---|---|
| Provider | MassGIS / EEA |
| Official source URL | https://arcgisserver.digital.mass.gov/arcgisserver/rest/services/AGOL/openspace/FeatureServer/0 |
| Dataset / version / vintage | Continuously maintained; acquired 2026-10-08 |
| Acquisition date | 2026-10-08 |
| License | Public domain (MassGIS) |
| AOI | AOI envelope |
| Source CRS → target CRS | EPSG:26986 → (4326) → EPSG:26986 |
| Resolution / scale | Parcel-based compilation |
| Preprocessing | `LEV_PROT` P (perpetuity) excluded in all scenarios; T (term-limited) and L (limited) also in conservative; one invalid polygon repaired (`make_valid`) |
| Output format / path | `data/interim/openspace.parquet` |
| Checksum | manifest |
| Known limitations / biases | Level of protection is as recorded by MassGIS; conservation restrictions may be incomplete |

## NHESP Priority Habitats of Rare Species

| Field | Value |
|---|---|
| Provider | MassWildlife Natural Heritage & Endangered Species Program, distributed by MassGIS |
| Official source URL | https://s3.us-east-1.amazonaws.com/download.massgis.digital.mass.gov/shapefiles/state/prihab.zip |
| Dataset / version / vintage | 15th Ed. Massachusetts Natural Heritage Atlas, effective 2021-08-01 |
| Acquisition date | 2026-10-08 (statewide zip, clipped to AOI, zip discarded) |
| License | Distributed by MassGIS (public domain statement); cite NHESP |
| AOI | intersects AOI (16 polygons) |
| Source CRS → target CRS | EPSG:26986 → (4326) → EPSG:26986 |
| Resolution / scale | Generalized habitat polygons |
| Preprocessing | Excluded only in the conservative scenario |
| Output format / path | `data/interim/prihab.parquet` |
| Checksum | manifest |
| Known limitations / biases | Priority habitat triggers regulatory review (MESA), not a prohibition |

## MassDOT Roads

| Field | Value |
|---|---|
| Provider | MassDOT, via MassGIS |
| Official source URL | https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/MassDOTRoads_gdb/FeatureServer/0 |
| Dataset / version / vintage | Road inventory; service last edited 2026-02-04 |
| Acquisition date | 2026-10-08 |
| License | Public domain (MassGIS) |
| AOI | AOI envelope |
| Source CRS → target CRS | EPSG:26986 → (4326) → EPSG:26986 |
| Resolution / scale | Centrelines |
| Preprocessing | Road surface = centreline buffered by an **assumed** half-width by `CLASS` (2: 9 m, 3/4: 6 m, 5/6: 4 m); public roads = `JURISDICTN` 1 (MassDOT) or 2 (town-accepted) |
| Output format / path | `data/interim/roads.parquet` |
| Checksum | manifest |
| Known limitations / biases | Surface width not harvested; cul-de-sac bulbs are not represented by centrelines |

## Building Structures

| Field | Value |
|---|---|
| Provider | MassGIS (Rolta 2011 base, updated) |
| Official source URL | https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Building_Structures/FeatureServer/0 |
| Dataset / version / vintage | Mostly 2011 imagery (8,528 of 9,306 in AOI), updates to 2025; service last edited 2026-05-22 |
| Acquisition date | 2026-10-08 |
| License | Public domain (MassGIS) |
| AOI | AOI envelope |
| Source CRS → target CRS | EPSG:26986 → (4326) → EPSG:26986 |
| Resolution / scale | Roof-line footprints |
| Preprocessing | Rasterized at cell centres as "existing development" |
| Output format / path | `data/interim/buildings.parquet` |
| Checksum | manifest |
| Known limitations / biases | Recent construction may be missing |

## Sewer service areas

| Field | Value |
|---|---|
| Provider | MassDEP Water Utility Resilience Program |
| Official source URL | https://arcgisserver.digital.mass.gov/arcgisserver/rest/services/AGOL/DEP_SEWER_SERVICE_AREAS/FeatureServer/2 |
| Dataset / version / vintage | PubV2025_10; Amherst service area confirmed 2024 |
| Acquisition date | 2026-10-08 |
| License | Public domain (MassGIS) |
| AOI | AOI envelope |
| Source CRS → target CRS | EPSG:26986 → (4326) → EPSG:26986 |
| Resolution / scale | Service-area polygons |
| Preprocessing | Share of each parcel inside the Amherst POTW area; **reported, not used as a constraint** |
| Output format / path | `parcels.parquet` column `sewer_share` |
| Checksum | manifest |
| Known limitations / biases | Service area ≠ capacity or a connection right |

## Town boundary

| Field | Value |
|---|---|
| Provider | MassGIS |
| Official source URL | https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/TOWNSSURVEY_POLYM/FeatureServer/0 |
| Dataset / version / vintage | Community boundaries from survey points; service last edited 2020-03-05 |
| Acquisition date | 2026-10-08 |
| License | Public domain (MassGIS) |
| AOI | `TOWN_ID = 8` |
| Source CRS → target CRS | (4326) → EPSG:26986 |
| Preprocessing | AOI = boundary + 250 m; 2 m grid snapped to whole cells |
| Output format / path | `data/interim/town.parquet`, `grid.json` |
| Checksum | manifest |
| Known limitations / biases | — |

## Web-only assets

- Noto Sans Regular glyph range 0–255 (`web/fonts/`), SIL Open Font License 1.1, from protomaps/basemaps-assets.
- MapLibre GL JS 6.11.1 (BSD-3-Clause) and PMTiles 4.5.0 (BSD-3-Clause), loaded from jsDelivr at pinned versions.
