# FirePath — M0 results (data feasibility)

> **Status: incomplete. The probe has run only in the cloud session, not on the build Mac.** The task
> asked for build-Mac results. The Mac is not reachable from this session, so no Mac result exists, and
> none is assumed below. The cloud results are reported because they are real, but they describe this
> session's egress policy, not the data providers.

## Update during M1a (2026-10-09)

You asked for `make probe` on the build Mac. **It was not run there.** This cloud session has no route to
the Mac: no peer or Remote Control session was reachable (session list empty), and no SSH or other access
was available. The probe was re-run in the cloud session and gave the same result as before: 3 of 32
endpoints answered (HRRR ×2, PyPI), 28 were proxy 403 and 1 timed out. The duplicate JSON was not kept.
Every statement below about the Mac therefore remains "not run". M1b stays **NO-GO** until
`provenance/probe_build-mac.json` exists.

## How to complete M0 on the build Mac

```bash
cd projects/firepath
make probe                      # = python3 src/firepath/probe.py --label build-mac (standard library only)
git add provenance/probe_build-mac.json
```

The probe is non-destructive. It sends GET requests for metadata and directory listings, HEAD requests for
the large files, and one 4 KB byte-range request to HRRR. It submits no jobs, sends no credentials and
creates no accounts. It writes `provenance/probe_build-mac.json` with status, error text, timings,
content headers and sha256 of the bytes read. It also crawls the NIFC FTP listing for the candidate
incidents (≤ 250 listing requests) and queries NIFC perimeter services for Pipeline/Haywire/Double
records. It checks free disk space against the 30 GB requirement. Then fill in the "build Mac" columns
below from that JSON.

## 1. Probe run in the cloud session (2026-10-09, `provenance/probe_cloud-session.json`)

Environment: Linux x86_64 container, 4 vCPU, HTTPS through the session's egress proxy
(`https_proxy_set: true`).

| Source | Check | Cloud session result | Build Mac |
|---|---|---|---|
| NOAA HRRR (AWS S3) | `.idx` GET; 4 KB byte-range of the 10 m U message | **200 / 206**. One transient `404 NoSuchBucket` in 3 identical requests during testing, so retries were added | not run |
| LANDFIRE site, version table | GET | proxy 403 | not run |
| LANDFIRE LFPS API (`/api/`, `/api/products`, `/api/job/submit` without args) | GET | proxy 403 | not run |
| LANDFIRE CONUS FBFM40 zips 200 / 220 / 230 / 240 | HEAD | proxy 403 (the URL patterns themselves are unverified) | not run |
| MTBS site; national perimeter zip | GET / HEAD | proxy 403 | not run |
| NIFC ArcGIS Online services (WFIGS/NIFS archive) | GET services list | proxy 403, so the Pipeline/Haywire query did not run | not run |
| NIFC FTP `incident_specific_data` (NIROPS IR) | GET listing + crawl | proxy 403, so the inventory is empty | not run |
| Mendeley NIROPS dataset metadata | GET | proxy 403 | not run |
| NASA FIRMS API (no key) | GET | proxy 403 (key requirement not observable) | not run |
| NASA FEDS (VEDA OGC API) | GET | proxy 403 | not run |
| gridMET listing / fm100 2022 / THREDDS DAS | GET / HEAD / GET | proxy 403 / 403 / **timeout** | not run |
| USGS TNM API (3DEP 1/3″) | GET | proxy 403 | not run |
| Census TIGER edges (Coconino) / TABBLOCK20 (AZ) | HEAD | proxy 403 | not run |
| USA Structures (geoplatform) / ArcGIS Online search | GET | proxy 403 | not run |
| ICS-209-PLUS (figshare API) | GET | proxy 403 | not run |
| InciWeb (Tunnel Fire page) | GET | proxy 403 | not run |
| NFMD (live fuel moisture) | GET | proxy 403 | not run |
| WRCC RAWS | GET | proxy 403 | not run |
| Synoptic API (no token) | GET | proxy 403 (token requirement not observable) | not run |
| PyPI (pyretechnics metadata) | GET | **200** | not run |

