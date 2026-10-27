# FirePath — M0 results (data feasibility)

> **Status 2026-10-24: the build-Mac probe has run** (`provenance/probe_build-mac.json`, macOS 26.6 arm64,
> 10 cores, 55.5 GB free). Follow-up source checks (NIFC file share, NIFC archives, LANDFIRE, Mendeley)
> were made from this cloud session, whose network policy now reaches the same hosts; each is labelled
> "cloud" below. Fire screening is **not frozen**: one decision is with the owner (section B4).

## A. Build-Mac probe (2026-10-24)

| Source | Mac result | Consequence |
|---|---|---|
| HRRR (AWS index + byte range) | 200 / 206 | OK |
| LANDFIRE site; LFPS API | 200; product list 200, submit without args → parameter error (expected) | LFPS works. Its catalogue holds **LF2016, LF2022–LF2025** only |
| LANDFIRE direct-download URLs in the probe | 404 | URLs changed; current paths are `/data-downloads/CONUS_LF20xx/…` (cloud). **LF 2020 (220) is archived on USGS ScienceBase**, not on LFPS (landfire.gov/data/lf2020, cloud) |
| 3DEP (TNM API) | 200 | OK |
| gridMET (listing, file, THREDDS) | 200 | OK |
| MTBS perimeter bundle | 200 (390 MB zip) | OK |
| TIGER edges/blocks; USA Structures | 200; hub page | OK |
| FIRMS | without key 401, **with the owner's key 200**: 5,000 transactions / 10 min; VIIRS/MODIS SP archives listed | OK. Key read from the git-ignored `.env`, redacted in the JSON (checked: 0 occurrences) |
| FEDS (openveda) | 200 | OK (fallback perimeters) |
| RAWS WRCC | 200 | OK; Synoptic not configured (not needed) |
| ICS-209-PLUS, InciWeb | 200 | OK (masking of burnout/spotting days) |
| **NIFC file share (NIROPS IR)** | **404** at `public/incident_specific_data` | Since **2026-05-04** these folders are under `protected/` and **require FAMAuth** (agency login + role approval; cloud, ftp.wildfire.gov). Not an option for this project |
| NFMD (fuel moisture) | 404 | moved; not needed (moisture from gridMET) |

**Disk:** 55.5 GB free (≥ 30 GB required) — OK.

## B. Observed perimeters: replacement for the NIFC file share

### B1. Mendeley NIROPS 2020–2024 (primary replacement)
Magstadt et al., *A high spatial resolution daily fire perimeter progression dataset for wildfires in the
Western United States: 2020–2024*, Mendeley Data doi:10.17632/95rj5d379g.1, **CC BY 4.0**, published
2026-06-02. 12,706 IR perimeters, 737 fires, USFS R1–R6 (includes R3), EPSG:4326, one UTC time per perimeter.
It was built from the same NIFC FTP files before the login requirement. Files: one shapefile (zip 1.39 GB,
.shp 2.07 GB), an area-time-series figure set, and the processing notebook.

The attribute table was read from the remote zip with HTTP byte ranges (5.5 MB; no geometry downloaded).
Inventory: `provenance/nirops_mendeley_inventory.json` (dbf sha256, scan times per fire).

| Fire | IR perimeters | consecutive daily pairs | first → last (UTC) | growth visible in ~24 h pairs |
|---|---|---|---|---|
| Bush 2020 | 17 | 16 | 06-14 04:00 → 06-30 | **74,134 ha** |
| Mangum 2020 (listed as "Magnum") | 23 | 19 | 06-10 07:13 → 07-08 | **28,851 ha** |
| Telegraph 2021 | 24 | 22 | 06-05 20:59 → 06-29 | **39,672 ha** |
| **Tunnel 2022** | 4 | 3 | **04-26** 06:45 → 04-29 | **78 ha** |
| Pipeline 2022 | 8 | 5 | 06-14 04:44 → 06-26 | 2,548 ha |
| Haywire 2022 | 7 | 5 | separate incident record | 611 ha |
| Cerro Pelado 2022 | 34 | 26 | 04-26 → 06-11 | **16,291 ha** |
| South Fork 2024 | 9 | 6 | — | 987 ha |
| Woodbury 2019 | — | — | not in the dataset (starts June 2020) | — |

