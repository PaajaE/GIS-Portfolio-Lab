# Landslide Susceptibility: Plan

> Status: **plan, rev. 3 (2026-10-08): owner decisions and feasibility check in §0b; M1 in progress.** Spec: §6 of `docs/GIS_Portfolio_Lab_v5.md`.
> Nothing has been harvested or implemented. Facts below are marked **verified** (checked against a primary source or
> a live service on 2026-10-08), **planned** (design decision, not yet executed) or **assumption** (to be tested).
> Method details move into [`METHOD.md`](METHOD.md) as they are executed; sources are in [`DATA_SOURCES.md`](DATA_SOURCES.md).

**Question (spec §6):** *Can we build a spatially transferable landslide susceptibility model and show where its
predictions are reliable?*

**Proposed answer shape:** a relative ranking of terrain in Buncombe and Yancey counties, NC, by susceptibility to
the **initiation** of rainfall-triggered shallow landslides. It is learned from the NC Geological Survey inventory of
Hurricane Helene (2024-09-27) on pre-event 2017 lidar terrain. It is validated on held-out watersheds, with a
forward-in-time check in Watauga County (1940 storm → Helene). It is published with separate layers for uncertainty,
training-data density and out-of-domain areas.

---

## §0 Evidence status

| Item | Status | Evidence |
|---|---|---|
| NCGS *Landslide Inventory of North Carolina*: 29,993 polygons; fields FeatureType (Source Area / Transport Zone / Deposit / Outline / Source Area (Reactivated)), ExistenceConfidence, LocationConfidence, LandslideType, SlopeModifier, AssociatedStorm, Basemap | verified | live FeatureServer, layer 2 (`dataLastEditDate` Oct 2026) |
| Helene source areas without anthropogenic modifier (`SlopeModifier = None Apparent`, existence confidence High/Moderate): Buncombe 1,815, Yancey 1,156 | verified | attribute table + centroid–county join |
| More than half of Helene source areas are road- or cut-related (Buncombe 1,815 natural of 3,779; Yancey 1,160 of 2,824) | verified | same |
| Natural Helene source polygons are small: median 84 m², IQR 45–152 m², p95 400 m² (n = 4,752, all counties) | verified | geometry query, areas in UTM 17N |
| 2,970 of 2,971 natural source areas in Buncombe + Yancey were mapped on "2025 UNC Collaboratory imagery & 2025 NCGS lidar change detection" | verified | `Basemap` field |
| Post-Helene orthoimagery (spring 2025, 6 in, leaf-off) covers Buncombe, Yancey and Watauga in full | verified | NC OneMap service description |
| The Helene "Priority 1" post-event lidar is publicly downloadable | **unknown** | named in the same description; not found in the TNM API (2026-10-08) |
| NCGS inspected all of both counties, so mapped absence is meaningful county-wide | **assumption** | consistent with full imagery and lidar coverage; not stated by NCGS |
| 3DEP 1 m DEM, project NC_Phase5_2018_A18, lidar collected 2017-02-11 → 2017-04-11; EPSG:26917; float32; nodata −999999; internal overviews | verified | tile metadata XML; remote header of a tile |
| Pre-event (NC Orthoimagery 2020–2023) and post-event (Helene 2025) orthos export without a token | verified | 256 px `exportImage` test |
| NOAA Emergency Response Imagery for Helene (2024-10-05 → 10-08, ~0.15 m, tiled GeoTIFF with overviews, EPSG:4326) covers the AOI bbox (~1,700 tiles, ~400 GB) | verified | `noaa-eri-pds` S3 listing; remote header |
| Licence of NC OneMap orthoimagery and of NC Composite Building Footprints | **no licence stated** | item metadata |
| USGS slope-relief susceptibility (doi:10.5066/P13KAGU3, Aug 2024, before Helene) exists | verified | USGS data release page |
| Scripted download from ScienceBase | **blocked** (bot challenge) | curl |
| GDAL 3.12.2 in the rasterio wheel has GRIB and MBTiles drivers, no raster PMTiles driver | verified | `rasterio.Env().drivers()` |
| Spatially held-out discrimination will be useful | **assumption** | tested in M4 |
| The model transfers to other storms or regions | **assumption** | only cross-event test is Watauga (M6) |

## §0b Owner decisions and feasibility check (2026-10-08)

**Decisions:**
- AOI = Buncombe + Yancey; Watauga is a separate temporal test; no McDowell or Henderson.
- Check licences before publishing; contact no external organisation without approval.
- The ScienceBase reference is optional and never blocks the pipeline.
- The site root is not changed for now.

**Feasibility inputs:**
- small inventory extract (all phases in the AOI + Watauga bbox)
- county outlines
- WBD HUC-12
- two MRMS 72 h QPE grids (ending 2024-09-28 00Z and 12Z, taking the cell-wise maximum)

They are reproduced by `make feasibility` (M1).

| Check | Result | Consequence |
|---|---|---|
| Positives (natural, existence + location confidence High/Mod) | 2,962: Buncombe 1,806, Yancey 1,156; road-related Helene source areas in AOI: 3,625 | as planned |
| HUC-12s with ≥ 50 % of area in AOI | 32 (median 76 km²); 16 with **zero** positives; 10 with ≥ 50 | five balanced HUC-12 folds are impossible: the two largest HUCs (690, 668) would each be a fold alone |
| Concentration | top 3 / 5 / 10 HUC-12s hold 58 / 74 / 98 % of positives | effectively ~10 informative blocks → wide intervals; per-watershed results are the honest unit of replication |
| Clustering | nearest-neighbour distance median 67 m; K(r)/πr² = 23 at 200 m, 8 at 1 km, 2.5 at 10 km | strong clustering at all scales up to the storm-cell scale |
| Leakage across HUC-12 lines | 99 % of positives have their nearest neighbour in the same HUC-12; pairs < 500 m crossing a HUC-12 boundary: 2 % | HUC-12 boundaries (ridges) separate clusters well, so HUC blocking is effective; a 500 m buffer touches 21 % of positives |
| **Rainfall confounding** | positives per km² by MRMS 72 h total: < 250 mm: 0.01–0.03 (717 km², 0.7 % of positives); 250–300: 0.47; 300–350: 0.71; 350–400: 2.0; > 400: 3.5–4.0. Spearman ρ (HUC-12 rain vs density) = 0.56 | **major:** without handling, the model and its AUC would largely learn where it rained; "no landslide" in low-rain terrain says nothing about susceptibility |
| Inventory method in AOI | 2,949 of 2,962 positives mapped on 2025 Collaboratory imagery + NCGS lidar change detection; 23 % of polygons < 50 m² | method uniform; small failures are mapped, but completeness under canopy is unknown |
| **Watauga 2024 test labels** | 318 Helene outlines (no source areas) mapped on **2024 Nearmap imagery** (not lidar change); modifier: 26 "None Apparent", 175 not assessed, 117 road/cut/fill/mining | different mapping method from the AOI and few confirmed natural failures |
| Watauga 1940 training labels | 1,218 outlines, 97 % Moderate existence confidence, 1940 air photos; median outline 660 m² | 1940 terrain is not available; 2017 lidar is 77 years post-event and may still show the scars |
| Recurrence | Helene → nearest 1940 outline: median 368 m; 12 % within 100 m; 17 outlines overlap a 1940 outline; Helene in Watauga lies inside the 1940 mapping hull (99 %) | the temporal test mostly measures new locations, not recurrence at old scars |
| Watauga rainfall | mean 306 mm (vs AOI positives mostly > 350 mm) | weaker trigger; fewer, more road-dominated failures |

