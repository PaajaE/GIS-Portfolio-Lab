# FirePath: how the data were obtained

This document records how every input was obtained: the route that worked, the routes that failed or are
closed, and what had to be done by hand. `DATA_SOURCES.md` holds the per-source reference fields
(licence, CRS, limitations). The `provenance/*.json` files record the URL, size, sha256 and retrieval
time of each downloaded file. Status: 2026-10-26.

## Principles

- **Open data only, no accounts in the code.** Every automated download uses a public endpoint without
  login. Where a provider needs a key (NASA FIRMS), the key sits only in the git-ignored
  `projects/firepath/.env` and never in code, commits or logs (`probe.py` redacts it).
- **Download only what the fire needs.** Each fire gets an area of interest (AOI): the union of its
  observed perimeters plus 5 km, on a 30 m UTM grid (`data/interim/<fire>/grid.json`). Every source is
  cut to that box at download time, through HTTP byte ranges, server-side subsetting or windowed reads.
  No national mosaic is stored, except the three LANDFIRE 2020 zips (below).
- **Nothing from after the prediction time.** Fuels come from the LANDFIRE version made *before* the
  fire. Weather is limited to the fire period, and perimeters are used as targets only after the start
  time (PLAN §3). This is checked automatically (see "Leakage checks").
- **Everything is reproducible.** `make harvest FIRE=<fire>` and `make prepare FIRE=<fire>` rebuild a fire
  from nothing. Raw and intermediate data (`data/`) are not committed; the manifests are.

## Where it ran

The work was split between two machines:

