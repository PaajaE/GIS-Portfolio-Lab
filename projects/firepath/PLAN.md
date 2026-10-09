# FirePath — plan (decision-ready draft)

> Status: **plan for approval, 2026-10-09.** Nothing has been harvested at scale, modelled or built.
> Spec: §7 (FirePath), with §2, §3, §12, §13, §16. Method decisions are recorded in `METHOD.md`, sources in
> `DATA_SOURCES.md`. Statements are marked **[verified]** (checked during planning, with the source),
> **[sourced]** (taken from a primary/official source but not checked against the data) or
> **[to verify]** (an assumption that milestone M0 checks before anything relies on it).

## 0. How this plan was made, and what could not be checked

- Read: `CLAUDE.md`; spec §2, §3, §7, §12–§16; `.claude/rules/{rust,web}.md`; skills `gis-analysis`,
  `web-ux`; `docs/product/DESIGN_DECISIONS.md`; Parcel Intelligence (`README.md`, `METHOD.md`,
  `DATA_SOURCES.md`, `Makefile`, `validation/HAND_CHECKS.md`, manifest, benchmark JSON, Cargo/pyproject).
  `projects/landslide-susceptibility/` **does not exist**, so there are no Project 02 decisions or
  shared-file changes to build on. FirePath would be built second, ahead of the spec's build order (§15).
  This is open question Q7.
- **Network reachability was checked from the cloud session that wrote this plan, not from the build Mac.**
  This session's egress policy refuses almost every data host with HTTP 403 at the proxy: landfire.gov,
  lfps.usgs.gov, edcintl.cr.usgs.gov (MTBS), services3.arcgis.com (NIFC), firms.modaps.eosdis.nasa.gov,
  northwestknowledge.net (gridMET), census.gov, tnmaccess.nationalmap.gov, mendeley, wifire.
  These results say nothing about the Mac, and earlier USGS and ArcGIS Online access from the Mac worked.
  Only **NOAA HRRR on AWS S3** was reachable. M0 therefore begins with a reachability probe *on the Mac*
  (§16 M0), and every source stays **[to verify]** until that probe passes.
- **Feasibility sample (git-ignored):** one HRRR GRIB2 message, the 10 m U wind analysis for
  2022-04-19 21 UTC (Tunnel Fire), fetched by byte range using the `.idx` file
  (`data/raw/feasibility/hrrr_20220419_21z_ugrd10m.grib2`, 2.38 MB,
  sha256 `e56bd295…a9384905`). Reading GRIB2 section 3 (template 3.30, Lambert conformal,
  1799 × 1059) gives resolution/component flags `00001000`. **[verified] HRRR 10 m winds are
  grid-relative**, so they must be rotated to earth-relative before use (§5).
- **Projection factors [verified]** (pyproj, at the candidate fires): EPSG:5070 (LANDFIRE's native CONUS
  Albers) has meridional scale 1.0066–1.0094, parallel scale 0.9907–0.9934, angular distortion
  0.76–1.07° and grid convergence −9.1 to −9.7°. NAD83 / UTM 12N (EPSG:26912) has scale 0.9996–0.9997
  and convergence −0.03 to −0.68°. This decides the CRS (§5).
- `df -h` on this container is not the Mac's disk. The disk budget in §16 is a requirement the Mac must
  meet, checked by `df -h` in M0.

---

## 1. Problem and decision

**Question (spec §7):** can a lightweight, reproducible rate-of-spread / arrival-time model reconstruct
the growth of historical wildfires well enough to explore alternative fuel, terrain and wind scenarios?

**Who uses reconstructed arrival times, and for what:**
- *Fire-management and fuels planners, and county emergency managers doing after-action or planning
  analysis.* They ask how much a different wind, drier fuels or a fuel change on one slope would have
  changed **when** the fire reached a road, a subdivision or a ridge, and whether the conclusion holds
  across plausible inputs.
- *Analysts and students of fire behaviour.* They want to see where a simple surface-spread model
  reproduces observed growth, where it fails (spotting, plume-driven runs, suppression), and how large
  the input uncertainty is compared with the model error.
- What they explore: (1) observed vs modelled perimeters through time; (2) scenario sensitivity (wind
  speed and direction, dead-fuel moisture, fuel map, slope effect) as arrival-time differences;
  (3) **modelled road-closure timing** and the resulting network travel time and population without a
  road connection, by hour.

**Decision metric:** arrival time per cell (hours since a fire-specific reference time `t0`, stored in
UTC). Derived from it: modelled burned area by time `t`, closure time per road segment, and population
with no open road path to the outside by hour, each with its scenario range and the validation error of
that fire next to it.

**Wording (applies to README, app and figures):**
- A **modelled scenario, not a forecast**. These are reconstructions of past fires under stated inputs,
  never predictions for current fires.
- **Not FARSITE/FlamMap, not an operational fire-behaviour system.** Surface spread only, no spotting,
  crown fire, suppression or fire–atmosphere coupling (§15).
- "Modelled road closure" means the arrival-time rule in §11, not an observed closure. "Population
  without a modelled road connection" is **exposure, not risk** (no evacuation behaviour, traffic or
  consequence model). Network results use **network travel time**, never straight-line distance.
- Ensemble output is called **scenario agreement** ("burned by t in 7 of 10 scenarios"), not probability,
  unless the test in §10 justifies more.
- A comparison with a different construct (VIIRS detections, MTBS boundaries, reported closures) is
  labelled **comparison**, not validation.

---

## 2. Fire selection

### 2.1 Sources for observed growth, and what they measure