Time handling (from the dataset's notebook): UTC = IRIN `DateFlown`+`TimeFlown` plus a fixed offset per
`TimeZone` label (MST +7, MDT +6, PST +8, PDT +7). Arizona keeps MST all year, so a perimeter mislabelled
MDT would be 1 h early. Telegraph's first scan (20:59 UTC = 13:59 MST) is a daytime time and must be
checked. Both go into the O1 perimeter audit in M1b (S2: ±1 h).

### B2. NIFC Operational Data Archive (secondary)
Public NIFC_Authoritative items (cloud): 2020 and 2021 as file geodatabases (469 MB and 1.34 GB, public
download 200); 2022 also as a feature service. The 2022 service holds the **edit history** of each
perimeter. `PolygonDateTime` is stale (every Pipeline IR polygon shows 06-13 12:54). The real scan time is
only in free-text `Comments` ("N350SM Tenax, 6/13/2022 2238", sometimes "0615UTC"), with mixed time
zones. Usable for cross-checks, not as the primary timing source.

### B3. Pipeline / Haywire
Separate incident records in both Mendeley (different IRWIN IDs) and the NIFC archive: **S6 met**.

### B4. Screening consequence — **decided 2026-10-24: S7 added, Cerro Pelado replaces Tunnel**
Under the pre-registered S1 (≥ 3 perimeters, ≥ 1 consecutive pair), **Tunnel formally passes, but it is
nearly empty as a test**. IR coverage starts on 04-26, after the extreme 04-19/20 run, and only **78 ha**
of growth remain to predict. A validation on 78 ha would be dominated by a handful of cells.
Pipeline is weak but usable (2,548 ha).

Options (no model has been run on any of these fires, so neither choice can be fitted to results):
1. **Keep the registered set** (Tunnel + Pipeline). Validation evidence would be very thin.
2. **Recommended: add S7 now** — "≥ 2,000 ha of growth visible between consecutive daily IR pairs"
   (the same 2,000 ha floor as S4's final-size bound). Tunnel fails S7. Under the registered
   replacement rule its listed alternative **Cerro Pelado 2022** (16,291 ha, 34 perimeters; UTM 13N;
   holdover start, so first-perimeter initialisation) takes its place. Pipeline stays. Calibration is
   unchanged (Bush, Mangum, Telegraph all pass S7 with wide margins).

Masked burnout/spotting days (ICS-209-PLUS) are still to be listed per fire before the screening file is
frozen.

## C. LANDFIRE vintages (revised)

| Fire | Rule (version predating the fire) | Source now |
|---|---|---|
| Bush, Mangum 2020 | LF 2016 Remap (disturbances to 2016) | LFPS `LF2016_*` (AOI clip) |
| Telegraph 2021; Pipeline, Cerro Pelado 2022 | LF 2020 (disturbances 2017–2020, "2022 capable") | **ScienceBase archive** (full CONUS per layer; size to measure before download) |
| (LF 2022 for any 2023 fire, if ever needed) | — | LFPS |

LF 2022 must **not** be used for the 2021–22 fires: it contains their own burn scars (leakage).

## D. Go / no-go (2026-10-24)

- **M1b (Mangum 2020 slice): data side GO.** Mangum has 23 IR perimeters with UTC times; LF2016 via LFPS,
  HRRR, gridMET and 3DEP are reachable from the Mac; disk is sufficient. The remaining precondition is
  numerical: the pre-registered HY confirmation run at 30 m (M1A_RESULTS, "D1 decision").
- **Screening freeze:** done 2026-10-26, `validation/fire_screening.json` (all five fires pass S1–S7; masked
  intervals: Telegraph 1, Pipeline 1 outside its window, others none).

## Earlier status (kept for the record)

### Update during M1a (2026-10-09)

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

**M1a-2 source check (news reports, not perimeter files):** the fire that merged with Haywire on 13–14
June 2022 was the **Double Fire**. Pipeline was a separate fire about 6 miles away (Coconino County
updates, CNN, Fox10, ABC15, via search). The v1 plan's "Pipeline + Haywire merged incident" was wrong
(an InciWeb page for the Double incident also carried Pipeline bulletins). Separability is therefore
**likely** but **not verified in the perimeter data**.

Earlier status: **unknown.** The probe looks for (a) separate IR files or sub-folders per fire under the "Double" incident on
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
| Bush, Mangum | 2020 | **LF 2016 Remap (200)**: its FBFM40 is "2019 capable" per catalog metadata; no FBFM40 for "LF 2019 Limited" was found (M1a-2 search) | LF 2020 (220) | not verified on the Mac; 2017–2019 disturbances missing (stale fuels) |
| Telegraph | 2021 | LF 2020 (220) | LF 2022 (230) | not verified |
| Tunnel, Pipeline, Cerro Pelado | 2022 | LF 2020 (220) | LF 2022 (230) | not verified |
| South Fork | 2024 | LF 2023 (240) | LF 2024 (250) | not verified |

## 4b. NIROPS product naming (M1a-2 source check)

NIROPS interpreters deliver four standard layers: Heat Perimeter (polygon), Intense Heat, Scattered Heat
and Isolated Heat Sources [sourced: an Alaska ordering guide, via search]. The official naming convention
is in the IRIN template and layer pack under `ftp.wildfire.gov/public/nirops/Tools/`. The probe now
checks that directory and tags crawled files by product type; only *Heat Perimeter* files are used as
observed perimeters. The scan-time encoding is still unknown and is the first thing to check in the Mac
probe output.

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