| Machine | Role |
|---|---|
| Build Mac (owner's MacBook) | Reachability probe (`provenance/probe_build-mac.json`); harvest and prepare of Telegraph, Pipeline and Cerro Pelado; the Internet Archive fetch for Telegraph; the hand downloads |
| Cloud session (Claude Code) | Code, tests and documents; harvest and prepare of Mangum and Bush; model runs and benchmarks so far |

The cloud session sits behind an egress proxy that refuses some hosts, including landfire.gov,
web.archive.org and synopticdata.com. Anything that needed those hosts ran on the Mac.

## Source by source

### 1. Observed fire perimeters (the targets)

- **What:** airborne infrared (NIROPS) perimeters, one per night-time flight, with the scan time.
- **Route used:** Magstadt et al., *NIROPS 2020–2024, USFS Regions 1–6*, Mendeley Data,
  doi:10.17632/95rj5d379g.1 (CC BY 4.0). The dataset is one large zipped shapefile.
  - `harvest.py` reads it **in place over HTTP range requests**: the zip directory first, then only the
    `.dbf/.shx/.shp` bytes of the pool incidents. It streams the deflate data and decodes polygons from
    the `.shx` offsets.
  - Result: `data/raw/perimeters/nirops_mendeley_pool.geojson`.
  - The full inventory with scan times for all pool fires is in
    `provenance/nirops_mendeley_inventory.json`.
- **Scan time:** `DateFlown + TimeFlown` shifted to UTC by the dataset's time-zone label. Arizona has no
  daylight saving time, so a mislabelled zone would be 1 h off (accepted as ±1 h, criterion S2).
- **Closed routes:**
  - The NIFC FTP archive (`ftp.wildfire.gov/protected/…`) has required a FAMAuth login since
    2026-05-04.
  - The NIFC "Operational Data Archive" on ArcGIS Online is reachable. Its `PolygonDateTime` is an edit
    time, not the scan time, so it is used only for cross-checks (`M0_RESULTS.md` B2).

### 2. Fuels: LANDFIRE FBFM40, canopy cover (CC), canopy height (CH)

- **Rule:** the newest LANDFIRE version whose last disturbance year is **before** the fire year.
  - 2020 fires (Bush, Mangum): **LF 2016 Remap**.
  - 2021–2022 fires (Telegraph, Pipeline, Cerro Pelado): **LF 2020**.
  - LF 2022 is never used for them: it already contains their own burn scars.
- **LF 2016, automated:** the public LANDFIRE GeoServer WCS (`edcintl.cr.usgs.gov/geoserver/landfire`),
  `GetCoverage` with an X/Y subset of the fire box.
  - The server delivers EPSG:3857 at 30 m. `prepare.py` warps it to the UTM grid with nearest neighbour.
  - It then checks that no fuel class changes its share by ≥ 1 percentage point. Measured worst cases
    are 0.009–0.047 pp.
  - The official LANDFIRE Product Service (LFPS) would also work, but it requires an e-mail address in
    every request, so it is not used.
- **LF 2020, by hand plus automated clip:** LF 2020 is no longer on the WCS or LFPS. It is archived on
  USGS ScienceBase as one CONUS zip per layer:

  | Layer | ScienceBase item | Zip size |
  |---|---|---|
  | FBFM40 | 6a1602c7b66b013d45990b82 | 3.36 GB |
  | CC | 6a15f914b66b01e66c9c2f39 | 1.92 GB |
  | CH | 6a16003fb66b013d45990b4b | 1.81 GB |

  - ScienceBase serves these files only after a captcha, so the owner downloaded them in a browser on
    the Mac into `data/raw/landfire_conus/`.
  - `harvest.py` then opens the GeoTIFF **inside the zip** through GDAL `/vsizip/` without unpacking. It
    cuts an exact pixel window around the fire in the native EPSG:5070, with no resampling, and records
    the zip's sha256.
- **Disturbance layers (for the checks):** the annual layers LF2020_Dist17–20 and LF2022_Dist21–22, from
  the same WCS.

### 3. Terrain: USGS 3DEP 1/3 arc-second DEM

- **Route:** the 1×1° GeoTIFF tiles on the USGS National Map S3 bucket
  (`prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/…`), merged for the fire.
- **Processing:** averaged onto the 30 m UTM grid; slope and aspect by the Horn method.

### 4. Wind: NOAA HRRR hourly analyses

- **What:** the 10 m U/V wind of the 3 km HRRR model, analysis hour (f00), from 24 h before the first
  perimeter to the end of the record.
- **Route:** NOAA Open Data on AWS (`noaa-hrrr-bdp-pds.s3.amazonaws.com`). For every hour `harvest.py`
  does the following:
  1. reads the small `.idx` index;
  2. downloads **only the two GRIB2 messages it needs** with an HTTP range request (a few MB of a file of more
     than 100 MB);
  3. crops them to the fire box plus 0.1° and records each message's sha256.
- **Time:** about 1–12 min per fire with 8 parallel downloads (326–1,126 hours per fire).
- **Processing:** HRRR winds are relative to its Lambert grid. `prepare.py` rotates them to true north,
  then to the UTM grid (checked analytically: 9.18° vs 9.15° for Mangum), and interpolates to a 300 m
  wind grid.

### 5. Fuel moisture: gridMET

- **Route:** daily 100 h and 1000 h dead-fuel moisture from the University of Idaho THREDDS server,
  NetCDF Subset Service over https, cut to the fire box and period.
- **Use:** the median over the window sets the moisture scenario.
- **Closed route:** the server's port 8080 address does not resolve from the cloud.

### 6. Situation reports (to mask burnout and spotting days)

The pre-declared rule (`validation/MASKING_RULE.md`) needs each fire's daily reports.

| Fires | Source | How |
|---|---|---|
| 2020 (Bush, Mangum) | ICS-209-PLUS (St. Denis et al., figshare doi:10.6084/m9.figshare.19858927.v3, CC BY 4.0) | narrative fields of the sitreps CSV |
| 2022 (Pipeline, Cerro Pelado) | InciWeb publications | `python -m firepath.sitreps <slug> <fire>`, text hashed in `provenance/sitreps_<fire>.json` |
| 2021 (Telegraph) | Internet Archive copies of the old InciWeb articles | `make sitreps-telegraph` on the Mac (58 articles). InciWeb no longer serves them, and the archive refuses fast requests, so the fetcher waits and retries |

Decisions with quotes are in `validation/masked_intervals.json`. The screening of all five fires is
frozen in `validation/fire_screening.json`.

### 7. Not yet obtained

- **RAWS station winds (independent check of HRRR):**
  - WRCC now lists data from before 2026 only with an access code. The owner is requesting one by e-mail.
  - Synoptic's free trial covers only 7 days of history.
  - FEMS returns only the last 2 weeks without a login.
- **NASA FIRMS active fire:** the owner obtained a key (`.env`); it is used in M4 as a timing comparison.
- **Roads, census blocks, structures (TIGER/Line, USA Structures):** only after validation (M6).

## Leakage checks (automated)

| Check | Where | Result |
|---|---|---|
| Fuel version older than the fire year | `tests/test_stage_boundaries.py` | — |
| Fire-year disturbance layer covers the final perimeter | `provenance/stale_fuels_<fire>.json` | covers 99.1–99.99 % of each final perimeter, so the *next* LANDFIRE version would have leaked the outcome |
| Stale fuels (disturbed after the chosen version, before the fire) inside the final perimeter | `provenance/stale_fuels_<fire>.json` | Mangum 13.5 %, Bush 0.6 %, Telegraph 0 %, Pipeline 1.5 %, Cerro Pelado 1.3 % |

## Reproduce

```bash
cd projects/firepath
uv sync
make probe                     # reachability of every endpoint (optional)
make harvest FIRE=mangum       # perimeters, aoi, landfire, disturbance, dem, hrrr, gridmet
make prepare FIRE=mangum       # warp to the 30 m grid, wind rotation, perimeter audit, moisture
uv run python -m firepath.prepare stale mangum
# LF 2020 fires: first put the three ScienceBase zips in data/raw/landfire_conus/
```

Disk: raw ≈ 150 MB per fire (plus 7.1 GB of LF 2020 zips once); interim ≈ 100 MB per fire.