| Source | What a "perimeter" is | Timing | Use here |
|---|---|---|---|
| **NIROPS airborne IR perimeters** (USFS National Infrared Operations; posted on the NIFC FTP `ftp.wildfire.gov/public/incident_specific_data/…`) | Fire edge hand-interpreted from airborne thermal imagery by an IR interpreter (IRIN) | Usually one night flight per day. The scan time sits in the file/metadata **[to verify per fire]** | **Primary time-stamped intermediate perimeters** (observed arrival intervals) |
| Mendeley "high spatial resolution daily fire perimeter progression dataset … Western US 2020–2024" (Magstadt, Wadhwani, Whitley, Martin, Sitter, Wei, O'Connor; doi:10.17632/95rj5d379g.1) [sourced] | The same NIROPS perimeters standardised to EPSG:4326, 12,705 perimeters, 737 incidents in USFS Regions 1–6, each with ≥ 3 collection days incl. ≥ 1 consecutive pair | As NIROPS | **Inventory / screening shortcut** and cross-check of my NIROPS parsing. Licence **[to verify]**. Prefer the NIFC FTP originals as the source of record |
| **NIFC WFIGS / NIFS Operational Data Archive** (yearly exports of the National Incident Feature Service, every edit kept, `GDB_FROM`/`GDB_TO`) [sourced] | The incident's operational "event polygon", often IR-derived and edited by incident GIS staff | `GDB_FROM` is an **edit time, not an observation time**. A polygon date field may exist **[to verify]** | Fallback for missing NIROPS days; cross-check of NIROPS. Not used for arrival-time error unless an observation time field exists |
| NIFC InterAgency Fire Perimeter History / WFIGS final perimeters | Final operational perimeter | Final only | Final-extent cross-check |
| **MTBS** burned area boundary (Landsat dNBR) [sourced] | A perimeter traced from pre/post Landsat imagery. It includes unburned islands and fingers inside the outline (documented commission error 4–16 % in shrub-steppe from that cause). Thematic severity raster inside | Post-fire assessment, no growth timing | Final-extent comparison and **unburned-island share** (the model burns every burnable cell inside its front). Never used as a model input |
| **NASA FIRMS VIIRS 375 m / MODIS 1 km** active-fire detections [sourced] | A pixel with active fire at overpass time | VIIRS S-NPP ≈ 01:30/13:30 local; NOAA-20 ≈ 50 min ahead of S-NPP; NOAA-21 from 2023; MODIS Terra ≈ 10:30/22:30, Aqua ≈ 13:30/01:30 | **Timing proxy (comparison only)**, see 2.4 |
| NASA FEDS (Fire Event Data Suite) 12-hourly VIIRS perimeters [sourced] | Object-tracked VIIRS fire area ("not analogous to operational perimeters", per NASA) | 12-hourly (00:00/12:00 stamps for 01:30/13:30 passes) | Fallback timing reference only if NIROPS is insufficient, clearly labelled as satellite-derived |

### 2.2 Candidate pool and scores

The pool is restricted to **USFS Southwestern Region (R3), Arizona/New Mexico, 2019–2022**. Reasons:
NIROPS coverage of National Forest fires; mostly **surface-fire-carrying fuels** (grass, grass-shrub,
chaparral, ponderosa pine litter/understory), where a Rothermel-type surface model is most defensible;
synoptic wind events (spring/early-summer dry fronts) that a 3 km hourly model can resolve; one fuel-climate
domain, so a calibration on some fires can fairly be expected to transfer to others; and a single UTM
zone (12N) for the Arizona fires. A California (R5) pool is the main alternative (Q1); it is weaker because
its large fires are more often plume- or spotting-dominated (chaparral, WUI, mixed conifer).

Scores: ●●● good, ●● adequate, ● weak, ? = not yet checked (M0 screening fills it). Facts marked † are
from InciWeb/agency releases found during planning [sourced]. The perimeter availability of every fire is
**[to verify]**, because the NIFC FTP and the Mendeley file could not be opened from this session.

| Fire (unit) | Start † | Final size † | Intermediate perimeters | Ignition quality | Fuel / terrain diversity | Weather | Grid cost (30 m, AOI + 5 km) | Spotting / suppression dominance | Role |
|---|---|---|---|---|---|---|---|---|---|
| **Bush 2020** (Tonto NF) | 2020-06-13 afternoon, vehicle fire at SR 87 / Bush Hwy (human) | ≈ 193,000 ac (≈ 78,000 ha) | ? (in Mendeley's 2020–24 window) | ●● location known, time "afternoon" | ●●● desert grass → chaparral → pine, rugged | ●●● HRRR | ≈ 3–4 M cells | ? big burnout operations likely late, so mask those days | **calibration** |
| **Mangum 2020** (Kaibab NF) | discovered 2020-06-08 ≈ 15:00, POO 36.251, −112.144 (human) | 71,450 ac (≈ 28,900 ha) | ? | ●●● POO coordinates published; start date ambiguous (June 6 vs 8), so initialise from first perimeter | ●● ponderosa / mixed conifer / PJ on the Kaibab Plateau, canyon edges | ●●● | ≈ 1.5–2.5 M | ? | **calibration** |
| **Telegraph 2021** (Tonto NF) | 2021-06-04 13:30 (human) | ≈ 180,700 ac (≈ 73,000 ha) | ? | ●●● | ●●● chaparral, grass, pine; very steep (Pinal Mtns) | ●●● | ≈ 3–4 M | ? long duration, firing operations likely | **calibration** |
| **Tunnel 2022** (Coconino NF) | 2022-04-17 16:22 (cause under investigation) | ≈ 19,000–21,000 ac (≈ 7,700–8,500 ha) | ? | ●●● | ●● grass, PJ, ponderosa; cinder hills | ●●● one extreme wind day (≈ 16,600 ac overnight on 19–20 Apr) | ≈ 0.5–0.8 M | ? wind-driven; spotting into Doney Park likely | **validation** |
| **Pipeline 2022** (Coconino NF, incident "Double Fire" with Haywire) | 2022-06-12 10:15 (human) | ≈ 26,500 ac (≈ 10,700 ha) | ? | ●●● | ●●● grass → ponderosa → mixed conifer on the steep west/north flanks of the San Francisco Peaks | ●●● | ≈ 0.6–1.0 M | ? merged incident with the lightning-caused Haywire Fire, so the two must be separable | **validation** |
| Woodbury 2019 (Tonto NF) | 2019-06-08 (human) | ≈ 123,000 ac | ? (pre-2020: FTP only) | ●● | ●●● | ●●● | ≈ 3 M | ? | alternative calibration |
| Cerro Pelado 2022 (Santa Fe NF) | 2022-04-22 afternoon; prescribed-burn holdover (exact time unknown) | 45,605 ac | ? | ● time unknown, so first-perimeter initialisation only | ●●● ponderosa / mixed conifer, Jemez | ●●● | ≈ 1.5 M (UTM 13N) | ? | alternative validation |
| South Fork 2024 (Lincoln NF, NM) | 2024-06-17 | ≈ 17,000 ac | ? | ● (cause disputed) | ●● | ●●● | ≈ 0.6 M | extreme wind run into Ruidoso; WUI spotting | alternative validation (LANDFIRE 2023 vintage) |

Excluded up front: fires dominated by plume/pyroCb behaviour or mass spotting (Creek 2020, North Complex
2020, Camp 2018, Marshall 2021, Palisades/Eaton 2025); very large long-duration complexes (Dixie 2021,
Hermits Peak 2022) where suppression and multiple ignitions dominate; lightning ignitions with unknown time,
unless initialised from a perimeter.

### 2.3 Calibration vs validation split, and why it is fair

**Rule (fixed before any model run): temporal holdout.** Calibrate on the pool fires from **2019–2021**
that pass screening. Validate on the **2022** fires that pass screening, **each opened exactly once**
after the calibrated parameters are locked (§8, `validation/locked_params.json` committed first).

- **Recommended:** calibration = **Bush 2020, Mangum 2020, Telegraph 2021**; validation = **Tunnel 2022,
  Pipeline 2022**.
- Why the test is fair and not cherry-picked: (1) the split is set by date, not by model fit, and mimics
  the real use (parameters from past fires applied to a later one); (2) the pool, the screening criteria
  and the rule are committed in this plan before any run, and every pool fire that passes screening is
  used, so no fire is dropped after seeing results; (3) both fuel complexes of the validation fires
  appear in calibration (grass/chaparral: Bush, Telegraph; ponderosa/mixed conifer: Mangum), so the
  validation fires are in-domain and the test is not trivially out-of-distribution; (4) the validation
  fires are not easy: Tunnel has an extreme wind run, Pipeline has steep terrain and a merged incident.
- **Screening criteria (pre-registered; M0 applies them and freezes `validation/fire_screening.json`):**
  S1 ≥ 3 time-stamped perimeters in the evaluation window with ≥ 1 consecutive daily pair;
  S2 observation time known to ±1 h (scan time) or the perimeter is excluded; S3 point of origin known to
  ±500 m **or** usable first perimeter; S4 final area 2,000–100,000 ha; S5 LANDFIRE version that predates
  the fire exists (§3); S6 the fire is separable from neighbouring incidents. Days whose growth the
  ICS-209 / InciWeb record attributes mainly to **firing (burnout) operations or long-range spotting** are
  masked from evaluation (a pre-declared list per fire, frozen before modelling). The fire is not dropped.
- If a recommended fire fails screening, its listed alternative takes its place in the same role. If the
  temporal rule then leaves < 2 validation fires, the fallback is **leave-one-fire-out across the whole
  set**, reported as such.

### 2.4 Satellite detections as a timing proxy, not arrival time

A VIIRS detection at time `t_d` means part of a 375 m pixel (≈ 0.8 km at swath edge; MODIS 1 km) was
burning at `t_d`. The bias runs both ways: (a) **late** by up to the gap since the previous usable overpass
(≈ 12 h for one sensor, a few hours with three VIIRS platforms plus MODIS; longer under cloud or thick
smoke); (b) **early** for a 30 m cell, because the pixel can trigger on fire elsewhere in the footprint.
Low-intensity backing fire may never be detected (omission). Use: an interval-censored consistency check
("the modelled arrival in the footprint precedes `t_d`, and follows the last non-detecting clear overpass").
It is never used for calibration and never called arrival-time validation. FIRMS API access needs a free
**MAP_KEY** [sourced], so it is open question Q2.

---

## 3. Temporal alignment (leakage traps)

| Input | Rule | Concrete choice (to verify in M0) |
|---|---|---|
| Fuels (FBFM40, canopy cover/height) | LANDFIRE version whose **last disturbance year < fire year**. LANDFIRE versions are named for the last disturbance year mapped [sourced]; LF 2020 (version 220) adds 2017–2020 disturbances and its fuels are "2022 capable" (projected 2 years of recovery) [sourced]; LF 2022 (230) includes 2022 disturbances | 2020 fires (Bush, Mangum): **LF 2019 Limited** if it carries FBFM40 (2017–2019 disturbances), else LF 2016 Remap (200). 2021 (Telegraph): **LF 2020 (220)**. 2022 (Tunnel, Pipeline): **LF 2020 (220)**, *not* LF 2022 (230), which encodes these fires |
| Stale fuels | Disturbances between the LANDFIRE cutoff and ignition are missing (e.g. 2021 fires and treatments for the 2022 fires) | Overlay NIFC perimeter history + MTBS for the gap years; report the stale share of each AOI; run a sensitivity scenario with those cells recoded |
| Leakage check | The chosen version's fuel-disturbance layer must show **no** disturbance of the fire year inside the AOI, and fuels inside the later perimeter must not differ systematically from the previous version | Automated test at the `prepare` boundary |
| Terrain | 3DEP DEM; bare-earth terrain barely changes in a fire, but the source-date footprint is recorded | Assert source date < fire start, or document |
| Weather | HRRR analyses (f00) and gridMET daily values **for the fire period only** (ignition − 24 h to window end) | — |
| Observed perimeters | Used as **initial conditions only at times ≤ the prediction start**; as targets only at later times | Enforced by the run API: `initialise(t0)` reads perimeters with `t ≤ t0` only |
| Domain | Built from the union of observed perimeters + 5 km buffer (a mild use of outcome geometry) | Test: doubling the buffer must not change arrival times inside the evaluation area. If it does, the run is "domain-limited" and is flagged |
| Subtle | HRRR assimilates surface observations near the fire and has smoke physics fed by satellite FRP. This is contemporaneous weather, not post-fire information, so it is acceptable and documented | — |

All times are handled in **UTC**. Arizona does not observe daylight saving time (MST = UTC−7) and New
Mexico does, so local times appear only in presentation.

---

## 4. Data and variables

| Dataset | Variable(s) | Rationale | Source · vintage · resolution · licence |
|---|---|---|---|
| LANDFIRE FBFM40 | Scott & Burgan 40 fuel model per cell | Fuel parameters (load by size class, SAV, depth, extinction moisture, heat content) enter Rothermel's no-wind ROS `R0` and the wind/slope coefficients | LANDFIRE (USGS/USFS), version per §3, 30 m, CONUS Albers; public domain, credit requested [sourced]; LFPS API asks for an email in requests [sourced, to verify] |
| LANDFIRE CC, CH | Canopy cover, canopy height | Wind adjustment factor (sheltered vs unsheltered midflame wind) | as above. CBH/CBD are **not used** (no crown fire, §15) |
| LANDFIRE FDist | Fuel disturbance year/type | Leakage test (§3) | as above |
| USGS 3DEP DEM | Elevation → slope (tan θ), aspect | Slope factor and upslope direction | 1/3″ (≈ 10 m) seamless, averaged to 30 m; public domain |
| HRRR analysis (f00) | 10 m U/V (grid-relative, rotated), 2 m T and RH, surface gust | Hourly wind speed and direction: wind is the main driver of spread rate and direction | NOAA HRRR via AWS Open Data (`noaa-hrrr-bdp-pds`), 3 km, hourly; public domain; **[verified] reachable** (this session) |
| gridMET | fm100, fm1000 (daily dead fuel moisture), ERC | Selects the fire's Scott & Burgan moisture scenario | Climatology Lab / Univ. of Idaho, 4 km daily; public domain per the Earth Engine catalogue, so the licence is to be confirmed at the primary source |
| NIROPS IR perimeters | Fire edge at scan time | Observed arrival intervals (targets) | NIFC FTP; public, non-copyrighted per the FTP posting rules [sourced] |
| NIFS Operational Data Archive / WFIGS | Operational perimeters, IRWIN ids, POO, discovery time | Cross-check, ignition record | NIFC Open Data; US Gov, public [to verify] |
| MTBS | Burned area boundary, thematic severity | Final-extent and unburned-island comparison | MTBS (USGS EROS / USFS GTAC); public domain |
| FIRMS VIIRS/MODIS | Detection time, location, FRP | Timing proxy (comparison) | NASA LANCE/FIRMS; free, citation requested; API needs MAP_KEY (Q2) |
| ICS-209 / ICS-209-PLUS | Daily narratives: firing ops, spotting, plume-dominated runs | Pre-declared masks of evaluation days | ICS-209-PLUS (St. Denis et al., figshare, 1999–2020 only) [sourced]; 2021–2022: InciWeb releases / SIT-209 **[to verify]** |
| Census TIGER/Line roads | Road edges with from/to node ids, MTFCC class | Network graph (§11) | US Census Bureau, public domain; **chosen over OSM** to avoid ODbL share-alike on the derived network |
| Census 2020 TABBLOCK20 | Block polygons with POP20, HOUSING20 | Population by hour without a road connection (exposure) | US Census Bureau, public domain |
| USA Structures | Building footprints | Structures within the modelled front by time (exposure count) | FEMA/ORNL, public domain [sourced]; FEMA hosts were unreachable from the Mac before, so an ArcGIS Online copy is tried and this stays optional |

**Fuel model system.** Scott & Burgan (2005) 40 models, parameter table transcribed from GTR-153 and
checked by test against published values. Non-burnable NB1/2/3/8/9 (codes 91, 92, 93, 98, 99) are barriers.
Dynamic models (GR, GS and some SH/TU) transfer live herbaceous load to dead by live herbaceous moisture,
as in Scott & Burgan.

**Weather choice.** HRRR hourly (3 km) is the primary source, because wind direction changes within a
day (frontal passages, diurnal slope/valley flow) and daily gridMET wind cannot represent the timing of a
run. gridMET is used only for the slowly varying dead-fuel moisture class. RAWS stations are the
independent check on HRRR winds near each fire (WRCC/raws.dri.edu, or Synoptic, which needs a token: Q3).
Wind-direction changes: each hour has its own wind field, and the propagation integrates across hour
boundaries exactly (§6.5). **Fuel moisture is static per fire**: one Scott & Burgan dead/live moisture
scenario (D1–D4 × L1–L4) chosen by a pre-registered mapping from the gridMET fm100 median over the
evaluation window, with drier/wetter neighbours as sensitivity scenarios (§10). Diurnal moisture is
omitted (dynamic moisture is out of scope). Its effect is diagnosed by splitting errors into day vs night
steps.

---

## 5. Harmonization

- **CRS: NAD83 / UTM zone 12N (EPSG:26912)** for the Arizona fires (13N, EPSG:26913, for New Mexico
  alternatives). It is conformal, with scale error ≤ 0.04 % at the candidate fires [verified]. LANDFIRE's native
  EPSG:5070 was rejected: at these fires it stretches north–south by ≈ +0.7–0.9 % and shrinks east–west by
  the same amount, with ≈ 1° angular distortion [verified]. That would bias an anisotropic spread model
  directly. The cost of UTM is resampling the categorical fuels (next point).
- **Cell size: 30 m** (LANDFIRE native). Spread geometry: a cell is the smallest barrier (a 30 m road or
  rock band) the model can see, and the stencil angle error (§6.4) is independent of cell size, but fronts
  are quantised to 30 m. Cell-size sensitivity: 60 m and 90 m runs (fuels by mode, DEM by mean) on every
  fire (§10). A conclusion that changes with cell size is reported as an artefact, not a driver.
- **Resampling.** Fuels, canopy and fuel disturbance (categorical/coded) use **nearest** at 30 m → 30 m. I
  verify that class proportions in each AOI change by < 1 percentage point and report the confusion matrix
  against a reverse-warped grid. The DEM is averaged from 1/3″ to 30 m **before** slope (Horn 3×3),
  computed in UTM metres. HRRR U/V are **rotated from Lambert grid-relative to earth-relative**, then to UTM
  grid-relative (convergence ≤ 0.7°), and only then interpolated bilinearly to a 300 m wind grid. Speed
  and direction are never interpolated separately. Without the rotation the direction error near
  Flagstaff would be ≈ 9° from HRRR alone. Wind conversion 10 m → 20 ft: × 1/1.15 (standard), then
  midflame wind adjustment factor from fuel-bed depth (unsheltered) or canopy cover/height (sheltered,
  Albini & Baughman), as in Andrews (2012).
- **Alignment.** One grid per fire: origin snapped to a multiple of 30 m in UTM, extent = union of observed
  perimeters + 5 km. Every raster is written on that grid and asserted equal (transform, shape, CRS).
  Perimeter → raster uses the cell-centre rule, as in Parcel Intelligence.
- **Nodata and non-burnable.** Outside the grid, the cell does not exist. Non-burnable fuels (NB codes),
  water and **missing fuel** are barriers (never burn; an edge that crosses one is invalid). Missing DEM →
  cell flagged and treated as a barrier (asserted to be 0 cells inside the AOI). The grid edge counts as
  a barrier, and reaching it before the window ends flags the run as domain-limited. Inside the initial
  perimeter, cells are "burned at t0" whatever their fuel.

---

## 6. Model formulation

An explicit **rate-of-spread → anisotropic arrival-time** model. It is not a burn/no-burn cellular
automaton: every burnable cell gets a continuous arrival time.

### 6.1 Head rate of spread

For cell *i* at time *t*:

```
R_head(i,t) = k · g(f_i) · R0(f_i, M) · (1 + φ_E(i,t))
φ_E          = | a_w · φ_w(U_mid(i,t), f_i) · ê_wind(i,t)  +  a_s · φ_s(tanθ_i, f_i) · ê_upslope(i) |
```

- `R0(f, M)` is Rothermel's (1972) no-wind, no-slope surface ROS for fuel model *f* at moisture scenario
  *M*, following the equations as compiled in Andrews (2018, RMRS-GTR-371) and the Scott & Burgan parameters.
  It is computed once per fuel code in Python (table), which is a stated physics prior, not a calibrated
  value.
- `φ_w = C · U_mid^B · (β/β_op)^(−E)` (Rothermel wind factor; C, B, E, β, β_op per fuel model, from the same
  table). `U_mid` = HRRR 10 m speed → 20 ft → × WAF.
- `φ_s = 5.275 · β^(−0.3) · tan²θ` (Rothermel slope factor).
- **Vector combination** of wind and slope (Rothermel 1972 / Finney 1998 practice): the two factors add as
  vectors in the wind and upslope directions. The resultant gives the **direction of maximum spread** and
  `φ_E`, and inverting `φ_w` gives the effective wind speed `U_E`.
- Stated modifiers (the free parameters, §6.7): global spread coefficient `k`; fuel multiplier `g` by
  fuel group; wind sensitivity `a_w`; slope sensitivity `a_s`; moisture multiplier `m` (scales dead
  moistures inside `R0` and `φ`).
- Two guards: `U_E` is capped at the Rothermel/Andrews wind limit, and `R_head` = 0 if dead moisture ≥
  extinction moisture.

### 6.2 Direction dependence (ellipse)

Length-to-breadth ratio from effective midflame wind (Anderson 1983, as used in FARSITE):
`LB = 0.936·e^(0.2566·U_E) + 0.461·e^(−0.1548·U_E) − 0.397` (U_E in mi/h), capped at 8.
Eccentricity `e = √(LB² − 1)/LB`. Spread rate in a direction at angle ψ from the maximum-spread
direction, for a fire growing from the rear focus (Richards 1990; Finney 2002 MTT):

```
R(ψ) = R_head · (1 − e) / (1 − e·cos ψ)
```

Backing ROS is `R_head·(1−e)/(1+e)`. Flanks follow from the same expression.

### 6.3 Per-neighbour travel time

For each stencil offset (Δr, Δc), a precomputed list gives the cells the straight segment between cell
centres crosses and the length in each (an exact grid traversal). Travel time = Σ ℓ_j / R_j(ψ), where ψ is
the segment's direction relative to each crossed cell's maximum-spread direction. **An edge is invalid if
any crossed cell is a barrier.** This prevents knight-move "jumps" over a one-cell barrier or past a
diagonal corner (tested, §12).

### 6.4 Propagation algorithm and its geometric bias

**Label-setting (Dijkstra) shortest arrival time on a 16-neighbour stencil** (8 + 8 knight moves), with a
32-neighbour option (adding (±3,±1), (±3,±2) and transposes). This is the minimum-travel-time idea of Finney
(2002) on a fixed lattice. Fronts restricted to stencil directions **over-estimate** arrival (under-predict
spread) away from those directions. For isotropic spread the worst-case relative error is
1/cos(Δ/2) − 1, where Δ is the largest angular gap: 8-neighbour 8.2 %, **16-neighbour 2.7 %**,
32-neighbour 1.3 %. The error grows for elongated ellipses. Mitigation: (1) analytic fixtures measure the
error as a function of LB and wind angle (§12); (2) the default stencil is the smallest that keeps the error
< 3 % at LB ≤ 4 on the fixture; (3) the 16 vs 32 stencil comparison runs on every real fire as an
**artefact check** (§10). Fast marching / ordered-upwind methods would be more accurate but much more
complex. They are not planned unless the artefact check shows the stencil error is comparable to the
physical sensitivities.

### 6.5 Time-varying wind

Wind and therefore `R_head`, LB and direction are piecewise-constant per hour (HRRR). Traversal of an
edge starting at time `t_u` integrates progress along the segment through the hour boundaries it crosses
(distance covered = ∫ R(τ) dτ). Because the progress is monotone, the travel-time function is **FIFO**
(a later start never arrives earlier), so time-dependent Dijkstra stays exact on the graph (Kaufman &
Smith 1993). A strip fixture with a wind switch has an analytic answer (§12).

### 6.6 Ignition and stopping

- **Mode A (primary, for evaluation): initialise from the first usable observed perimeter** at its scan
  time `t0`. Interior cells = burned at t0, boundary cells are sources. This removes ignition location/time
  error from the spread-rate evaluation.
- **Mode B (secondary): point ignition** at the reported POO and discovery time (InciWeb/IRWIN), to show how
  much error comes from ignition.
- **One-step-ahead variant of Mode A:** re-initialise from the observed perimeter at each `t_{k−1}` and
  predict to `t_k`. This isolates day-to-day spread-rate skill from accumulated error.
- **Stopping rule:** propagate until the heap minimum exceeds `T_end` = end of the evaluation window
  (+ 48 h margin for censored error metrics). Cells not reached are "not burned by T_end". There is no
  other extinction rule (no burnout, no suppression).
- **Evaluation window (pre-registered):** from the first usable perimeter to the earlier of (a) the first
  perimeter time at which observed area ≥ 90 % of the final area and (b) 7 days. Masked days (§2.3) are
  excluded from metrics, not from the run.

### 6.7 Free parameters and physical ranges

| Parameter | Meaning | Range (prior bounds) | Calibrated? |
|---|---|---|---|
| `k` | global spread coefficient (the "ROS adjustment factor" of FARSITE practice) | 0.2 – 5 (log-uniform) | yes |
| `a_w` | wind sensitivity (multiplies φ_w; absorbs WAF and HRRR speed bias) | 0.3 – 3 (log) | yes |
| `a_s` | slope sensitivity (multiplies φ_s) | 0.3 – 3 (log) | yes |
| `g_timber / g_grass` | fuel multiplier: relative adjustment of timber/timber-understory (TL/TU) vs grass/grass-shrub/shrub (GR/GS/SH) models; `g_grass` = 1 | 0.3 – 3 (log) | yes |
| `m` | moisture multiplier on dead fuel moistures | 0.7 – 1.3 | **no, a scenario variable**: it is confounded with `k` (both scale `R0`), so it is varied in §10 and fixed at 1 in calibration |
| stencil, cell size, LB cap | numerical choices | 16/32; 30/60/90 m; 8 | no (artefact checks) |

---

## 7. Baselines (calibrated on the same fires, same objective, same initialisation)

- **B0, isotropic constant rate:** `R = c` everywhere burnable (1 parameter). This is what "distance from
  the fire" would give.
- **B1, wind-only ellipse:** uniform fuel, no slope, `R_head = c · (1 + b · U10^1.5)` with the same hourly
  HRRR wind, ellipse from `U10` (2 parameters).
  This is the **baseline the model must beat**: it asks whether fuels and terrain add skill beyond wind.
- The model is reported beside both, per fire and per time step. "No detectable gain over B1" is a
  possible and reportable result.

---

## 8. Calibration

- **Primary objective: arrival-time interval error.** Consecutive observed perimeters give each cell an
  observed arrival interval (t_{j−1}, t_j]. Per cell, error = 0 if the modelled arrival lies in the
  interval, else the distance to it in hours, capped at 48 h (cells never reached take the cap). The error
  is averaged over cells **burned in the observation or the model within the window, excluding cells inside
  the initial perimeter** (these are trivially right) and masked days. It is averaged per fire, then
  across fires with **equal weight per fire**, so a large fire does not dominate. This scores the claim
  (timing), not only the final extent.
- **Secondary (reported, not optimised):** growth-only Dice at each step (newly burned area between
  t_{k−1} and t_k), cumulative IoU/Dice, area ratio, boundary distances. Calibration must not improve the
  primary at the cost of the growth-only Dice relative to B1 (checked).
- **Optimizer:** SciPy `differential_evolution` in log-parameter space within the bounds of §6.7,
  `seed=20261009`, `popsize=15`, `maxiter=60`, `polish=True` (L-BFGS-B), `vectorized=True`. Each generation is
  one Rust batch call (Rayon across population members × fires), so results do not depend on thread
  timing. Repeat with seeds {1, 2, 3} to show the optimum is reproducible. Each baseline goes through the
  same procedure.
- **Identifiability / equifinality:** (1) the *behavioural set* is every evaluated parameter vector within
  5 % of the best objective; report the 5–95 % range and pairwise rank correlations (expected
  `k`–`a_w` trade-off); (2) a one-parameter profile per parameter (re-optimising the others); (3) a
  parameter whose profile is flat within 5 % is reported as **not identifiable** and fixed at 1, not
  interpreted.
- **Overfitting detection before touching validation fires:** leave-one-calibration-fire-out (3 refits),
  comparing the left-out fire's score with the in-sample score and with B1 under the same procedure.
  Report parameter stability across refits.
- **Lock:** the chosen parameter vector, behavioural set, code commit and config hash go to
  `validation/locked_params.json` **in its own commit**. `make validate` refuses to evaluate a validation
  fire if the current config hash differs from the locked one.

---

## 9. Validation (held-out fires, once)

- **Metrics, per fire × per observed time step, model | B1 | B0 side by side:**
  burned area (model/observed ratio); IoU and Dice on cumulative area; **growth-only Dice** (new area since
  t_{k−1}); mean symmetric boundary distance (m); Hausdorff distance and its 95th percentile (m);
  arrival-time interval error (h, median and mean, with **signed bias**: model early vs late); in both
  continuous Mode A and one-step-ahead mode; Mode B as a secondary row.
- **Error maps:** per step, cells over-predicted (model burned, observed not), under-predicted, agreed,
  and initial. Colour plus hatch, with a legend. Plus an arrival-time difference map (model − observed
  interval, h) with a diverging ramp.
- **Classification audit of "observed burned at t":** NIROPS vs operational (NIFS) perimeter on the same
  day (IoU); fraction of VIIRS detections up to t that fall inside the t perimeter; final NIROPS perimeter
  vs MTBS boundary (IoU) and the MTBS unburned/very-low share inside it (the model cannot represent
  islands). Large disagreements are reported, and the affected steps are flagged before the model is
  scored on them.
- **"Good enough", stated before seeing validation results:**
  - **G1, better than the baseline:** on a validation fire, the model is "better than B1" only if its
    primary error is lower **and** it wins on the majority of evaluated steps. The range across the
    behavioural parameter set is shown as the interval; if intervals overlap, the result is "no
    detectable gain". Otherwise it is stated plainly that the model is not better.
  - **G2, fit for scenario exploration:** in one-step-ahead mode, median growth-only Dice ≥ 0.5 **and**
    median absolute arrival-time error at observed boundaries ≤ 12 h. These thresholds are my
    pre-registered judgement for "useful for comparing scenarios", not literature benchmarks.
  - Network coupling (§11) and scenario results are presented as **reconstructions** only for fires that
    meet G1 and G2. Other fires are shown with their errors and the failure is explained (e.g. spotting
    run, wind error).
- **Hand checks:** a frozen sample (`validation/hand_check_sample.json`): for each validation fire, the
  best, median and worst step by primary error, plus every masked day. Figures show observed perimeter,
  model and B1, with legends. `validation/HAND_CHECKS.md` has an "AI notes" column labelled
  **AI-assisted, pending human review**, and an empty human column.

---

## 10. Sensitivity and uncertainty

- **Physical factors (around the locked parameters):** wind speed multiplier ×[0.7, 1.3] (HRRR 10 m
  speed error); wind direction offset [−30°, +30°]; dead-fuel moisture scenario (one class drier/wetter;
  `m` ∈ [0.7, 1.3]); slope coefficient `a_s` over its behavioural range; fuel map (the previous LANDFIRE
  version as a structural alternative, plus `g` over its behavioural range, plus stale-fuel recoding, §3).
- **Design:** (1) **Morris elementary effects** (r = 20 trajectories × 7 factors = 160 runs per fire) to
  rank factors; (2) **Latin hypercube scenario ensemble**, N = 256 per fire, factors independent and
  uniform within the ranges above, plus parameter vectors drawn from the behavioural set. Seeds come from
  `numpy.random.SeedSequence(20261009).spawn(n)`, one per fire and design. Scenario parameters are generated
  in Python and passed to Rust as arrays, so the Rust kernel has **no RNG**.
- **Artefact checks, reported separately, never as physical drivers:** stencil 16 vs 32; cell size 30 /
  60 / 90 m; ignition jitter (Mode B ± 1 and ± 3 cells); grid orientation (analytic fixture: arrival-time
  error vs wind angle 0–90° in 7.5° steps; on real fires, a 16/32 stencil comparison). A physical
  sensitivity smaller than the artefact spread is not claimed.
- **Probability-of-burning-by-time:** **not claimed by default.** The input ranges are expert ranges, not
  calibrated probability distributions, and 2 validation fires cannot establish reliability. The ensemble
  is shown as **scenario agreement** (share of scenarios with the cell burned by t, and the 10–90 %
  arrival-time range). A reliability diagram on the validation fires is computed as a **diagnostic** and
  shown with that label.

---

## 11. Network coupling (only after validation, only for fires meeting G1 + G2)

```
arrival time  →  modelled closure time per road segment  →  hourly network recomputation
              →  travel time to the nearest exit  /  population without a road connection, by hour
```

- **Data:** TIGER/Line edges (topology from TNIDF/TNIDT node ids), drivable MTFCC classes, assumed
  free-flow speeds per class (stated, varied ±25 %); 2020 census blocks (POP20) assigned to their nearest
  drivable node, with the MAUP/centroid caveat stated; exits = road nodes beyond the domain buffer.
- **Closure rule (a scenario, not observed):** a segment closes at `min(arrival within b of the segment) − L`.
  Central b = 100 m, L = 1 h; scenarios b ∈ {50, 100, 250} m, L ∈ {0, 1, 3} h. Ensemble arrival times give a
  closure-time range per segment.
- **Routing:** multi-source Dijkstra from the exits on the reversed graph, recomputed for each hour
  (≤ 168) with closed edges removed. `scipy.sparse.csgraph` is enough here (a few thousand edges); the
  portfolio's Rust graph story belongs to Healthcare (§12).
- **Outputs by hour:** population (and housing units) without an open path to any exit; median and
  maximum network travel time to the nearest exit for the connected population, vs pre-fire;
  structures within the modelled front (exposure count, if USA Structures is available).
- **Comparison (not validation):** documented closures from InciWeb/ADOT releases (e.g. US 89 during
  the Tunnel Fire). Agreement in timing is reported as a comparison.
- **Wording:** "modelled closure", "population without a modelled road connection", "exposure". No
  evacuation, traffic, warning or consequence modelling, so no "risk" or "evacuation time".

---

## 12. Rust (the core of this project)

**Why Rust here (recorded in METHOD.md):** calibration (≈ 3,000 parameter vectors × 3 fires × 2 seeds),
leave-one-out refits, Morris + LHS ensembles (≈ 400 runs × 5 fires) and the artefact grid add up to
**~25,000 propagations of 0.5–4 M cells with time-dependent edge costs**. A pure-Python label-setting
loop is expected to take minutes per run, which makes this infeasible. SciPy's `csgraph` Dijkstra is fast
but supports only static edge weights (no time-varying wind, no traversal integration). Both statements
are measured in the benchmark, not assumed.

**Ownership:**
- *Rust (`rust/`, crate `firepath_kernels`, PyO3/maturin, uv path dependency)* owns cell state, neighbour
  evaluation (stencil traversal, ellipse ROS, time integration), propagation (time-dependent Dijkstra) and
  **parallel scenario execution** (Rayon across scenarios; each propagation is sequential). It also does
  the streaming ensemble reduction.
- *Python* owns harvest, grids, the Rothermel fuel table, weather fields, scenario sampling, calibration,
  metrics and export. `firepath.reference` is a pure-Python (heapq) implementation of the same algorithm:
  the **oracle**.

**Semantics and tolerance:**
- Arrival times in f64 internally, written as f32 hours. Rust vs reference: |Δt| ≤ 1e-9 · max(1, t) h per
  cell, and identical reached/not-reached status, except cells whose arrival is within that tolerance of
  `T_end` (listed in the test output).
- **Exact ties:** heap key = (arrival, cell index) with `f64::total_cmp`, so the pop order is total and
  deterministic. Dijkstra's final values do not depend on tie order. A symmetric fixture checks that this
  holds. NaN never enters the heap (asserted).
- **Determinism:** no RNG in Rust. Rayon `par_iter` over scenarios with results collected **by scenario
  index**. Ensemble reductions are integer counts (per cell, per report time, u16) merged in index order,
  so they are order-independent. A test runs `RAYON_NUM_THREADS=1` and `=10` and requires **bit-identical**
  outputs.
- **Edge / nodata / non-burnable:** as in §5. Edges never leave the grid. An empty source set gives all
  cells "not reached". A source cell on a barrier is an error.

**Fixtures with analytic answers (Rust tests and pytest against the reference):**
1. Uniform fuel, no wind, no slope, point source: arrival equals the **stencil gauge distance** exactly
   (the convex-hull norm of the stencil vectors), and Euclidean within the 2.7 % / 1.3 % bounds.
2. Uniform wind: the burned area at T is the analytic ellipse with the ignition at the rear focus. Test
   head, back and flank distances and LB, for wind angles 0–90° (grid-orientation error table).
3. Barrier with one gap: arrival behind the wall = path through the gap. A one-cell **diagonal** barrier
   must not be crossed by a knight move.
4. Uniform slope, no wind: upslope elongation and head ROS match `R0 (1 + φ_s)`.
5. 1-D strip with a wind switch at t1: piecewise-linear arrival, exact. FIFO holds.
6. Edges and nodata: border sources, all-barrier grid, empty sources, source inside the initial
   perimeter, non-burnable islands inside the initial perimeter.
7. Rothermel table: `R0` and φ for several SB40 models vs published Scott & Burgan / BehavePlus values
   (tolerance 1–2 % for the transcribed charts). A second independent implementation (`pyretechnics`,
   EPL-2.0, dev dependency only, **[to verify]**) is used if it covers SB40.

**Benchmark (`make bench`, `benchmarks/propagation.json`, all §12 fields):** input sizes (cells, stencil,
horizon, burned cells, scenarios), algorithm, CPU/RAM/OS/toolchain, reference time, Rust time, speed-up,
several sizes.

| Axis | Values |
|---|---|
| Grid | synthetic 256², 512², 1024², 2048², 4096² (heterogeneous fuel/slope, hourly wind) + the 5 real fires |
| Horizon (time steps) | 24 h, 72 h, 168 h of hourly wind (changes burned-cell count and hour crossings) |
| Scenarios | 1, 8, 64, 512 |
| Implementations | Python reference (≤ 512², N = 1, larger sizes **not run** rather than extrapolated) · SciPy `csgraph` Dijkstra on the static-wind case (the best compiled non-Rust comparison) · Rust single-thread · Rust + Rayon (1/2/4/8/10 threads) |
| Harness | `timeit.repeat` (as in Parcel Intelligence), release build, medians and minima, correctness flag per row |

The speed-ups are reported as measured, including a sub-linear Rayon scaling (memory bandwidth) and a
modest gain over SciPy on the static case if that is what the numbers show.

---

## 13. Web app (web-ux process)

**Primary user and tasks** (from §1): an analyst or planner exploring a past fire.
1. See how well the model reproduced the fire through time (observed vs modelled, with the baseline).
2. Scrub through time and read *when* the front reached a place.
3. Compare scenarios (wind ±, direction ±, moisture, fuel map) as changes in arrival time.
4. See when roads close (modelled) and how many people lose a road connection, by hour, with ranges.
5. Read what the model cannot tell them, next to the result.

**First screen (D1 reused):** h1 = the question in plain language; a two-sentence lede with the guardrail
("a reconstruction under stated inputs, not a forecast, not an operational fire model"); the headline =
the validation result on the held-out fires (model vs wind-only baseline), filled from `summary.json`
(D13). It is not a KPI tile row.

**Information architecture:** question → result → workbench (map + panel, D3) → case study (spec §13
order). The fire selector (native radios, D6) shows each fire's role (**calibration** / **validation**)
in its label.

**Time control (new pattern, to record as D19 once implemented):** a native `<input type="range">`
(1-hour steps, label = local time with zone, plus "h since start") with play/pause and previous/next
observed-perimeter buttons. Fully keyboard-operable (arrows, PageUp/Down = ±6 h, Home/End). On phones it
docks under the map, full width, with ≥ 44 px targets, checked at 320–400 px. `aria-valuetext` gives the
human time and "observed perimeter at 21:14 MST" when on one.

**Map encoding.** Modelled burned-by-t is a filled area from the isochrone bands, filtered `t ≤ T`, in a
single-hue sequential ramp by arrival hour (D9). The observed perimeter at the nearest observed time
`≤ T` is a dark outline, dashed for the baseline. In error mode the map shows over-, under- and agreed
areas as colour plus hatch, never colour alone. Scenario agreement uses three contour lines (≥ 10 / 50 /
90 % of scenarios). Self-contained cartography (D10): own hillshade, roads and places from TIGER.

**Scenario comparison (D7 adapted):** the panel always shows all scenarios for the selected place or road
segment as arrival-time bars (central marked, ensemble 10–90 % range) with the baseline beside. Clicking or
searching a road or place gives a text report (D4/D17: phones get a "View report ↓" jump after a tap).

**Road-closure timeline:** a compact chart below the map, with the hour on the x-axis, population without
a road connection (central line + scenario band) and labelled closure ticks for named roads. It is synced
with the time slider and has a table alternative for screen readers.

**Limitations (D15) sit beside the results**, not only at the bottom: a short "what this cannot tell you"
under the validation headline and under the network chart.

**Payloads (rules/web.md; measured before/after):**
- Options considered: (a) arrival-time **COG** decoded in the browser (geotiff.js ≈ 100–200 KB plus
  per-pixel recolouring, and no MapLibre filtering); (b) **raster PMTiles** with encoded arrival times,
  which needs a custom shader layer to threshold by time; (c) **vector isochrones** (hourly bands as
  polygons with `t_h`) in PMTiles, filtered with one MapLibre expression.
- **Decision: (c)** for display. It is styleable, filterable without custom code, and inspectable on
  tap. Budget ≤ 3 MB per fire for the central scenario plus observed perimeters; scenario agreement
  contours are lazy-loaded. The full arrival-time **COG per fire and scenario is a download** for
  analysts, not loaded by the app.
- MapLibre/PMTiles at pinned versions as in D12. One zoom `interpolate` per expression. Glyph URL
  templates unescaped. The dev server supports HTTP Range (`npx http-server`).

**Publication:** to add `firepath/` to Pages the workflow's "Assemble site" step must copy
`projects/firepath/web/` and the root redirect must become a small index of apps. **Both are
shared-structure changes, and I will not make them without your approval (Q4).**

---

## 14. Engineering and testing

**Layout (as Parcel Intelligence):** `projects/firepath/` with `pyproject.toml` + `uv.lock`, `Makefile`,
`METHOD.md`, `DATA_SOURCES.md`, `README.md`, `src/firepath/`, `tests/`, `rust/`, `web/`, `provenance/`,
`benchmarks/`, `validation/`. `data/` is git-ignored (root `.gitignore` already covers `projects/*/data/`).

**Pipeline stages and make targets:**

| Target | Module | Output |
|---|---|---|
| `make probe` | `firepath.probe` | reachability + auth table per source (`provenance/probe.json`) |
| `make harvest` | `harvest` | `data/raw/<fire>/…`, `provenance/harvest_manifest.json` (URL, query, version code, sha256, acquired UTC, service edit date, LANDFIRE version, HRRR keys) |
| `make prepare` | `prepare` | per-fire grid: `data/interim/<fire>/{fuel,cc,ch,dem,slope,aspect,barrier}.tif`, `wind_<hour>.npz` (300 m, UTM-relative U/V), `observed.parquet`, `obs_interval.tif` |
| `make fueltable` | `fuels` | `data/interim/fuel_table.parquet` (R0, C, B, E, β/β_op, WAF inputs per SB40 code × moisture scenario) |
| `make calibrate` | `calibrate` | `data/out/calibration/*.json`, then `validation/locked_params.json` (separate commit) |
| `make validate` | `validate` | per fire × step metrics `data/out/<fire>/metrics.parquet`, error maps, audit, figures |
| `make sensitivity` | `sensitivity` | Morris + LHS, artefact checks, agreement counts |
| `make network` | `network` | hourly closures and population (only for fires with G1+G2) |
| `make bench` | `bench` | `benchmarks/propagation.json` |
| `make web` | `export` | `web/data/*.pmtiles`, `summary.json`, downloads (COG, Parquet) |
| `make test` | — | `pytest -q` + `cargo test -q` |
| `make all` | — | prepare → fueltable → calibrate → validate → sensitivity → network → web |

**Output schema (documented in the README):**
- `arrival_<fire>_<scenario>.tif`: UTM, 30 m, band 1 `arrival_h` float32 = hours since `t0` (UTC `t0` in
  the tags), NaN where band 2 ≠ 1/2. Band 2 `status` uint8: 0 not reached by horizon, 1 reached,
  2 burned at t0 (initial perimeter), 3 barrier/non-burnable, 4 outside domain.
- `metrics.parquet`: fire, role, mode, step_utc, method (model/B1/B0), param_set, area_obs_ha,
  area_mod_ha, iou, dice, growth_dice, mean_bdist_m, hausdorff_m, hausdorff95_m, at_err_median_h,
  at_err_mean_h, at_bias_h, masked.
- `closures.parquet`, `network_hourly.parquet`, `ensemble_agreement_<fire>.tif` (uint16 counts per
  report time + N in the tags).
- JSON export: float32 values cast to float64 before rounding. Counts (runs, kernel calls, scenarios) are
  derived in the pipeline. The app text comes only from `summary.json`.

**Tests:**
- Rust unit and fixture tests (§12), Python reference vs Rust on all fixtures plus 50 seeded random small
  grids (heterogeneous fuel, barriers, hourly wind).
- Stage-boundary tests on **real outputs**: CRS = EPSG:26912, identical grid across rasters, 30 m, extent
  covers observed perimeters + buffer; fuel codes ⊂ SB40 ∪ NB; class proportions preserved after
  resampling; DEM nodata = 0 inside the AOI; slope range plausible; HRRR rotation (test vector:
  grid-relative → earth-relative at a known longitude); all observed perimeter times strictly increasing
  and ≥ t0; LANDFIRE version predates the fire (leakage); the validation lock hash matches; metrics in
  [0, 1] where applicable; JSON number formatting.
- Seeds everywhere stochastic (DE, Morris, LHS, random fixtures), recorded in outputs.

---

## 15. Explicit scope: omitted processes and their expected bias on the validation fires

| Omitted | Expected effect | Where it bites |
|---|---|---|
| **Spotting** | Under-predicts runs that jump barriers/roads and advance ahead of the front. Arrival too late | Tunnel's 19–20 April wind run into Doney Park (likely) |
| **Crown-fire transition** | Under-predicts head ROS in ponderosa/mixed conifer under wind. Calibration pushes `k`/`a_w` up, which then over-predicts surface-fire days | Pipeline (timber on the Peaks); Mangum (calibration) |
| **Dynamic (diurnal) fuel moisture** | Over-predicts night spread, under-predicts afternoon peaks. Error splits by time of day | All fires: diagnosed by day/night error split |
| **Fire–atmosphere feedback / plume dominance** | Misses indrafts and plume-driven runs. HRRR winds are ambient | Long fires with big runs (Telegraph, Bush; calibration) |
| **Suppression and firing operations** | The model over-predicts where lines held. Burnouts make observed growth that is not free spread | Late days of all fires: masks and the 7-day / 90 % window limit this |
| **Sub-cell fuel heterogeneity / fuel-map error** | Roads, rock and small fuel breaks below 30 m are invisible. LANDFIRE errors propagate | Grass/PJ mosaics (Tunnel); covered partly by the fuel-map scenario |
| **Terrain-resolving wind** (no WindNinja) | 3 km winds miss channelling on the San Francisco Peaks and in canyons. Direction errors | Pipeline, Telegraph |
| **Unburned islands** | The model burns all cells inside the front, while MTBS/IR finds islands. This inflates over-prediction | Reported via the MTBS unburned share |

---

## 16. Milestones (vertical slices; each ends with exit criteria and one local commit)

| # | Milestone | Exit criteria | Commit |
|---|---|---|---|
| **M0** | Probe, inventory and screening (the Mac) | `make probe` table for every source (reachable / needs key or account / blocked) committed; NIROPS perimeter inventory with scan times for the pool; `fire_screening.json` frozen with the final fire set and masked days; `df -h` ≥ 30 GB free recorded; open questions answered | `chore(firepath): probe, screening, frozen fire set` |
| **M1** | **Slice 1: one calibration fire end-to-end with the Python reference** (Mangum 2020: mid-size, timber + slope; not a validation fire) | harvest → prepare → fuel table → reference propagation (Mode A and one-step) → B0/B1 → all metrics and an error map for hand-picked (not calibrated) parameters; fixtures 1–7 pass against the reference; stage-boundary tests on real outputs; leakage test passes | `feat(firepath): slice 1 — reference model on Mangum` |
| **M2** | Rust kernel at parity (no optimisation) | the PyO3 crate builds in `uv sync`; all fixtures + 50 random grids agree with the reference within tolerance; bit-identical across thread counts; first benchmark rows at 2 sizes | `feat(firepath): Rust propagation kernel at parity` |
| **M3** | All calibration fires + calibration | harvest/prepare for Bush and Telegraph; DE (3 seeds) for model, B0 and B1; behavioural sets, profiles, leave-one-fire-out; **lock commit** of `locked_params.json` | `feat(firepath): calibration` + `chore(firepath): lock parameters` |
| **M4** | Validation (once) | Tunnel and Pipeline harvested, prepared and evaluated once against the lock; per-fire, per-step table with B0/B1; error maps; audit; G1/G2 verdicts written down; hand-check sample frozen, review sheet with an empty human column | `feat(firepath): validation on held-out fires` |
| **M5** | Sensitivity, ensembles, artefacts | Morris ranking; LHS N=256 per fire; agreement rasters; stencil/cell-size/ignition/orientation tables; physical vs artefact statements | `feat(firepath): sensitivity and scenario ensembles` |
| **M6** | Network coupling | only for fires with G1+G2; closures, hourly population/travel time with ranges; comparison with documented closures | `feat(firepath): road-closure and network exposure` |
| **M7** | Benchmark | full §12 table on the Mac (release build), honest reading | `perf(firepath): propagation benchmark` |
| **M8** | Web app | web-ux pass; `summary.json`-driven text; payload measured; browser check at 320/400/1280 px; keyboard pass; D19+ recorded in `DESIGN_DECISIONS.md` | `feat(firepath): web app` |
| **M9** | Docs, publication prep | README, METHOD, DATA_SOURCES complete; Pages change prepared **only with your approval**; ready for `/quality-gate projects/firepath` | `docs(firepath): case study` |

**Budget (build Mac: M4, 10 cores, 16 GB):**
- **Disk:** raw ≤ 6 GB kept (LANDFIRE ≈ 0.5 GB; 3DEP windowed reads ≈ 0.3 GB; HRRR byte-range messages
  ≈ 2.4 MB × 4 fields × 24 h × 10 days × 5 fires ≈ 11.5 GB **transient**, cropped to AOI on arrival so that
  ≈ 0.1 GB is kept, with each message's sha256 in the manifest; perimeters, MTBS subsets, FIRMS < 1 GB;
  TIGER/blocks/structures for 5 counties ≈ 1.5 GB). Interim ≤ 3 GB; outputs ≤ 3 GB. **Peak ≈ 20 GB, so
  ask for ≥ 30 GB free.** If LFPS clipping is unavailable, LANDFIRE CONUS zips are several GB each per
  layer and version. That is a fallback, decided in M0 with a measured size.
- **RAM, per run:** shared read-only per fire ≈ 16 B/cell (fuel code u8, tanθ/aspect f32, WAF f32,
  barrier bits) + wind (300 m × hours, small); per scenario ≈ 9 B/cell (f64 arrival + u8 state) + heap
  (≤ 24 B × frontier). At 4 M cells: 64 MB shared + ≈ 40 MB per concurrent run → 10 threads ≈ 0.5 GB.
  The ensemble reducer holds u16 counts × 24 report times ≈ 190 MB per fire. Only the central and named
  scenarios keep full arrival rasters. **Total < 2 GB**, well inside 16 GB.
- **Compute (estimates, to be replaced by measured values):** Rust ≈ 0.5–3 s per propagation at 1–4 M
  cells → calibration ≈ 20–40 min with Rayon, ensembles + artefacts ≈ 30 min, benchmark ≈ 30 min. The
  Python reference only runs on fixtures, ≤ 512² benchmarks and slice 1 (minutes per run).

**Risks and mitigations:**

| Risk | Mitigation |
|---|---|
| NIROPS perimeters sparse or without scan times | NIFS archive with a polygon time field; FEDS 12-hourly as a labelled fallback; the alternative fires |
| Data hosts blocked or LFPS unavailable from the Mac | Probe first; LANDFIRE full downloads (budgeted); MTBS via GEE-independent USGS bundle; FIRMS optional |
| Model does not beat the wind-only baseline | Pre-registered G1. Report it plainly; explain via error maps (spotting, wind) |
| Calibration absorbs crown fire/spotting into inflated `k`, `a_w` | Leave-one-fire-out, behavioural ranges, the day/night and masked-day splits |
| HRRR 3 km winds wrong in complex terrain | RAWS comparison; direction-offset scenarios; stated limitation |
| Stencil bias mistaken for physics | Analytic fixtures; 16/32 and cell-size checks; artefact table kept apart |
| Merged incidents (Pipeline + Haywire) | Separate by perimeter ids/time; S6 screening; if not separable, swap to the alternative |
| Rust speed-up over SciPy small on static weights | Report it. The real gain is time-dependent costs and parallel scenarios, which are measured |
| Payload too large for Pages | Simplify isochrones to 30 m; hourly → 3-hourly bands beyond 72 h; COGs as downloads only |

---

## 17. Open questions for you

1. **Q1, fire set.** Approve the **Arizona R3 temporal-holdout set** (calibrate Bush 2020, Mangum 2020,
   Telegraph 2021; validate Tunnel 2022, Pipeline 2022, with the listed alternatives)? The alternative is a
   California R5 pool (e.g. El Dorado 2020, Apple 2020 → Oak 2022, Mosquito 2022). It has richer fuel
   variety but more plume/spotting-dominated growth. The final set is fixed by the M0 screening against
   the pre-registered criteria either way.
2. **Q2, NASA FIRMS MAP_KEY** (free, email registration) for the VIIRS/MODIS timing comparison. Without it
   I drop the FIRMS audit or use FEDS if it is reachable without a login. I will not register on your
   behalf.
3. **Q3, RAWS wind check:** is the WRCC web archive enough, or do you want to obtain a Synoptic API token
   (account required)? Optional. HRRR is the model input either way.
4. **Q4, publication:** may I (later, M9) extend `.github/workflows/pages.yml` to copy
   `projects/firepath/web/` and replace the root redirect with a small index of apps? Both change shared
   site structure.
5. **Q5, where to run M0+.** This cloud session cannot reach the data hosts (proxy 403 for LANDFIRE,
   NIFC, MTBS, FIRMS, gridMET, Census, TNM). Either run harvest on the Mac (as for Project 01), or add
   those domains to this environment's allowed list.
6. **Q6, branches.** The plan is committed on local `feat/firepath` (from `main` at `1035d45`). This
   session's harness also designates `claude/epic-faraday-01rz3x` for pushes. Which branch should carry
   the work when you approve a push?
7. **Q7, build order.** Project 02 (Landslide) has not been started. Is it fine to build FirePath before
   it? If so, the decisions recorded here (CRS per fire, time control D19) become family decisions first.