**Verdict: feasible, with four design changes (adopted below).**
1. **Triggered domain.** Training and headline evaluation are restricted to land with MRMS 72 h ≥ 250 mm.
   - That is 1,805 km² holding 99.3 % of positives.
   - The rest of the AOI is shown as "not tested by Helene's rainfall" (hatched) and excluded from headline numbers.
   - The 250 mm cut is a scenario (200 / 300 mm in sensitivity).
2. **Rainfall handling.**
   - Rainfall enters both models as a covariate, to adjust for the trigger, not as a susceptibility factor.
   - The susceptibility product is the prediction **at a fixed reference rainfall** (the triggered-domain median),
     i.e. terrain ranked under equal trigger.
   - The terrain-only model is a contrast.
   - The **primary metric is rainfall-stratified**: within 50 mm bins, plus within-watershed AUC.
   - This replaces the rev. 2 rule "rainfall only for stratification", which the data showed was too weak.
3. **Cross-validation.**
   - **Leave-one-HUC-12-out** (21 HUC-12s in the triggered domain), pooling out-of-fold predictions. This replaces
     five balanced folds.
   - Results are also given **per watershed** for the 10 HUC-12s with ≥ 50 positives, which are the replicates.
   - Intervals by HUC-12 block bootstrap; the effective n of about 10 is stated next to every interval.
   - HUC-10 grouping and leave-one-county-out remain robustness checks.
4. **Watauga is downgraded to an indicative secondary check.**
   - **Test positives:** Helene outlines that are "None Apparent" or not assessed and lie > 30 m from any road
     (independent TIGER check). Expected n ≈ 100–200.
   - **Predictors for this test:** smoothed to ≥ 15 m, so 1940 scar micro-morphology on the 2017 surface carries
     less weight.
   - **Baseline:** "distance to nearest 1940 outline", to show whether any skill is just recurrence.
   - The 2024 labels use a different method (Nearmap imagery, not lidar change), so detection differs from 1940.
   - The result is reported as "indicative" with its interval, never in the headline.

**Licence check (2026-10-08, documents read; nobody contacted):**
- **NC Orthoimagery 2020–2023 and Helene 2025:** both point to the NC OneMap terms. Those state a "free and
  unrestricted use policy" for partner content, say no written release is needed, give a citation, and carry a
  no-warranty clause. The Helene 2025 item lists use constraints "None" and asks for acknowledgement of the NC
  Collaboratory at UNC Chapel Hill. → Using clipped sites with attribution is consistent with the terms.
  **Verified from the terms text. Final confirmation before publishing (M8).**
- **NC Composite Building Footprints:** the licence field is empty and the layer is not on NC OneMap. →
  **Unresolved.** Local analysis only. Before publishing aggregated exposure counts, either find written terms or
  switch to Microsoft US Building Footprints (ODbL; aggregated counts as a produced work with attribution).

**Other data-access findings:**
- Annual NLCD 2023 is not available as a per-year WCS coverage. **NLCD 2021 Land Cover** and **NLCD Tree Canopy
  Cover 2021** are, natively at 30 m in EPSG:5070 (verified with a GetCoverage test). → Use the 2021 vintage for
  both, three years pre-event, which also keeps the vintages consistent.

---

## 1. Problem and decision

- **Users:**
  - North Carolina Geological Survey
  - Buncombe and Yancey planning offices: post-Helene rebuild and new-development screening, slope ordinances
  - emergency management prioritising geotechnical field reconnaissance
  - NCDOT district geotechnical staff
- **Decision:** which slope units to prioritise for site-specific geotechnical review before the next
  extreme-rainfall event.
- **Product:** a **relative ranking** of terrain by susceptibility to *initiation* of rainfall-triggered shallow
  landslides (debris slides and debris flows), expressed as a percentile of hillslope area.
- **Decision metric:** the **capture curve on held-out watersheds**: the share of mapped Helene initiation sites
  that falls in the top *k* % of hillslope area. *k* is a user-chosen screening scenario (default 10 %; reported at
  5 / 10 / 20 %), not a single threshold. Every unit also carries prediction uncertainty, training-data density and
  an out-of-domain flag.
- **Probability policy:**
  - The app shows **no per-cell or per-unit probability**.
  - Calibration is evaluated on held-out folds as a diagnostic. Even a calibrated score only estimates the chance
    that a cell contained a *mapped* initiation *in Helene*. That is not an annual or future probability.
  - What may be shown per class is an **observed, event-specific frequency**, with its confidence interval:
    "in held-out watersheds, X % of units in this class had at least one mapped Helene initiation (95 % CI …)".
- **Wording:**
  - *susceptibility*, not *hazard*: no recurrence, no trigger probability, no runout
  - not *risk*: no consequence or vulnerability
  - exposure (§11) comes only after validation, as "exposure to initiation-susceptible terrain"

## 2. Study area and inventory

### Candidates (checked 2026-10-08)

