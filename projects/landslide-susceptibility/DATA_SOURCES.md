# Landslide Susceptibility — Data sources

> Status: **M1 harvested 2026-10-09 (UTC)**; QA in [`validation/M1_DATA_QA.md`](validation/M1_DATA_QA.md).
> Earlier status: draft (2026-10-08). Each section records what was verified against the
> source on 2026-10-08 (feasibility queries returning attributes or headers only). "Planned" fields are filled by
> `make harvest`, which will write SHA-256 checksums, query URLs, counts and service edit dates to
> `provenance/harvest_manifest.json`.

**AOI (proposed):** Buncombe + Yancey counties, NC, + 2 km buffer; Watauga County for the temporal holdout.
**Target CRS:** NAD83 / UTM zone 17N, EPSG:26917, metres; NAVD88 metres.

**Reachability (`curl -I` / GET, 2026-10-08):**
- **Reached:** prd-tnm S3 and the TNM API; services2.arcgis.com (NCGS); maps.deq.nc.gov; services.nconemap.gov
  (some services token-protected, see below); sdmdataaccess (SSURGO); mrlc.gov; noaa-mrms-pds and noaa-eri-pds S3;
  tigerweb.geo.census.gov; data.fs.usda.gov (canopy); WA DNR download zip.
- **Blocked or failed:** www.sciencebase.gov blocks scripted access with a bot challenge; hazards.fema.gov failed
  (not needed).