Totals: 32 checks; 3 answered; 28 refused by the proxy (`Tunnel connection failed: 403 Forbidden`);
1 timeout. **A proxy 403 is a policy refusal of this session, not a response from the provider.**

## 2. Candidate fire inventory (NIROPS perimeters and scan times)

| Fire | Role | NIROPS IR files found | Scan times | Status |
|---|---|---|---|---|
| Bush 2020 | calibration | — | — | **unknown**: FTP unreachable from the cloud session |
| Mangum 2020 | calibration (M1b slice) | — | — | unknown |
| Telegraph 2021 | calibration | — | — | unknown |
| Tunnel 2022 | validation | — | — | unknown |
| Pipeline 2022 | validation | — | — | unknown |
| alternatives (Woodbury 2019, Cerro Pelado 2022, South Fork 2024) | — | — | — | unknown |

The crawler logic is verified only against a synthetic directory tree (`tests/test_probe.py`): region →
year → incident → IR → files, with timestamps parsed from file names such as `20220419_2130_…`. The real
NIFC naming scheme is unknown, so the crawler may need adjusting after the first Mac run. That is the
first thing to check in its output.

## 3. Pipeline / Haywire separability

**Unknown.** The probe looks for (a) separate IR files or sub-folders per fire under the "Double" incident on
the FTP, and (b) separate incident names or IRWIN ids in NIFC perimeter services. Decision rule (from PLAN
§2.3, S6): if per-fire perimeters with scan times exist for the evaluation window, Pipeline stays a
validation fire; if only merged "Double" perimeters exist after the fires joined, the evaluation window
ends at the last separable perimeter; if no separable perimeter exists, Cerro Pelado 2022 replaces it.

## 4. LANDFIRE vintage per candidate fire

The vintage **rule** is set (PLAN §3: the last disturbance year of the version precedes the fire year).
**Availability is unverified.** LANDFIRE hosts were unreachable, and the download URL patterns in the probe
are unconfirmed.

| Fire | Fire year | Version by rule | Rejected (contains the fire) | Availability |
|---|---|---|---|---|
| Woodbury | 2019 | LF 2016 Remap (200) | LF 2019 Limited, LF 2020 | not verified |
| Bush, Mangum | 2020 | LF 2019 Limited **if it publishes FBFM40/CC/CH**, else LF 2016 Remap (200) | LF 2020 (220) | not verified; whether LF 2019L has fuels is open |
| Telegraph | 2021 | LF 2020 (220) | LF 2022 (230) | not verified |
| Tunnel, Pipeline, Cerro Pelado | 2022 | LF 2020 (220) | LF 2022 (230) | not verified |
| South Fork | 2024 | LF 2023 (240) | LF 2024 (250) | not verified |

## 5. Disk and storage

- Cloud container: 31.9 GB free of 270.6 GB on the project path (meets the 30 GB requirement). **This
  is not the build Mac.**
- Build Mac: not measured. The probe records it.
- Budget (PLAN §16): peak ≈ 20 GB, persistent raw ≤ 6 GB. Unchanged, because no measured download sizes
  exist yet.

## 6. Go / no-go

| Next step | Needs data? | Recommendation |
|---|---|---|
| **M1a**: mathematical specification + analytic fixtures + propagation-scheme bake-off + Rothermel table tests | no | **GO**, after decisions D1–D3 |
| **M1b**: first data slice (Mangum 2020, Python reference) | yes | **NO-GO** until the Mac probe shows: LANDFIRE (rule version) obtainable for the Mangum AOI; NIROPS (or a documented fallback) perimeters with scan times for Mangum (≥ 3, ≥ 1 consecutive pair); HRRR reachable; gridMET or an alternative reachable; 3DEP reachable; ≥ 30 GB free |
| M0 screening of all pool fires (frozen `validation/fire_screening.json`) | yes | after the Mac probe; needed before calibration (M3), not before M1b |
| Calibration, network, web | — | blocked by the gates in PLAN §16 |