| | **NCGS Landslide Inventory of NC** | USGS Landslide Inventories across the US v3 (Belair et al. 2025, doi:10.5066/P14AJF8I) | WA DNR Landslide Inventory (WGS DDS-29) | Oregon DOGAMI SLIDO 4.5 / 4.6 |
|---|---|---|---|---|
| Licence | NC DEQ: free, no release agreement, no warranty; access info "NC Geological Survey" | public domain | free download (909 MB zip); map services now require a token; licence text to confirm | free download; licence text to confirm |
| Geometry / mapping | polygons per phase (Source / Transport / Deposit / Outline); Helene mapped on 2025 imagery + NCGS lidar change detection, Nearmap, field | compilation of many inventories; points + polygons | lidar-derived scarps and deposits (SLIP protocol, after Burns & Madin 2009) | lidar-derived deposits and scarps |
| Confidence | existence and location, each High / Moderate / Low with written definitions | coded 1–8 by data and method | to confirm in DDS-29 | `CONFIDENCE` field |
| Type | debris flow, debris slide, flowslide, deep-seated…; **SlopeModifier** separates road cut / embankment / none apparent | type attribute added in v3 | mostly deep-seated | mostly deep-seated deposits |
| Event dates | 21,895 Helene; 1,241 from the Aug 1940 storm (1,217 in Watauga); ~520 other dated (2004 Frances/Ivan, 2021 Fred…); 5,774 undated | machine-readable dates in v3, sparse | sparse | `YEAR` on 7,232 historic points; deposits mostly undated |
| DEM vintage vs events | **3DEP lidar 2017 = 7.5 years before Helene** | varies by source | inventory mapped *on* the lidar that would supply predictors | same |
| Density in candidate AOI | 1.06 (Buncombe) and 1.43 (Yancey) natural High/Mod source areas per km² | low, uneven | high | high, uneven |

### Recommendation
**NCGS Helene initiation zones in Buncombe + Yancey counties** (811 + 1,709 = 2,520 km²), plus a **Watauga County
temporal slice**.

- It is the only candidate where the predictor terrain clearly predates the events. In WA and OR the inventory is
  digitised from the same lidar the predictors would come from, so terrain would encode the scars (circular).
- Source areas are separated from transport and deposit zones. That makes initiation susceptibility a well-posed
  target.
- Confidence fields are explicit, and a field separates natural from road-related failures.
- Inside the AOI, mapping is dense and used one method (§0).
- The USGS v3 compilation stays secondary: it is heterogeneous and does not carry the Helene phases.

**Alternatives:**
- (a) Add McDowell + Henderson (+1,085 natural source areas, +2,100 km²). This requires resolving a 2,570-feature
  undated cluster in McDowell.
- (b) Yancey only (811 km², 1,156 positives): cheaper, but weaker cross-validation.
- (c) WA or OR for deep-seated susceptibility, accepting the circularity. Not recommended.

### Temporal trap
- All predictors are pre-event: 3DEP lidar 2017, NLCD 2021 land cover and canopy, building footprints from 2022/2023 imagery.
- Post-event imagery and lidar appear only (a) in NCGS's labels and (b) in the app's **display-only** before/after
  comparison (§12). They are never model inputs.

### Temporal holdout (Watauga)
- Watauga has 1,217 outlines from August 1940 (mapped from 1940 air photos) and 317 Helene outlines, on the same
  2017 terrain.
- **Design:** train on 1940 and test on Helene. This is forward in time on the same ground.
- **Caveats:**
  - Both events are mapped as *Outlines*, not source areas. The initiation proxy is the top 20 % of each outline by
    elevation, with a sensitivity.
  - The 2017 DEM is 77 years after 1940, so healed 1940 scars may still be expressed. That can only inflate the
    *training* fit. The 2024 test is clean.
  - The Helene mapping method in Watauga is checked in M1.
- Inside Buncombe + Yancey only 96 dated pre-Helene features exist, so no temporal holdout is possible there.

### Licences and attribution
- **NCGS / NC DEQ:** credit "North Carolina Geological Survey, NC Department of Environmental Quality". Show the
  no-warranty statement. No share-alike.
- **Public domain:** USGS 3DEP, WBD, NLCD; NOAA MRMS and ERI; USDA NRCS SSURGO.
- **No licence stated:** NC OneMap orthoimagery and NC Composite Building Footprints. This is open question §15.3.

## 3. Analytical unit

- **Pixel baseline: 5 m grid.**
  - The median natural source area of 84 m² is about 3.4 cells.
  - At 10 m most scars fall within one cell.
  - 1–2 m slope is dominated by micro-relief and would mean 0.6–2.5 billion cells.
- **Slope units: the reporting unit and the second model unit.**
  - Hydrological half-basins (Carrara et al. 1991), the classical basis that `r.slopeunits` refines.
  - **Steps:** a priority-flood fill (Barnes et al. 2014), then D8 flow on a 10 m DEM (mean of 5 m), then channels
    at accumulation threshold *A*. Each sub-basin is split into left and right banks along its channel. Units
    smaller than 0.01 km² are merged into the neighbour sharing the longest boundary.
  - *A* = 0.05 / 0.1 / 0.2 km² is a sensitivity (MAUP).
  - **Tool:** `pysheds` for fill / D8 / accumulation (GDAL has no flow routing). Splitting and merging are project
    code. GRASS `r.slopeunits` is not used: it would need a full GRASS installation, and its iterative refinement
    by aspect variance is not required for a half-basin comparison. This is a recorded deviation.
- **Labels:**
  - **Pixel:** positive if the cell centre lies in a positive polygon (cell-centre rule, as in P01).
  - **Unit:** positive if at least one positive-polygon centroid falls in it. The count and the positive area
    fraction are stored.
- **Predictors per unit:** for continuous predictors, mean, sd and p90 (initiation happens on the steepest part);
  for categorical ones, class area fractions; plus unit area and relief.
- **Registration tolerance:** labels were digitised on 2025 imagery and lidar, predictors come from 2017 lidar.
  - A misfit of a few metres is likely: imagery RMSE ≈ 0.3 m, plus digitising and orthorectification on steep
    slopes.
  - Sensitivity: label dilation by one cell. This is one reason the reporting unit is the slope unit.

## 4. Data and predictors (planned)

