# FirePath — wildfire spread model checked against observed fire perimeters

Project 03 of the GIS Portfolio Lab. A time-dependent elliptical spread model (Rothermel / Scott & Burgan
fuels, slope, hourly HRRR wind; level-set + graph propagation, Rust kernels) is calibrated on three
Arizona fires (Bush 2020, Mangum 2020, Telegraph 2021) and validated once on two later fires (Pipeline
2022, Cerro Pelado 2022) against airborne infrared perimeters. Status: M1b/M2 done, calibration (M3) next.
A modelled scenario is not a forecast.

## Data and how it was obtained

All inputs are open data, cut to each fire's area at download time and logged with sha256 in
`provenance/`:

| Source | What | How it was obtained |
|---|---|---|
| NIROPS infrared perimeters (Magstadt et al., Mendeley, CC BY 4.0) | observed fire extent with scan times | read in place from the published zip by HTTP range requests |
| LANDFIRE LF 2016 / LF 2020 | fuel models, canopy cover and height | public WCS (LF 2016); ScienceBase CONUS zips downloaded by hand (captcha), clipped through GDAL /vsizip/ (LF 2020) |
| USGS 3DEP 1/3″ | terrain, slope | public S3 tiles |
| NOAA HRRR f00 | hourly 10 m wind | only the needed GRIB2 messages, by byte range from NOAA Open Data on AWS |
| gridMET | dead-fuel moisture | THREDDS subset service |
| ICS-209-PLUS, InciWeb, Internet Archive | daily reports, used to mask burnout days | scripted fetch, texts hashed |

Full account (routes that failed, hand steps, leakage checks, how to reproduce): **`DATA_ACQUISITION.md`**.
Per-source reference fields: `DATA_SOURCES.md`. Method: `METHOD.md`. Plan and milestones: `PLAN.md`.

## Run it

```bash
uv sync
make harvest FIRE=mangum && make prepare FIRE=mangum
uv run python -m firepath.run mangum            # Mode A at 90 m, hand-set parameters (pipeline check)
make test
make bench
```
