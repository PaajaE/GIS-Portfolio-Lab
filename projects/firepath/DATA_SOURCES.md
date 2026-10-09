# FirePath — Data sources

Required fields follow spec §3 "Provenance". **Status: planning (2026-10-09).** Nothing has been harvested
except one feasibility sample (HRRR, below). Fields not yet established are marked *to verify (M0)*; the
reachability probe on the build Mac (`make probe`) and the harvest manifest will fill them.

Reachability from the planning session (a cloud container, **not** the build Mac): only AWS S3 (HRRR) was
reachable; landfire.gov, lfps.usgs.gov, edcintl.cr.usgs.gov, services3.arcgis.com,
firms.modaps.eosdis.nasa.gov, northwestknowledge.net, census.gov and tnmaccess.nationalmap.gov were refused
by that session's egress proxy (HTTP 403). This says nothing about the Mac.

**Target CRS:** NAD83 / UTM 12N (EPSG:26912), metres, 30 m grid per fire (PLAN §5).

## NOAA HRRR analyses (f00)

| Field | Value |
|---|---|
| Provider | NOAA NCEP / GSL, via NOAA Open Data Dissemination on AWS |
| Official source URL | https://noaa-hrrr-bdp-pds.s3.amazonaws.com/ (`hrrr.YYYYMMDD/conus/hrrr.tHHz.wrfsfcf00.grib2` + `.idx`) |
| Dataset / version / vintage | HRRR (v3 until Dec 2020, v4 after — *to record per fire*), hourly analyses for the fire period only |
| Acquisition date | Feasibility sample 2026-10-09 (UGRD 10 m, 2022-04-19 21 UTC, byte range from `.idx`; sha256 `e56bd29566ca9ef260b8d5eaf0910ede95b0d0b13d927960fb042c42a9384905`) |
| License | U.S. Government work (public domain) — *confirm wording on the AWS registry page (M0)* |
| AOI | per-fire grid + margin |
| Source CRS → target CRS | Lambert conformal 3 km (GRIB2 template 3.30, 1799 × 1059) → UTM 12N; **U/V are grid-relative (flag `00001000`, verified)** → rotate to earth-relative, then to UTM grid-relative, then bilinear to a 300 m wind grid |
| Resolution / scale | 3 km, hourly |
| Preprocessing | byte-range fetch of UGRD/VGRD 10 m, TMP/RH 2 m, GUST; crop; rotate; 10 m → 20 ft (÷ 1.15) |
| Output format / path | `data/raw/<fire>/hrrr/`, `data/interim/<fire>/wind_*.npz` |
| Checksum or version pin | sha256 per downloaded message in the manifest |
| Known limitations / biases | ambient wind at 3 km — no terrain channelling or fire-induced winds |

## LANDFIRE fuels (FBFM40, CC, CH, FDist)

| Field | Value |
|---|---|
| Provider | LANDFIRE (USGS EROS / USDA Forest Service) |
| Official source URL | https://landfire.gov/ ; LANDFIRE Product Service (LFPS) — *endpoint and email requirement to verify (M0)* |
| Dataset / version / vintage | version whose last disturbance year precedes the fire: LF 2019 Limited or LF 2016 Remap (2020 fires), LF 2020 / 220 (2021–2022 fires) — *to verify* |
| Acquisition date | not yet |
| License | public domain, credit requested — *confirm (M0)* |
| AOI | per fire |
| Source CRS → target CRS | EPSG:5070 (Albers) → EPSG:26912, nearest (categorical) |
| Resolution / scale | 30 m |
| Preprocessing | nearest warp; class-proportion check; leakage check against FDist |
| Output format / path | `data/interim/<fire>/fuel.tif` etc. |
| Checksum or version pin | LANDFIRE version code + sha256 |
| Known limitations / biases | map accuracy limits; disturbances after the version's cutoff missing ("stale fuels") |

## USGS 3DEP DEM

| Field | Value |
|---|---|
| Provider | USGS 3D Elevation Program |
| Official source URL | *TNM Access API / prd-tnm S3 — to verify (M0)* |
| Dataset / version / vintage | 1/3 arc-second seamless; source-date footprint to record |
| License | public domain |
| Source CRS → target CRS | NAD83 geographic → EPSG:26912, averaged to 30 m before slope |
| Known limitations / biases | mosaic of source dates |

## Observed perimeters (NIROPS IR; NIFS/WFIGS; MTBS)

| Field | Value |
|---|---|
| Provider | USFS National Infrared Operations via NIFC FTP; NIFC (NIFS Operational Data Archive, WFIGS); MTBS (USGS EROS / USFS GTAC) |
| Official source URL | https://ftp.wildfire.gov/public/incident_specific_data/ ; NIFC Open Data hub; https://www.mtbs.gov/ — *to verify (M0)* |
| Dataset / version / vintage | per fire; screening index: Magstadt et al., Mendeley Data doi:10.17632/95rj5d379g.1 (NIROPS 2020–2024, R1–R6) — licence *to verify* |
| License | NIFC FTP content is public, non-copyrighted (FTP posting rules); MTBS public domain — *confirm* |
| Known limitations / biases | IR perimeters are interpreted heat edges at scan time; NIFS `GDB_FROM` is an edit time, not an observation time; MTBS outlines include unburned islands (commission) |

## NASA FIRMS active fire (VIIRS 375 m, MODIS 1 km)

| Field | Value |
|---|---|
| Provider | NASA LANCE / FIRMS |
| Official source URL | https://firms.modaps.eosdis.nasa.gov/ — API requires a MAP_KEY (open question Q2) |
| Use | timing proxy, comparison only (PLAN §2.4) |
| Known limitations / biases | overpass-limited timing; pixel ≫ cell; omission under cloud/smoke/low intensity |

## gridMET

| Field | Value |
|---|---|
| Provider | Climatology Lab (J. Abatzoglou) |
| Variables | fm100, fm1000, ERC (daily, ≈ 4 km) |
| License | public domain per the Earth Engine catalogue entry — *confirm at primary source (M0)*; cite Abatzoglou (2013) |

## Census TIGER/Line roads, 2020 census blocks (TABBLOCK20), USA Structures

| Field | Value |
|---|---|
| Provider | U.S. Census Bureau; FEMA/ORNL (structures) |
| License | public domain (U.S. Government works); chosen instead of OSM (ODbL share-alike) |
| Use | network graph and population exposure (PLAN §11), only after validation |
| Known limitations / biases | TIGER road positional accuracy and class-based speeds; block population assigned to the nearest road node (MAUP); structures layer optional (FEMA hosts previously unreachable) |