| Dataset | Variable | Physical / empirical rationale | Source · vintage · resolution · licence |
|---|---|---|---|
| 3DEP 1 m DEM | slope (°) | shear stress on the failure plane | USGS · lidar 2017-02/04 · 1 m → 5 m mean · PD |
| " | profile and plan curvature (5 m; smoothed 15 m) | convergent hollows concentrate subsurface flow; Appalachian debris flows start in hollows | " |
| " | local relief (r = 50, 250 m) | hillslope energy; the variable of the USGS national slope-relief model | " |
| " | TPI (r = 50, 250 m) | slope position: hollow, side slope, nose | " |
| " | roughness (sd of slope, r = 25 m) | bedrock outcrop vs soil-mantled slope | " |
| " | log upslope contributing area (10 m D8); distance to channel | saturation potential (spec: flow accumulation) | " |
| " | northness, eastness | moisture and vegetation; **event-direction caveat**, flagged in the driver audit | " |
| NCGS Geologic Map of NC (1985) | lithology group (~5 classes) | weathering, residual-soil thickness | NCGS · 1:500,000 · free · coarse-scale caveat |
| SSURGO (Soil Data Access) | depth to restrictive layer; hydrologic soil group; clay % | thin colluvium over bedrock; infiltration | USDA NRCS · PD · map units are partly slope phases, so slope-phase names are never used |
| NLCD 2021 Land Cover (MRLC WCS) | land-cover group (forest / developed / open-agricultural / other) | root reinforcement; disturbance | USGS / MRLC · 30 m · PD (changed from Annual NLCD 2023, §0b) |
| NLCD Tree Canopy Cover 2021 (MRLC WCS) | canopy % | root cohesion (continuous) | USFS / MRLC · 30 m · PD; kept only if not redundant with land cover |
| MRMS MultiSensor QPE 72 h Pass 2, ending 2024-09-28 00Z and 12Z (cell-wise max) | storm-total rainfall | **trigger covariate**: defines the triggered domain, adjusts the models; the product is predicted at a fixed reference rainfall (§0b) | NOAA · ~1 km · PD · GRIB2 (driver present) |
| WBD HUC-12 / HUC-10 | cross-validation groups | independent hydrological blocks | USGS · PD |

**Deliberately dropped:**
- **elevation:** a proxy for Helene's orographic rainfall, so it would encode the trigger footprint
- **distance to road:** encodes road-related failures and mapping access
- **PRISM normal precipitation:** weak gradient within 2,500 km², collinear with elevation
- **drainage density:** descriptive statistic at unit level only

**Collinearity and categories:**
- Slope, relief, roughness and TPI are expected to have Spearman ρ > 0.8. Check ρ and VIF inside the training
  folds; the logistic regression keeps a set with VIF < 5.
- The gradient-boosting model keeps all of them, and importance is reported per predictor *family* (grouped
  permutation).
- Categories are one-hot with a reference level in the logistic regression and native categoricals in
  gradient boosting. Classes under 1 % of area are merged.

**Display-only data (never model inputs):**
- NC Orthoimagery 2020–2023 (pre) and Helene 2025 (post), both 6 in and leaf-off
- NOAA ERI October 2024, the public-domain fallback for "post"
- Helene 2025 lidar hillshade, only if publicly downloadable

## 5. Harmonization (planned)

- **CRS:** EPSG:26917 (NAD83 / UTM 17N, metres), the native CRS of the 3DEP tiles (verified). The DEM is
  aggregated, never reprojected. Vectors are reprojected locally with PROJ. NC State Plane (US feet) is avoided.
  Vertical: NAVD88 metres.
- **Grid:** 5 m with origin on the 5 m UTM lattice. Extent = AOI + 2 km buffer, which covers the largest kernel
  (250 m) and watersheds crossing county lines. Units truncated by the buffer edge are excluded.
- **Resampling:**
  - DEM: 1 m → 5 m `average` per tile, then mosaic.
  - Continuous 30 m / 1 km layers: `bilinear` onto 5 m.
  - Categorical layers: `nearest`, or vector rasterization by cell centre.
  - Hydrology DEM: 10 m = `average` of 5 m.
- **Nodata:**
  - Declared per layer; never zero.
  - Kernels are strict: any nodata or off-grid cell in the window gives nodata.
  - Cells with nodata in any predictor are excluded and mapped as "no data", with the share reported.
  - Water (NLCD 11 + NHD) is outside the domain.
- **Edges:** the 2 km buffer means interior windows are complete. 3DEP tile overlaps (6 m) are mosaicked
  first-valid, with a seam-difference test.
- **Display imagery** is warped to EPSG:3857 only for tiling.

## 6. Sampling design (planned)

- **Positives:**
  - natural Helene `Source Area` and `Source Area (Reactivated)` polygons
  - existence and location confidence High or Moderate (Low ≈ 30 features dropped)
  - `AssociatedStorm` normalised (three Helene spellings)
  - Transport zones and deposits are never positives.
  - **Variants:** (i) including road-related source areas, as a contrast that exposes the road artefact;
    (ii) High confidence only.
- **Negatives** (mapped absence ≠ true absence), drawn from the domain minus:
  - every mapped polygon of every phase, storm and confidence, + 30 m
  - undated features + 30 m
  - road corridors (15 m from centreline), so that excluded road-related failures do not teach "near road = safe"
  - water
- **Domain:**
  - **Headline domain** = hillslopes: slope ≥ the 1st percentile of positive-cell slope, outside high-intensity
    developed land.
  - The full domain is reported as a contrast, labelled as inflated by trivial flats.
  - Headline numbers are split forested vs developed hillslopes.
- **Ratio:**
  - Training: all positive cells + 10× random negatives per fold (1:5 and 1:20 as sensitivity).
  - Evaluation: all positives + a 2 % random sample of test-fold negatives, weighted to the true prevalence.
  - King & Zeng (2001) intercept correction for case-control sampling.
- **Inventory-bias checks:**
  1. **Method:** uniform inside the AOI (verified), so method bias is low.
  2. **Detection:** lidar change detection and leaf-off imagery under-detect small or shallow failures and those
     under intact canopy. We report the size distribution of positives and a sensitivity excluding polygons
     < 50 m².
  3. **Effort:** positives per km² by HUC-12 and county (Yancey 1.43 vs Buncombe 1.06). We test whether the
     difference survives conditioning on rainfall and terrain. If it does not, we state that mapping effort may
     differ.
  4. **Residual audit:** is predicted susceptibility associated with inventory density, county line or DEM tile
     edges beyond terrain? This uses partial correlation of residuals.
- **Audit of the natural/road rule** against independent data:
  - the share of `None Apparent` source areas within 20 m of a road or building
  - the share of road-coded ones more than 100 m from any road
  - Conflicts go to `validation/modifier_conflicts.csv`.
- **Terminology:** a high-ranked unit without a mapped initiation is "high susceptibility, no mapped Helene
  initiation", never "false positive" or "model error" in the app. Helene did not test every susceptible slope
  equally, and not every failure was mapped.