**Licence summary:**
- **Public domain:** USGS (3DEP, WBD, NLCD), NOAA (MRMS, ERI) and USDA NRCS (SSURGO) are US Government works.
- **NC DEQ / NCGS:** free, no release agreement, no warranty.
- **NC OneMap orthoimagery** (2020–2023 and Helene 2025): the item licence points to the NC OneMap terms
  (https://www.nconemap.gov/pages/terms, read 2026-10-08 via the Hub page item e60514c3b78542ef9902e3d7f7a671c1).
  - **Terms:** "free and unrestricted use policy" for partner content; no written release required; no warranty;
    sale must not violate state law.
  - **Requested citation:** *NC OneMap (2019). North Carolina Department of Information Technology, Government
    Data Analytics Center, Center for Geographic Information and Analysis.*
  - **Helene 2025:** use constraints "None"; acknowledgement of the NC Collaboratory at UNC Chapel Hill
    "appreciated".
- **NC Composite Building Footprints:** **no licence stated** and not listed on NC OneMap. Local analysis only until
  terms are found; fallback Microsoft US Building Footprints (ODbL).

## Landslide Inventory of North Carolina (NCGS)

| Field | Value |
|---|---|
| Provider | North Carolina Geological Survey, NC DEQ |
| Official source URL | https://services2.arcgis.com/kCu40SDxsCGcuUWO/arcgis/rest/services/NC_Landslide_Inventory/FeatureServer (layer 2 "Landslide Features", polygons; layer 0 Observations, layer 1 Ground Ruptures); item 10209ea129584a548c957b7ad1a02249 |
| Dataset / version / vintage | live service; **snapshot frozen**: service `dataLastEditDate` 2026-10-08T18:54:29+00:00, acquired 2026-10-09T05:30:19+00:00; 26,050 features in the harvest bbox (layer 2), plus Observations (7,341) and Ground Ruptures (158). Absorbed the former "North Carolina Post Helene Landslide Inventory" service (deprecated, offline in 2027) |
| Acquisition date | 2026-10-09 (UTC); feasibility queries 2026-10-08 |
| License | NC DEQ: geospatial data offered at no charge; no written release agreement required; no warranty; sale must not violate state law. Access info: "NC Geological Survey" |
| AOI | statewide service; harvested for the bbox of both buffered regions (AOI + Watauga) |
| Source CRS → target CRS | service SR 103122 / 6543 (NC State Plane, US ft) → requested as needed → EPSG:26917 |
| Resolution / scale | interpretive mapping; positional quality given by `LocationConfidence` |
| Preprocessing (implemented in `landslide.inventory`, tested) | normalize `AssociatedStorm` (three Helene spellings); positives = Helene `Source Area`/`Source Area (Reactivated)`, `SlopeModifier = None Apparent`, existence + location confidence High/Moderate; all other features become exclusion zones |
| Output format / path | `data/raw/ncgs_features.parquet`, `ncgs_observations.parquet`, `ncgs_ground_ruptures.parquet` (GeoParquet, EPSG:4326 as served) |
| Checksum or version pin | manifest `sources.ncgs_features.sha256` + service edit date; QA test asserts 2,962 AOI positives |
| Known limitations / biases | 3 invalid geometries (2 Helene outlines, 1 transport zone — none are positives; repaired with `make_valid` in M3) and 5 exact duplicate geometries; live and growing; "currently incomplete" per NCGS; detection bias toward larger / canopy-free failures likely; mapping extent not published |

Verified counts (2026-10-08):

| Item | Count |
|---|---|
| Total polygons | 29,993 |
| Helene | 21,895 |
| Undated | 5,774 |
| Aug 1940 storm (Watauga 1,217) | 1,241 |
| Other dated | ~520 |
| FeatureType: Source Area | 10,055 |
| FeatureType: Outline | 9,595 |
| FeatureType: Deposit | 6,368 |
| FeatureType: Transport Zone | 3,757 |
| FeatureType: Source Area (Reactivated) | 217 |
| Helene natural source areas, High/Moderate confidence: Buncombe | 1,815 |
| Helene natural source areas, High/Moderate confidence: Yancey | 1,156 |
| Mapping basis of AOI natural source areas: "2025 UNC Collaboratory imagery & 2025 NCGS LCD" | 2,970 of 2,971 |

Size of natural Helene source polygons (n = 4,752): median 84 m², IQR 45–152 m², p95 400 m².

## USGS 3DEP 1 m DEM

| Field | Value |
|---|---|
| Provider | U.S. Geological Survey, 3D Elevation Program |
| Official source URL | https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/NC_Phase5_2018_A18/ (found via TNM Access API) |
| Dataset / version / vintage | **AOI:** 54 tiles — NC_Phase5_2018_A18 (48; lidar 2017-02-11 → 2017-04-11) + TN_Eastern_2_16_B16_Del4_2016 (6; 2016-02-05 → 2016-04-04; Tennessee side of the buffer only). **Watauga:** 29 tiles — NC_Phase5 (18), NC_Phase4_2017_A17 (5; 2016-02-27 → 2017-10-30), TN (6). Dates read per tile from FGDC metadata; **all pre-event** |
| Acquisition date | 2026-10-09; 24.2 GB transferred, tiles deleted after aggregation |
| License | public domain |
| AOI | AOI + 2 km buffer; Watauga |
| Source CRS → target CRS | EPSG:26917 (verified), NAVD88 m → unchanged |
| Resolution / scale | 1 m (10,012 × 10,012 px tiles with 6 m overlap; float32; nodata −999999; overviews 2–32) → 5 m `average` |
| Preprocessing | per-tile download → exact 5 × 5 block mean on the UTM 5 m lattice (strict nodata) → delete raw; first-valid mosaic with project priority NC Phase 5 > NC Phase 4 > TN. Seams: no vertical offset (|median| ≤ 0.09 m); worst p99 |Δ| 0.88 m, ≤ 0.8 % of overlap cells > 1 m, all on cross-project overlaps (2016 vs 2017 lidar) |
| Output format / path | `data/interim/dem_5m_aoi.tif` (14,499 × 15,575), `dem_5m_watauga.tif` (9,095 × 6,997); per-tile `data/interim/dem5_tiles/`; metadata `data/raw/dem_meta/` |
| Checksum or version pin | manifest: SHA-256 of every 1 m tile (streamed) and 5 m product |
| Known limitations / biases | terrain as of 2016–2017; later cuts and grading not represented; interpolated under structures and water; no nodata inside counties or buffer (QA). Elevation 398–2,037 m (AOI) |

## Geologic Map of North Carolina (1985)

| Field | Value |
|---|---|
| Provider | NC Geological Survey |
| Official source URL | https://services2.arcgis.com/kCu40SDxsCGcuUWO/arcgis/rest/services/Geologic_Map_of_North_Carolina/FeatureServer (layer 3 "Map Units": MapUnit, Name, Description) |
| Dataset / version / vintage | 1985 state geologic map |
| Acquisition date | 2026-10-09 (283 map-unit polygons in the harvest bbox) |
| License | NC DEQ terms (as above) |
| Resolution / scale | 1:500,000 — coarse relative to 5 m; used as lithology groups only |
| Preprocessing (planned, M3) | group map units into ~5 lithology classes; rasterize by cell centre |
| Known limitations / biases | scale mismatch; contacts uncertain by hundreds of metres |

## SSURGO (USDA NRCS) via Soil Data Access

| Field | Value |
|---|---|
| Provider | USDA NRCS |
| Official source URL | https://sdmdataaccess.sc.egov.usda.gov/ (POST endpoint verified) |
| Dataset / version / vintage | current county surveys; survey versions in the manifest (`survey_version`) |
| License | public domain |
| Preprocessing | M1: map-unit polygons (NC021 35,176; NC199 14,695; NC189 14,846) + `muaggatt` brockdepmin, hydgrpdcd, aws0100wta, wtdepannmin, and muname (kept for audit, never a predictor). `brockdepmin` is null for 46–53 % of polygons, which in SSURGO means no bedrock recorded within the described depth (≈ 2 m) — to be coded as "> described depth", not missing (M3). Clay % not yet harvested (M3 if retained) |
| Known limitations / biases | map units partly defined by slope class → collinear with slope; tested with/without soils |

## NLCD 2021 Land Cover; NLCD Tree Canopy Cover 2021 (MRLC WCS)

| Field | Value |
|---|---|
| Provider | USGS / MRLC; USDA Forest Service |
| Official source URL | https://www.mrlc.gov/ ; https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/ (reached) |
| Dataset / version / vintage | WCS coverages `mrlc_download__NLCD_2021_Land_Cover_L48` and `mrlc_download__nlcd_tcc_conus_2021_v2021-4` (native EPSG:5070, 30 m; GetCoverage with X/Y subset verified 2026-10-08). Annual NLCD 2023 is not offered per year in the WCS |
| License | public domain |
| Resolution / scale | 30 m → 5 m (`nearest` for classes, `bilinear` for canopy) |
| Known limitations / biases | 30 m mixed pixels on narrow ridges/hollows. Canopy GeoTIFF declares nodata = 0, but 0 is a valid 0 % canopy; its real no-data flag is 254 (0.011 % of AOI cells) — handled in M3 |

## NOAA MRMS MultiSensor QPE 72 h (Pass 2)

| Field | Value |
|---|---|
| Provider | NOAA / NSSL MRMS, AWS Open Data |
| Official source URL | https://noaa-mrms-pds.s3.amazonaws.com/CONUS/MultiSensor_QPE_72H_Pass2_00.00/20240928/ (files listed) |
| Dataset / version / vintage | two 72 h accumulations ending 2024-09-28 00Z and 12Z; the cell-wise maximum is used (covers 25 Sep 00Z → 28 Sep 12Z; harvested 2026-10-09) |
| License | public domain |
| Resolution / scale | ~1 km; GRIB2 (GDAL GRIB driver verified in the rasterio wheel) |
| Use | trigger stratification and contrast model only — never a susceptibility predictor |
| Known limitations / biases | radar beam blockage in mountains; gauge correction sparse |

## USGS Watershed Boundary Dataset (HUC-12 / HUC-10)

| Field | Value |
|---|---|
| Provider | USGS |
| Official source URL | https://prd-tnm.s3.amazonaws.com/StagedProducts/Hydrography/WBD/HU2/GPKG/WBD_06_HU2_GPKG.zip (HTTP 200; region 05 also needed for Yancey/Watauga — to check) |
| License | public domain |
| Use | spatial cross-validation groups, reporting |

## Reference products (comparison only)

| Field | USGS slope-relief susceptibility | NCGS Channelized Debris Flow Model |
|---|---|---|
| Source | Belair, Jones, Martinez, Mirus, Wood (2024), doi:10.5066/P13KAGU3 (ScienceBase item 65ccea5bd34ef4b119cb3bac) | https://maps.deq.nc.gov/arcgis/rest/services/DEMLR/North_Carolina_Channelized_Debris_Flow_Model/MapServer (layer 0 "Source Area and Transport Path") |
| Vintage | Aug 2024 — before Helene | ArcGIS item created **2025-04-28** (after Helene), modified 2026-06-25; inputs and calibration not documented → **not a pre-event reference**; if used at all, labelled as a post-event product that may reflect Helene |
| What it measures | national slope/relief-threshold susceptibility, 90 m, all landslide types | channelized debris-flow initiation and run-out paths for storms ≥ ~5 in / 24 h; NCGS: "significantly more false positives than true positives" |
| Licence | public domain | NC DEQ terms |
| Access | **ScienceBase blocks scripted download** → optional manual download; never blocks the pipeline (owner decision) | map service has **Map capability only (no Query)**: vector data cannot be retrieved; only a rendered export is possible → comparison decided in M4 (rendered export documented as such, or dropped) |

## Exposure data (used only after validation)

| Field | NC Composite Building Footprints | NCDOT Road Characteristics / TIGER/Line |
|---|---|---|
| Source | https://services1.arcgis.com/YBWrN5qiESVpqi92/arcgis/rest/services/North_Carolina_Composite_Building_Footprints/FeatureServer — **harvested 2026-10-09 for the buffered AOI only: 160,651 footprints, local use only** | TIGER/Line 2024 roads per county (harvested: 37021 13,820; 37199 3,738; 37189 4,685 segments; EPSG:4269); NCDOT service reached but not used yet |
| Vintage | 2022 (Northern Mountains) / 2023 (Southern Mountains) orthos — pre-event; primary structures ≥ 800 ft² | quarterly / annual |
| Licence | **no licence stated** (NC DPS–EM, DOA; item licence field empty) — local use only until resolved | NCDOT: to check; TIGER: public domain |

## Display-only imagery (never model inputs)

| Field | NC Orthoimagery 2020–2023 (pre) | NC Orthoimagery Helene 2025 (post) | NOAA ERI Helene (fallback post) |
|---|---|---|---|
| Source | https://services.nconemap.gov/secure/rest/services/Imagery/Orthoimagery_2020_2023/ImageServer | …/Imagery/Orthoimagery_Helene_2025/ImageServer | s3://noaa-eri-pds/2024_Hurricane_Helene/ (flights 2024-10-05 → 10-08 cover the AOI bbox, ~1,700 tiles) |
| Vintage / conditions | 2020–2023 cycle, leaf-off, 6 in, RMSE 1.0 ft | spring 2025, leaf-off, 6 in, 4-band; Buncombe, Yancey, Watauga covered in full | Oct 2024, leaf-on, ~0.15 m, EPSG:4326, tiled GeoTIFF with overviews |
| Access | `exportImage` works without token (verified 256 px); year-specific services 2022/2023 require a token | same | public S3, windowed reads |
| Licence | NC OneMap terms: free and unrestricted use, citation requested (item `licenseInfo` → terms page) | NC OneMap terms; use constraints "None"; acknowledge NC Collaboratory at UNC Chapel Hill | public domain (U.S. Government) |
| Use | curated-site before/after swipe only | same | fallback for "post" |

The Helene "Priority 1" lidar (2025) is named in the post-event imagery description. It was not found in the TNM
API on 2026-10-08 and again on 2026-10-09 (only NC_Phase5_2018_A18 and legacy point clouds over Yancey). The pre/post lidar
swipe is therefore shelved until a public release exists.