## 7. Models (planned)

- **Baseline:** L2 logistic regression on the VIF-pruned, standardized set + one-hot categories. Coefficients are
  reported with fold ranges.
- **Advanced:** scikit-learn `HistGradientBoostingClassifier` with native categoricals. scikit-learn is needed
  anyway, so no LightGBM dependency. Random forest only if gradient-boosting tuning proves unstable.
- **Tuning:** a small grid (learning rate, max leaf nodes, min samples per leaf, L2), **only inside training folds**
  (inner CV grouped by HUC-12).
  - Scaling, VIF pruning, feature selection and calibration are fitted in a per-fold `Pipeline`.
  - The outer test folds never influence any fitted step.
- **The same two models on slope-unit features.** Pixel and unit are compared at matched area capture.
- **Two score sets per unit:**
  - **out-of-fold (OOF) rank:** each unit scored by the model that did not see its watershed. All validation
    views, hit/miss layers and threshold-slider metrics use it.
  - **final-model rank:** fit on all data; this is the susceptibility product.
  - The app labels which is shown. Their rank shift is reported.
- **Reproducibility:** seeds in `config.py`; fold assignment frozen in a file.

## 8. Validation design (planned)

> **Revised after the feasibility check (§0b).** The primary design below supersedes the earlier "5 balanced
> HUC-12 folds".

- **Primary: leave-one-HUC-12-out inside the triggered domain** (21 HUC-12s; 32 in the AOI, median 76 km²).
  - Out-of-fold predictions are pooled.
  - A 500 m buffer of training data is removed around the held-out watershed.
  - **Why watersheds:** 99 % of positives have their nearest neighbour in the same HUC-12, and only 2 % of pairs
    within 500 m cross a HUC-12 line, so ridgelines separate the clusters.
  - **Block size:** checked by a residual variogram in M4. HUC-10 grouping is a robustness check.
- **Replicates:** the 10 HUC-12s with ≥ 50 positives get their own held-out AUC and capture. The median and
  range across them is reported with every pooled number, and the effective n of about 10 is stated next to
  intervals.
- **Rainfall-stratified primary metrics:** AUC and capture within 50 mm rainfall bins (weighted average), plus
  within-watershed AUC. A pooled AUC across the full rainfall range is shown only as a contrast.
- **Harder transfer tests:**
  1. **Leave-one-county-out:** Buncombe → Yancey and the reverse.
  2. **Distance decay:** performance vs distance to the nearest training watershed.
  3. **Watauga temporal holdout** (§2), plus applying the Buncombe + Yancey model to Watauga-Helene.
- **Rainfall stratification:**
  - AUC and capture are reported within MRMS storm-total terciles. Without this, held-out watersheds with little
    rain look like model failures when the trigger was absent.
  - A contrast model that includes rainfall shows how much apparent skill is the trigger footprint.
- **Positive clustering:**
  - Positives per fold and per HUC-12. Folds with < 20 positive units are flagged.
  - HUC-12s with < 10 positives get no per-HUC score ("too few to evaluate").
- **Contrast only:** a random pixel split on the same data, to show leakage inflation. Never the headline.
- **Metrics on held-out data:**
  - ROC-AUC and PR-AUC (with the prevalence baseline)
  - Brier score and Brier skill score
  - a reliability diagram (10 bins), with isotonic calibration fitted on inner folds as a diagnostic
  - confusion matrices at the top 5 / 10 / 20 % area thresholds
  - capture (success / prediction-rate) curves
  - a **spatial error map** per HUC-12 and per unit
- **Uncertainty of comparisons:**
  - fold-level values + a HUC-12 **block bootstrap** (2,000 resamples) for each metric and for Δ(GBM − LR)
  - If the interval contains 0, the result says "the advanced model is not detectably better".
- **Leakage checklist:**
  - adjacent cells across folds (buffer)
  - preprocessing fitted on all data
  - target-derived features (no inventory density; no SSURGO slope-phase names)
  - post-event predictors
  - one landslide split across folds (folds by polygon membership)
  - tuning on test folds
  - road artefact (corridor masked)
  - duplicate polygons (geometry hash)
- **Reference comparison** (labelled "comparison", scored on the same held-out folds):
  - (1) **USGS slope-relief threshold susceptibility** (Belair et al. 2024, doi:10.5066/P13KAGU3; 90 m; published
    August 2024, before Helene). It measures national, slope/relief-based susceptibility to all landslide types.
  - (2) **NCGS Channelized Debris Flow Model** (source area and transport path). It measures debris-flow pathways
    "susceptible during a large storm event", and NCGS states it produces more false positives than true
    positives.
  - The USGS Helene preliminary hazard estimate includes rainfall. It is a *hazard* product, cited as a different
    construct and not scored.
- **Transferability limits, stated in the app and README:**
  - within-event spatial CV is interpolation inside one storm footprint
  - Watauga is the only cross-event test, with small n
  - nothing here supports transfer to other physiographic regions, deep-seated landslides, road-cut failures,
    non-rainfall triggers, or terrain changed after 2017
  - the area of applicability covers predictor space, not trigger or process space

## 9. Uncertainty (separate layers, planned)

1. **Susceptibility:** final-model rank percentile of hillslope area.
2. **Prediction uncertainty:** p10–p90 spread of the rank percentile over 30 refits on HUC-12 block-bootstrap
   samples.
3. **Training-data density:** kernel density (2 km bandwidth) of *all* mapped features, plus the mapping-method
   layer. It shows where labels are thin, not where landslides are few.
4. **Out-of-domain:** area of applicability (Meyer & Pebesma 2021).
   - A dissimilarity index on importance-weighted standardized predictors, with the threshold from the
     cross-validated index.
   - Implemented with scikit-learn `NearestNeighbors`.
   - Units outside are hatched and excluded from headline numbers.
5. **Sensitivity** (one at a time, table as in P01):
   - slope-unit threshold *A*
   - negative buffer 15 / 30 / 60 m
   - negative ratio
   - positive definition (incl. road-related; high confidence only; excluding < 50 m²)
   - label dilation by one cell
   - grid 5 vs 10 m
   - domain threshold
   - leave-one-county-out
   - rainfall contrast model
   - Watauga initiation proxy

## 10. Rust (planned)

- **Kernels** (pure-Rust crate in `rust/` with a PyO3 feature built by maturin, as in P01):
  1. **Multi-scale square-window statistics**, one pass per radius: mean and sd from summed-area tables (f64);
     min and max by van Herk / Gil-Werman (O(1) per cell). Local relief, TPI and roughness derive from these.
  2. **3×3 multi-output terrain pass:** slope, aspect, profile and plan curvature (Zevenbergen & Thorne 1987) and
     TRI (Riley et al. 1999) in one sweep.
  3. *Candidate, only if measured:* priority-flood + D8 accumulation, if `pysheds` is a bottleneck in speed or RAM.
- **Oracle:** a NumPy/SciPy reference, using explicit loops on small fixtures and nan-aware
  `scipy.ndimage.generic_filter` on medium ones.
  - There is no `gdaldem` in the wheels, so the 3×3 formulas are implemented from the papers.
  - They are tested on analytic surfaces: a plane gives exact slope, a paraboloid exact curvature; plus flats and
    ties.
- **Tolerance:** min, max and relief exact; mean, sd, TPI and curvature rtol 1e-9 in f64; outputs stored as f32.
  Windows are square, a documented simplification of circular windows.
- **Edge and nodata semantics:** strict. Any nodata or off-grid cell in the window gives nodata, and empty input
  gives empty output. Tested on borders, holes, all-nodata, 1×1, flats and ties.
- **Benchmark** (`make bench`, release build, `timeit` medians, Apple M4 / 16 GB, single thread):
  - sizes 1k², 4k², 8k² cells and the full 5 m AOI (~116 M cells, tiled)
  - radii 1, 5, 10, 50 cells
  - reference: SciPy C filters for the fair comparison, the nan-aware Python version for the semantic one
  - all §12 fields written to `benchmarks/terrain_kernels.json`
- **Expected result:** a 1–3× speed-up over SciPy on plain mean/max. Any gain should come from nodata-aware
  multi-output passes. It is reported as measured, including small or negative results.
- **Not in Rust:** I/O, warping, mosaicking, rasterization (GDAL/rasterio) and ML (Python).

## 11. Exposure (only after the M5 validation passes; planned)

- **Data:**
  - **Buildings:** NC Composite Building Footprints (2022 Northern Mountains / 2023 Southern Mountains imagery,
    pre-event; primary structures ≥ 800 ft²). The licence is open (§15.3); the public-domain fallback is TIGER
    for roads and Microsoft US Building Footprints (ODbL) for buildings.
  - **Roads:** NCDOT Road Characteristics or TIGER/Line.
- **Metric:** buildings (footprint centroids) and road km in the top-*k* % units by out-of-fold rank, inside the area
  of applicability, per HUC-12, at *k* = 5 / 10 / 20 % and by uncertainty class.
- **Wording:** "buildings located in terrain the model ranks most susceptible to landslide *initiation*". Not risk,
  not damage, and **runout is not modelled**: many Helene impacts were downslope of the source.
- **Comparison:** the NCGS *Observations* layer (impacts on roads and structures) is a comparison with observed
  impacts, labelled as such.

## 12. Web app: short story + full map (planned; `web-ux` process)

**Users:** primarily a county planner or NCGS geologist; secondarily a portfolio reviewer.

**First screen:**
- **h1:** "Where in Buncombe and Yancey counties is terrain most susceptible to landslides like Helene's, and
  where can the model be trusted?"
- **Lede:** susceptibility, not hazard or risk; initiation only.
- **Headline** from `summary.json` (D13): held-out capture at *k* = 10 % with CI, split forested vs developed
  hillslopes (D2). No probabilities.

**Core tasks:**
1. See which terrain ranks most susceptible.
2. Judge how well that ranking matched Helene in held-out watersheds, and where it failed.
3. Check how trustworthy one place's ranking is (uncertainty, density, out-of-domain).
4. Choose a screening threshold and see its trade-off.
5. See exposure per watershed.

**Information architecture.** This extends D1 deliberately (to be recorded in `DESIGN_DECISIONS.md` when
implemented): question → headline → **short story (5 steps)** → workbench (full map, D3) → case study in spec §13
order.

### Story (one sticky map; step text filled from `summary.json`)
1. **What happened:** Helene and the mapped initiations (natural vs road-related), with a before/after comparison
   at one curated site.
2. **What the model sees:** terrain predictors at that site (hollows, steep slopes).
3. **The ranking and the threshold:** the susceptibility map, with the threshold slider introduced.
4. **Where it worked and where it didn't:** held-out hits and misses, and the per-watershed error map with
   "too few to evaluate" hatching.
5. **Where not to trust it:** out-of-domain hatch and the density layer, then "Explore the full map".

**Story accessibility:**
- Steps are reachable by Next/Previous buttons.
- Scroll-driven changes respect `prefers-reduced-motion`.
- The text carries the message without the map.
- Built on IntersectionObserver, no scrollytelling library.
- On phones the map is sticky at 50 vh with the steps below.

### Workbench controls (all native and keyboard-operable)
- **View** (radio group, D6): Susceptibility · Prediction uncertainty · Training-data density · Held-out
  validation.
  - These are never merged into one bivariate colour.
  - The out-of-domain hatch is a separate toggle, on by default.
- **Model variant** (radio group): gradient boosting · logistic regression. The USGS national map is added as a
  *comparison* only if obtained.
  - Variants are compared mainly by capture curves in one chart with confidence bands, plus a sentence that says
    "not detectably better" when the interval includes 0.
  - On the map the switch swaps the rank field. A difference map is added only if the rank shift matters (decided
    in M5).
- **Threshold slider:** `<input type="range">` over *k* = 1–30 % of hillslope area, in 1 % steps, with snap points
  at 5 / 10 / 20 %.
  - **Map:** a single MapLibre filter on a precomputed rank percentile; no computation in the browser.
  - **Readouts** from precomputed out-of-fold metrics with confidence intervals:
    - capture of held-out Helene initiations
    - area share
    - observed event-specific frequency in the flagged units
    - buildings and road km flagged
  - **Controls:** `aria-valuetext` reads the full sentence, and ± buttons support touch and precision.
  - **Why a slider and not D6 radios:** the threshold is an ordinal continuum with many meaningful values. The snap
    points keep the reported scenarios.
  - **The text states** that the slider changes a screening *policy* (how much area to flag), not the model.

### Vertical swipe ("Compare" mode)
- **(a) Before/after imagery at 4–6 curated sites** (~2 × 2 km each): NC Orthoimagery 2020–2023 | Helene 2025.
  They are like-for-like: 6 in, leaf-off.
  - **Site selection:** a frozen rule (`validation/story_sites.json`): the largest clusters of natural initiations,
    one high-susceptibility site with no mapped initiation, and one miss.
  - **Payload:** WebP tiles z12–18, ~4–8 MB per site per epoch, loaded lazily.
  - **Feasibility:** export is verified. **Publication depends on the licence (§15.3).**
  - **Fallback:** NOAA ERI Oct 2024 (public domain, leaf-on, only larger scars visible) for "post", and the
    project's 2017 hillshade for "pre", labelled as different sensors and seasons.
  - A full-AOI imagery swipe is **not planned**: hundreds of GB of source, and hotlinking third-party image
    services conflicts with D10 and depends on their uptime.
- **(b) Prediction | mapped landslides (whole AOI):**
  - out-of-fold susceptibility on the left
  - mapped Helene features on the right, over the 2017 hillshade; natural vs road-related distinguished by pattern
    and shape, not colour alone
  - **UI note:** a swipe hides one side exactly where you compare. Precise co-location is shown in the "Held-out
    validation" view (initiation points over ranks) and in the capture curve. The swipe is the overview, not the
    evidence.
- **(c) Pre/post lidar hillshade:** only if the Helene lidar is publicly downloadable; display only.
- **Implementation:**
  - Two synchronized MapLibre maps with a clip divider, our own small module (no compare plugin unless it proves
    simpler).
  - The handle is `role="slider"`, arrow-key operable and touch-draggable, kept separate from map gestures.
  - **Verified at 320 px in M8.** If the handle conflicts with cooperative gestures, phones get a Before/After
    toggle instead.

### Failure and uncertainty views
- **Held-out validation view:**
  - initiation points by out-of-fold rank band: top 10 % / 10–30 % / missed (bottom 70 %), with distinct shapes
  - per-HUC-12 capture choropleth with the "too few to evaluate" hatch
  - a list of the largest missed clusters, linked to the map
- **Charts** (checked at 320–400 px; legends; text equivalents):
  - capture curves for logistic regression, gradient boosting and the reference, with CI
  - spatial vs random-split AUC
  - reliability diagram, with the reason probabilities are not shown
  - rainfall-tercile performance
  - leave-one-county-out and Watauga results
- **Unit report** (tap or search; D4; D17 "View report" button on phones):
  - final and out-of-fold rank
  - uncertainty band, density, area-of-applicability status
  - mapped-initiation status, phrased as in §6
  - predictor values vs the AOI distribution
- **Search:** HUC-12 names and road names from a local index; no geocoder.

### Encoding and delivery
- **Colour:**
  - Susceptibility: a warm single-hue sequential ramp. The family teal already means "robustness" in PI, so this
    deviates deliberately.
  - Uncertainty: grey sequential. Density: purple sequential.
  - Out-of-domain and "too few to evaluate": hatches (D9).
  - Base: own 2017 hillshade (D10).
- **MapLibre rules:** one zoom `interpolate` per expression (`case` inside the stops); glyph URL with unescaped
  `{fontstack}/{range}`.
- **Numbers:** float32 cast to float64 before rounding for JSON; UI number formatting is tested.
- **Payload:**
  - slope-unit vector PMTiles with ranks, uncertainty, density, area-of-applicability flag, label and HUC (≤ 15 MB
    expected)
  - 5 m rank raster as lazy WebP PMTiles (~25 MB), via the GDAL MBTiles driver + `pmtiles convert`, or
    `rio-pmtiles`, decided in M8
  - curated imagery sites, lazy
  - `summary.json` with the per-*k* metrics table and story numbers
  - Target ≤ 150 MB on Pages, measured.
- **GitHub Pages:**
  - Extend `.github/workflows/pages.yml` to copy both apps.
  - Replace the root meta-refresh with a small landing page with two cards. **Asked before changing the root.**
  - Add a `landslide-web` entry to `.claude/launch.json` (http-server@14.1.1, port 8138, HTTP Range).

## 13. Engineering and testing (planned)

- **Layout:** as in P01, under `projects/landslide-susceptibility/`, with package `src/landslide/` and crate `rust/`.
- **Dependencies:** as in P01 (numpy, scipy, rasterio, geopandas, pyogrio, pyarrow), plus:
  - **scikit-learn:** logistic regression, gradient boosting, grouped CV, isotonic calibration, nearest neighbours
  - **pysheds:** D8 hydrology, not available in GDAL
  - **matplotlib:** dev only, for figures
- **Make targets:**
  - `harvest`: inventory snapshot; DEM tiles → 5 m by download-aggregate-delete; SSURGO, NLCD, geology, MRMS, WBD,
    roads, buildings and reference products; writes `provenance/harvest_manifest.json` with SHA-256, query URLs,
    counts and service edit dates
  - `prepare`, `terrain`, `units`, `sample`, `model`, `validate`, `uncertainty`, `exposure`
  - `sites`: frozen site rule + windowed imagery exports
  - `bench`, `web`, `test`, `serve`
  - `all` = prepare → web
- **Fixtures:**
  - analytic DEMs (plane, paraboloid, cone, step, nodata hole), 7×7 to 64×64
  - a three-unit synthetic slope-unit case
  - a 20-polygon inventory snippet covering every FeatureType, storm spelling and modifier
- **Stage-boundary tests on real outputs** (skipped when `data/` is absent):
  - CRS 26917, 5 m, aligned origin
  - nodata share in the domain < 0.1 %
  - predictor value ranges
  - positives within the domain; no negative within 30 m of a mapped polygon
  - folds are HUC-pure; no unit in two folds
  - prevalence matches the inventory
  - scores in [0, 1]
  - per-*k* table: capture monotone in *k*, area share ≈ *k* ± 0.5 %
  - every `summary.json` number traces to an output file
  - a string lint so that "probability" never sits next to a susceptibility value in app text
- **Output schema (documented in README):**
  - `data/out/units.parquet`: unit_id, huc12, county, fold, label, n_sources, predictors…, rank_final, rank_oof_lr,
    rank_oof_gbm, unc_p10_p90, density, di, in_aoa, n_buildings, road_km
  - rasters `susceptibility_5m.tif`, `uncertainty.tif`, `density.tif`, `aoa.tif`
- **Hand checks:**
  - **Sample**, frozen in `validation/hand_check_sample.json`: per susceptibility class two units with and two
    without a mapped initiation; the four largest misses on the error map; two out-of-domain units.
  - **Figures:** pre-event hillshade + model layers, with legends.
  - **Sheet:** `validation/HAND_CHECKS.md` with an empty human column. Labelled "AI-assisted, pending human review"
    wherever cited.
- **No typed results:** app text numbers come from `summary.json`; counts such as kernel calls are derived.

## 14. Milestones, budget, risks

| M | Slice | Exit criteria (one local commit each; push only with approval) |
|---|---|---|
| M1 | Scaffold, harvest, data QA | `uv sync` builds; inventory snapshot frozen (GeoParquet + query date + `lastEditDate` + checksum); inventory audit table reproduces §0 counts; DEM dates recorded; MRMS GRIB read; licences of NC orthos and footprints settled; Helene lidar availability and the Watauga mapping method checked; reference products obtained or dropped |
|  | **M1 status 2026-10-09** | **done:** snapshot frozen (2,962 positives reproduced by test); every DEM tile dated and pre-event; MRMS GRIB read; NC ortho terms read (free use, citation); footprints licence unresolved (local only); Helene lidar not public (pairing (c) shelved); Watauga 2024 mapped on Nearmap imagery; ScienceBase optional, not obtained; NCGS debris-flow model is post-event (2025-04) and query-disabled → see DATA_SOURCES. Report: `validation/M1_DATA_QA.md` |
| M2 | Terrain kernels | reference + Rust pass fixtures including edges and nodata; full-AOI predictors; `benchmarks/terrain_kernels.json` |
| M3 | Stack, slope units, sampling | harmonized stack passes boundary tests; units at three thresholds; labels, negatives, modifier audit CSV, density layer |
| M4 | Baseline + validation harness | HUC-12 folds frozen; logistic-regression spatial-CV metrics + random-split contrast; variogram check; reference comparison |
| M5 | Advanced model | nested-tuned gradient boosting; Δ vs baseline with block-bootstrap CI; calibration diagnostic; error map; grouped importance + artefact audit |
| M6 | Uncertainty, transfer, sensitivity | bootstrap ensemble; area of applicability; sensitivity table; leave-one-county-out; rainfall strata; distance decay; Watauga 1940 → 2024 |
| M7 | Exposure, hand checks, summary | exposure per HUC-12 with wording; frozen hand-check and story-site samples; figures and sheet; `summary.json` |
| M8 | Web app + Pages | story, slider and swipe built on real outputs; verified in a browser at 320 / 400 / 768 / 1280 px with a keyboard-only pass; workflow builds both apps (root change only after approval) |
| M9 | Docs + handoff | README / METHOD / DATA_SOURCES complete; `/quality-gate` triggered by you |

### Budget (estimates, to be measured)
- **Network:** ~20 GB in total.
  - ~40 DEM tiles of 300–450 MB each for Buncombe + Yancey + buffer, plus ~10 for Watauga.
  - Tiles are processed one at a time, so at most ~1 GB of raw DEM sits on disk at once.
  - Curated imagery ≤ 2 GB.
- **Disk:**
  - 5 m stack (~116 M cells × ~20 layers, deflate) ≈ 5–7 GB
  - Watauga ~2 GB, outputs ~2 GB, web ≤ 150 MB
  - **Peak ≤ 15 GB of ~65 GB free.**
- **RAM:**
  - kernels on 4096² tiles with a halo ≤ 2 GB
  - `pysheds` on the 10 m grid (~29 M cells) ~3–4 GB
  - training sample < 1 GB; prediction chunked
  - **Peak target ≤ 8 GB of 16 GB.**
- **Time:**
  - harvest 1–2 h, network-bound
  - `make all` ~1–2 h, dominated by the 30-model bootstrap
  - roughly 8 working sessions for M1–M9

### Key risks (ordered) → mitigation
1. **A single trigger event.** Susceptibility learned from Helene mixes terrain predisposition with Helene's
   rainfall footprint, and transfer to other storms is barely testable.
   → Elevation excluded, rainfall strata, a rainfall contrast model, Watauga, and explicit transfer limits.
2. **Inventory completeness and detection bias** (small, shallow, under-canopy failures; possible differences in
   county effort; live service).
   → Snapshot, the size-threshold sensitivity, the density layer, the residual audit, and "no mapped initiation"
   wording.
3. **Licences for display imagery and footprints** (no licence stated).
   → Decision §15.3, with public-domain fallbacks (NOAA ERI, project hillshade; TIGER / Microsoft).
4. **ScienceBase bot challenge.** → Manual download (§15.4), or drop the USGS comparison.
5. **Small source polygons vs the 5 m grid, plus 2017 ↔ 2025 misregistration.** → Dilation sensitivity; slope unit
   as the reporting unit.
6. **Too few independent blocks** if the variogram forces HUC-10. → Report the fold spread and wide intervals
   honestly.
7. **Interaction scope** (story + slider + swipe). → Built only after M7 on real outputs. The phone swipe falls back
   to a toggle if testing fails. No feature without data behind it.
8. **Technical:**
   - `pysheds` RAM → process per HUC-10, or the Rust kernel.
   - The Rust speed-up may be small → reported as is.
   - SSURGO slope phases → property attributes only, plus a with/without-soils test.
   - 1940 outlines in Watauga are a different mapping method → proxy sensitivity; labelled as a secondary test.

## 15. Open questions (decisions for the project owner)
*Decided 2026-10-08 (§0b):*
- *Q1: Buncombe + Yancey + the Watauga test.*
- *Q2: site root not changed for now.*
- *Q3: check terms before publishing; no contact.*
- *Q4: ScienceBase optional and non-blocking.*

1. **AOI:** Buncombe + Yancey + the Watauga temporal slice (recommended), add McDowell + Henderson, or Yancey only?
2. **Site root:** replace the redirect with a small landing page listing both apps? (Asked again before the change
   in M8.)
3. **Licences:** use the NC Composite Building Footprints and NC OneMap orthoimagery, which state no licence?
   Options: an inquiry to NC OneMap (outward-facing, only on instruction), or public-domain sources only
   (NOAA ERI + project hillshade for the swipe; TIGER / Microsoft for exposure).
4. **ScienceBase:** will the owner download the USGS slope-relief susceptibility map (doi:10.5066/P13KAGU3)
   manually in M1?

## Readiness
- **Ready for M1** (scaffold, harvest, data QA) once §15.1, §15.3 and §15.4 are answered.
- **Not ready for modelling** until M1 has frozen the inventory snapshot and settled the licences.
