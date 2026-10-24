# Landslide Susceptibility — Method

> Status: **draft** — M1 (harvest + QA), M2 (terrain kernels), M3 (stack, slope units, sampling) and M4 (baseline +
> spatial validation) done; M5 (advanced model) stopped by its pre-registered rule; owner chose the 5 m LR (2026-10-10);
> M6 (uncertainty, transfer, sensitivity) done: robust locally, not transferable, geology confound found. Spec section: §6.
> Each statement is tagged **[verified]** (checked against a primary source or live service on 2026-10-08),
> **[planned]** (design, see [`PLAN.md`](PLAN.md)) or **[assumption]** (to be tested). Results will replace the
> planned items as milestones complete.

## Problem / decision
**Question (spec §6):** can we build a spatially transferable landslide susceptibility model and show where its
predictions are reliable?

**Who acts:** NCGS, Buncombe and Yancey planning offices, emergency management and NCDOT geotechnical staff.
**Decision:** which slope units to prioritise for site-specific geotechnical review before the next extreme-rainfall
event. [planned]

**Output wording:** relative susceptibility to *initiation* of rainfall-triggered shallow landslides, as a
percentile of hillslope area.
- It is not hazard and not risk.
- It is not a probability of a future landslide. Calibration is evaluated only as a diagnostic, and class-level
  frequencies are reported as "observed in Helene, in held-out watersheds". [planned]

## Study area and analytical unit
**AOI:** Buncombe + Yancey counties, NC (2,520 km²), plus a Watauga County temporal slice. [planned, pending owner
decision]

Reasons:
- the densest Helene initiation mapping: 1,815 and 1,156 natural High/Moderate-confidence source areas [verified]
- one mapping method inside the AOI [verified]
- pre-event lidar from 2017 [verified]

**Feasibility (2026-10-08) [verified]:**
- 32 HUC-12s in the AOI; positives are strongly clustered (top 10 HUC-12s hold 98 %).
- Rainfall strongly confounds positive density.
- Watauga 2024 labels come from a different mapping method.
- Consequences are in the decisions log and `PLAN.md` §0b.

**Unit of analysis:**
- a 5 m grid; the median natural source polygon is 84 m² [verified]
- **slope units**: hydrological half-basins on a 10 m DEM, at accumulation thresholds 0.05 / 0.1 / 0.2 km² [planned]

**Reporting unit:** the slope unit. [planned]

## Data and rationale
| Dataset | Why | Variable | Status |
|---|---|---|---|
| NCGS Landslide Inventory of NC | labels: initiation zones by phase, confidence, modifier, storm | positives / exclusions | fields and counts verified |
| USGS 3DEP 1 m (lidar 2017-02/04) | pre-event terrain | slope, curvature, relief, TPI, roughness, contributing area, aspect | metadata verified |
| NCGS Geologic Map of NC 1985 | weathering / residual soil | lithology group | service verified |
| SSURGO | colluvium thickness, infiltration | depth to restrictive layer, HSG, clay % | SDA reachable |
| NLCD 2021 land cover and tree canopy (MRLC WCS) | root reinforcement, disturbance | land-cover group, canopy % | planned |
| NOAA MRMS 72 h QPE | trigger: triggered domain + adjustment covariate | storm-total rainfall | archive verified |
| WBD HUC-12 / HUC-10 | spatial CV blocks | groups | reachable |
| NC footprints, NCDOT/TIGER roads | exposure only (after validation) | counts, km | licence open |

Excluded predictors [planned]:
- **elevation:** encodes Helene's rainfall footprint
- **distance to road:** encodes road failures and mapping access
- **PRISM normals:** weak gradient, collinear with elevation

Full provenance: [`DATA_SOURCES.md`](DATA_SOURCES.md).

## Harmonization
**Implemented in M3, 2026-10-09.**

**Grid:** every layer is on the 5 m DEM grid (EPSG:26917, NAVD88 m), asserted by tests.

**Inputs:**
- NLCD 2021: nearest, grouped into forest / developed open / developed / open-agricultural / wetland /
  water.
- Tree canopy 2021: bilinear. Its 254 flag is nodata; 0 % stays valid.
- MRMS: the cell-wise maximum of the two 72 h windows, bilinear from ~1 km.
- Geology (NCGS 1985, 1:500 k): rasterized by cell centre into 4 lithology groups. Inside the AOI every unit is
  grouped: metasedimentary/metavolcanic 53 %, basement orthogneiss 28 %, granitoid 8 %, mafic/ultramafic 2 % of
  the grid; the rest is Tennessee buffer.
- SSURGO (`muaggatt`): hydrologic soil group (dual groups → D) and minimum depth to bedrock. A null depth is
  coded as 250 cm plus a `bedrock_recorded = 0` flag, because SSURGO null means "no bedrock within the described
  profile", not missing data. Clay % was not harvested, because HSG carries the infiltration rationale.

**Hydrology** (10 m = exact 2×2 mean of the 5 m DEM; pysheds fill pits → depressions → flats → D8 → accumulation):
- log10 contributing area
- HAND on the conditioned DEM
- straight-line distance to the drainage cell, with channels at 0.1 km²
- Values are repeated 2×2 onto the 5 m grid. Inside the counties 0.07 % of cells reach no channel.
- Contributing area of large rivers entering from outside the 2 km buffer is truncated; this affects valley
  floors, not hillslopes.

**Domain** (Buncombe + Yancey, MRMS ≥ 250 mm, every predictor valid, no open water):
- 1793 km² (71,700,466 cells).
- Hillslope domain: slope ≥ 20.9° (1st percentile of positive cells),
  730 km².

**Time:** all predictors are pre-event (lidar 2016–17, NLCD and canopy 2021, footprints 2022/23); rainfall is the
event trigger.

## Baseline
**Implemented in M4, 2026-10-09** (`src/landslide/baseline.py`; full results in
[`validation/M4_BASELINE.md`](validation/M4_BASELINE.md), numbers from `validation/m4_baseline.json`).

**Model:** L2 logistic regression (C = 1). Inside each training fold: standardize, then select predictors by
forward VIF (≤ 10) in a fixed physical priority order, slope first. Rainfall (MRMS 72 h) and, for units, log unit
area are adjustment covariates that are always kept.
- **Score** = the linear predictor with rainfall set to the triggered-domain median (334 mm) and unit area to the
  median (0.066 km²): terrain ranked under equal trigger. It is a rank, not a probability.
- **Slope units** (A = 0.1 km², 22,569 units): every unit is used, so there is no negative sampling. Label = ≥ 1
  primary source area.
- **5 m hillslope cells:** all positive cells; per fold, 10 negatives per positive from the M3 pool.

**Result (leave-one-HUC-12-out, 500 m buffer; point, 95 % HUC-12 block bootstrap):**

| | Rainfall-stratified AUC | Within-watershed AUC | Capture, top 10 % of area |
|---|---|---|---|
| Units, LR | 0.767 (0.704–0.814) | 0.744 (0.680–0.814) | 37 % (27–51 %) |
| Units, slope p90 alone | 0.767 (0.707–0.842) | 0.755 (0.704–0.824) | 39 % (27–55 %) |
| 5 m cells, LR | 0.867 (0.846–0.891) | 0.868 (0.852–0.897) | 61 % |
| 5 m cells, slope alone | 0.806 (0.772–0.844) | 0.814 (0.786–0.842) | – |

- **Gates (fixed before the first fit):** G1 and G2 pass. The 9 replicate watersheds have within-watershed AUC
  0.63–0.85.
- **At unit level the LR does not beat slope p90 alone** (Δ 0.000, CI −0.042 to +0.034). At 5 m it does
  (Δ +0.061, CI +0.029 to +0.088).
  → M5 must beat **slope alone**, not only the LR. Aggregating the 5 m score to units is a candidate for the
  unit product.
- **Rainfall adjustment changes the ranking little:** rain-adjusted minus terrain-only LR is +0.003 (CI includes
  0). The pooled AUC (0.831) exceeds the stratified one (0.767) because of the between-rainfall contrast.
- **Lowest within-watershed AUC is the wettest replicate** (Headwaters Broad River, 544 mm, AUC 0.63). Terrain
  discriminates less where the trigger was extreme. [interpretation, untested]

## Advanced method
**Run in M5, 2026-10-09** (`src/landslide/advanced.py`; results in
[`validation/M5_ADVANCED.md`](validation/M5_ADVANCED.md)).

**Setup:**
- HistGradientBoosting (learning rate 0.05, L2 1). Leaves, minimum leaf size and iterations are tuned per outer
  fold by inner CV grouped by HUC-12, scored by rainfall-stratified AUC.
- Native categoricals at 5 m.
- 5 m scores are aggregated to units as a per-area intensity. Every hillslope cell is scored by the fold model
  that did not see its watershed, which also produces out-of-fold 5 m score rasters.

**Outcome:**

| Candidate (units) | Δ vs slope p90, stratified AUC | Δ vs slope p90, within watershed |
|---|---|---|
| (a) unit LR | −0.000 (−0.042 to +0.034) | −0.011 (−0.026 to +0.004) |
| (b) unit GBM | −0.008 (−0.049 to +0.020) | +0.000 (−0.013 to +0.016) |
| (c) 5 m LR → units | +0.029 (−0.016 to +0.059) | +0.017 (+0.006 to +0.034) |
| (d) 5 m GBM → units | +0.022 (−0.005 to +0.039) | +0.026 (+0.019 to +0.034) |

- **C1 fails at both units:** GBM − LR is −0.008 (−0.032 to +0.026) on units and +0.008 (−0.003 to +0.021) on
  cells. Gradient boosting is **not detectably better** than logistic regression.
- **C2 fails for all candidates.**
  - (c) and (d) beat slope within watersheds: the intervals exclude 0, and (d) is better in 9 of 9 replicates.
  - They do not beat it on the primary rainfall-stratified metric (lower bounds < 0).
  - → **Stop rule applied:** no product chosen, M6 not started.
- **At 5 m** the model does beat slope: GBM +0.069 (+0.046 to +0.089), LR +0.061.
- **Importance:** slope dominates every model. At 5 m, relief / position / roughness, aspect and curvature add
  value; land cover, soil and geology add almost none.
- **Artefact audit (out-of-fold residuals, units):**
  - Units near roads have fewer *natural* positives than the terrain predicts (O/E 0.57–0.72 in the nearest
    quintile). This is expected from the target definition, since failures near roads are mostly coded
    road-related and excluded. It means the ranking is terrain susceptibility to *natural* initiation, not to all
    failures.
  - Residuals fall with mapped-feature density (O/E ≈ 0 in the lowest density quintiles). That variable contains
    the labels, so the association is partly circular. It shows that the model ranks high terrain where nothing at
    all was mapped (low trigger intensity or unmapped; cannot be separated).
  - Units near the county line have fewer positives than predicted (O/E 0.6). This is not explained yet.



## Sampling (implemented in M3)
**Positives (primary rule):**
- Helene source areas with no slope modifier **and** no runoff modifier, existence and location confidence
  High/Moderate.
- Count: **2,582 polygons → 16,421 cells** in the domain.
- 95 polygons contain no cell centre and burn the cell of their
  representative point.
- **Variants:** slope-modifier only (2,962 polygons, the feasibility rule), and all source areas including
  road-related ones.

**Exclusions (never negatives):**
- every mapped polygon of any event, phase or confidence (+30 m)
- TIGER ∪ OSM vehicle roads (+15 m)
- open water
- Together they cover 16.5 % of the domain; the road corridor alone is
  13.7 %.

**Negatives:** a seeded pool of 400,000 cells from 59,889,389 eligible cells (weight
149.7). Per-fold subsamples are drawn from it in M4.

**Slope units** (half-basins; `data/out/units_<A>.parquet`, units with ≥ 50 % domain):

| A (km²) | Units in model domain | Positive units | Share |
|---|---|---|---|
| 0.05 | 38,830 | 1,440 | 3.7 % |
| 0.1 | 22,569 | 1,238 | 5.5 % |
| 0.2 | 12,483 | 991 | 7.9 % |

2,565 of 2,582 sources lie in model-domain units at
A = 0.1 km². The others are in units that are mostly below the rainfall threshold.

**Natural/road coding audit** (`validation/modifier_conflicts.csv`):
- Primary positives: 2.3 % within 20 m of a road.
- Road / cut / fill source areas: 27.4 % within 20 m of a road,
  and 49.5 % more than 100 m away, even with OSM roads.
- 99.5 % of "Road Embankment" source areas carry
  "Road Runoff". The road-related class therefore mostly marks failures *triggered by road drainage downslope of
  the road*, so distance to a road cannot verify it.
- 90 primary positives within 20 m of a
  road or building are listed for human review.

**Training-data density:** Gaussian kernel (σ = 2 km) of all 21,209 mapped features in the
AOI grid, on a 100 m grid (`labels_aoi/density_100m.tif`).

## Validation
**M4 decision gates, fixed 2026-10-09 before the first model fit.** The baseline (slope units, A = 0.1 km²,
primary positive rule, leave-one-HUC-12-out with a 500 m buffer) shows *convincing spatial predictive value* only if:
- **G1:** the rainfall-stratified out-of-fold ROC-AUC is ≥ 0.70, and its 95 % HUC-12 block-bootstrap lower bound
  is ≥ 0.60;
- **G2:** the within-watershed out-of-fold AUC is > 0.60 in at least 7 of the 9 replicate HUC-12s (≥ 50
  positive units each).

If either gate fails, M5 (gradient boosting) does not start; the method is revised first. The random split, the
pooled AUC, the slope-only and rainfall-only scores are contrasts, not gates.

**M4 checks (2026-10-09):**
- **Fold sufficiency** ([`validation/folds_huc12.csv`](validation/folds_huc12.csv)): 35 HUC-12 folds.
  - 10 have ≥ 10 positive units and get a per-watershed score; 9 have ≥ 50 (replicates).
  - 25 are flagged (< 20 positive units), and 20 have none. Those are held out and pooled, but never scored alone.
  - Effective n for every interval ≈ 10 watersheds.
- **Spatial leakage:**
  - Residual correlation between units is ≤ 0.12 below 2 km and ≈ 0 beyond 8 km, so the HUC-12 blocks (median
    76 km²) exceed the correlation range.
  - Dropping the 500 m buffer raises the AUC by 0.014. Leave-one-HUC-10-out gives 0.756. A random 5-fold split
    gives 0.797 (units) and 0.882 (cells). The leakage inflation is modest, but real.
  - Held-out positive units lie at a median 2.4 km from the nearest positive in another watershed.
- **Negative-sample bias (5 m):**
  - Scoring against unrestricted domain cells (including the excluded zones near mapped features and roads)
    instead of the filtered pool changes the stratified AUC from 0.867 to 0.862.
  - Excluded cells rank only slightly higher than eligible ones (AUC 0.529).
  - At unit level there is no exclusion. The 1,000 units whose only Helene sources are road-related or
    otherwise non-primary are labelled 0; without them the AUC is 0.778.
- **Mapping effort:** out-of-fold observed / expected positive units is 0.86 in Yancey and 0.91 in Buncombe, so
  there is no county difference after conditioning on terrain and rainfall.
  - 20 HUC-12s, some at 340–450 mm, have almost no mapped Helene feature of any kind (e.g. Big Crabtree Creek,
    Bent Creek). Whether that is lower trigger *intensity* (not captured by 72 h totals) or unmapped terrain
    cannot be separated with these data. The within-watershed AUC is the metric that is immune to it.
- **Positive rule:**
  - The slope-only variant (incl. 380 runoff-modified natural slopes) gives practically the same ranking:
    Spearman of out-of-fold scores 0.997.
  - Scored on primary labels, the difference is +0.000 (CI −0.002 to +0.002); the cell model is 0.858 vs 0.867.
  - The rule choice does not change the susceptibility ranking.
- **Calibration (diagnostic only):** Brier skill 0.047 at actual rainfall. Weak, and not a basis for any
  probability statement.
- **Reference products:** none scored. ScienceBase (optional) was not obtained, and the NCGS debris-flow model is
  post-event. Slope-only and rainfall-only scores are the comparison rules.

**M5 criteria and product rule, fixed 2026-10-09 before the first M5 fit.**

Candidates (all out-of-fold, leave-one-HUC-12-out with the 500 m buffer, scored on the same slope units):
- (a) unit LR (M4)
- (b) unit gradient boosting
- (c) 5 m LR aggregated to units
- (d) 5 m gradient boosting aggregated to units

Aggregation: unit score = log of the mean over the unit's domain cells of exp(cell score), with cells below the
hillslope threshold contributing 0. It is a per-area intensity, so flat units rank low.

- **C1, advanced better than baseline:** Δ(GBM − LR) rainfall-stratified AUC, with the HUC-12 block-bootstrap
  95 % lower bound > 0, on the same unit (units: b − a; cells: GBM − LR).
- **C2, better than slope alone:** Δ(candidate − slope p90) rainfall-stratified AUC lower bound > 0 **and**
  Δ within-watershed AUC point estimate > 0.
- **Product rule:**
  - Among the candidates that pass C2, the unit product is the one with the highest within-watershed AUC.
  - If none passes C2, no model is chosen. The finding "terrain slope explains the ranking; the model's added
    value is not detectable" is reported, and work stops for an owner decision before M6.
  - Selecting among four candidates on the same out-of-fold results is mildly optimistic; this is stated with
    the result.

**Owner decision 2026-10-10 (after M5):**
- The product is the **5 m logistic regression** ranking.
- 5 m gradient boosting and slope alone stay as comparison models.
- Slope units (A = 0.1 km², aggregated 5 m score) are the summary layer.
- The M4/M5 validation split and criteria are unchanged.

**M6 design, fixed 2026-10-10 before any M6 computation.** Nothing here is tuned after seeing results, and none
of it changes the product.
1. **Prediction uncertainty:**
   - 30 refits of the 5 m LR, each on a HUC-12 block-bootstrap resample of the training data.
   - Per cell: the p10–p90 range of the area percentile across refits.
2. **Area of applicability** (Meyer & Pebesma 2021):
   - Dissimilarity index on the standardized predictors, weighted by |standardized coefficient| of the final LR.
   - Threshold = upper whisker (Q3 + 1.5 IQR) of the leave-one-HUC-12-out dissimilarity of training cells.
   - Mapped on a 50 m lattice.
3. **Sensitivity** (one at a time; LOHO 500 m; 5 m LR; reported as Δ vs primary, no gate):
   - negative ratio 1:5 and 1:20
   - positives from polygons ≥ 50 m² only
   - registration tolerance (score = 3×3 maximum for every evaluated cell)
   - domain ≥ 300 mm
   - terrain-only model
   - leave-one-county-out
   - distance decay (training cells removed within 0.5 / 2 / 5 / 10 km of the held-out watershed)
   - unit threshold A = 0.05 / 0.2 for the summary layer

   The conclusion "the 5 m model ranks better than slope alone" is restated for each variant, using the
   within-watershed point Δ.
4. **Trigger intensity check** (one check, no tuning):
   - Maximum 1 h and maximum 6 h MRMS rainfall (25 Sep 00Z – 28 Sep 12Z) vs the 72 h total. The triggered domain
     (72 h ≥ 250 mm) is unchanged.
   - **T1:** unit-level pooled AUC of the trigger alone; Δ(intensity − 72 h) block-bootstrap lower bound > 0.
   - **T2:** 5 m LR with the intensity covariate instead of the 72 h total; within-watershed Δ lower bound > 0.
   - "Meaningful benefit" = T1 **and** T2. The result is reported; adopting it is an owner decision.
5. **Watauga (indicative, never in the headline):**
   - **Test positives:** Helene outlines with SlopeModifier "None Apparent" or not assessed, existence + location
     High/Moderate, > 30 m from TIGER ∪ OSM roads. The initiation proxy is the top 20 % of each outline by
     elevation.
   - **(i) Transfer:** the final AOI model applied to Watauga.
   - **(ii) Temporal:** a 5 m LR trained on the 1940 outlines' initiation proxies, with predictors smoothed to
     15 m (3 × 3 mean). Recurrence baseline = distance to the nearest 1940 outline.
   - **Reported:** AUC vs eligible domain cells, with intervals from a bootstrap over outlines (clusters).

Results: §Uncertainty and sensitivity and [`validation/M6_UNCERTAINTY_TRANSFER.md`](validation/M6_UNCERTAINTY_TRANSFER.md).
- **Primary:** leave-one-HUC-12-out inside the triggered domain (500 m buffer), rainfall-stratified metrics, per-watershed replicates; plus leave-one-county-out, HUC-10 grouping and distance decay.
- **Temporal:** Watauga 1940 → Helene 2024.
- **Strata and contrast:** rainfall-stratified evaluation; random split as a contrast only.
- **Metrics:** ROC/PR-AUC, Brier, reliability, confusion at top 5/10/20 %, capture curves, spatial error map.
- **Intervals:** block-bootstrap CIs for metrics and for Δ(advanced − baseline).
- **Comparison, not validation:** USGS slope-relief susceptibility and the NCGS channelized debris-flow model.

## Uncertainty and sensitivity
**M6, 2026-10-10** (5 m LR; numbers from `validation/m6_*.json`; full tables in
[`validation/M6_UNCERTAINTY_TRANSFER.md`](validation/M6_UNCERTAINTY_TRANSFER.md)).

- **Robust within the study area.** Negative ratio 1:5/1:20, positives ≥ 50 m² only, a 3×3 registration
  tolerance, domain ≥ 300 mm and dropping the rainfall covariate change the AUC by ≤ 0.012. The model stays
  better than slope alone in every variant (+0.05 within watersheds). The summary layer beats slope p90 at
  A = 0.05/0.1/0.2 by +0.01–0.03.
- **Not transferable beyond ~5–10 km.**
  - Leave-one-county-out: rainfall-stratified AUC 0.676, below slope alone. Training on Buncombe and testing on
    Yancey gives a within-watershed AUC of 0.85; the reverse gives 0.69.
  - Distance decay: removing training cells within 2 or 5 km of the held-out watershed costs ≤ 0.02, within
    10 km 0.18.
  - **Watauga** (indicative): the transferred AOI model reaches AUC 0.50 (0.44–0.56), slope alone 0.55. A model
    trained on Watauga's 1940 outlines reaches 0.79, and distance to the 1940 outlines 0.58.
- **Cause found (post-hoc diagnosis, no model changed):** the geology terms.
  - AOI natural initiations occur only in geology groups 1 and 3.
  - Groups 2 and 4 are the least-rained rock types (hillslope median 268 mm vs 350 and 535 mm).
  - The geology coefficients therefore largely encode the rainfall gradient.
  - Without them, the Watauga transfer AUC is 0.70.
  - This confounds the product ranking across geology boundaries, and the within-AOI validation cannot detect it.
- **Prediction uncertainty** (30 HUC-12 bootstrap refits):
  - 58 % of the final top-10 % cells stay in the top 10 % in ≥ 90 % of refits.
  - 7 % fall below the top 20 % in their worst decile.
- **Area of applicability:** 4.5 % of the hillslope lattice lies outside it. It covers predictor space only;
  the transfer tests show that this is not sufficient.
- **Trigger intensity check:**
  - The maximum 6 h rainfall explains *where* initiations happened better than the 72 h total (T1: unit AUC
    0.806 vs 0.742, Δ +0.065, CI +0.012 to +0.156).
  - It does not change the terrain ranking (T2: Δ −0.0006).
  - → No "meaningful benefit" by the pre-registered rule. It is relevant to the open question of watersheds with
    heavy rain but almost no mapped failures.

### Test: 5 m LR without geology predictors (owner approval 2026-10-10; fixed before computation)
**Question:** does removing the geology terms (which M6 showed to encode the rainfall gradient) make the model
transferable without losing skill inside the AOI?

**Models compared:**
- *current* = 5 m LR as in M4–M6.
- *no-geology* = identical, except that the one-hot geology columns are removed.

Same predictors otherwise, same forward VIF order, rainfall covariate at the reference, same 1:10 thinning
seeds, same folds and buffer, same metrics. Every comparison is paired, using the same bootstrap resamples.

**Decision rule.** No-geology replaces current **only if R1 and R2 both hold**; otherwise the current model is
kept as a local experiment and the transfer problem is reported as unresolved.
- **R1, AOI non-inferiority** (leave-one-HUC-12-out, 500 m buffer, 5 m hillslope cells): Δ(no-geology − current)
  with a HUC-12 block-bootstrap 95 % **lower bound ≥ −0.01**, for both the rainfall-stratified AUC and the
  within-watershed AUC.
- **R2, meaningful transfer improvement, both of:**
  - (a) leave-one-county-out: Δ rainfall-stratified AUC with a HUC-12 block-bootstrap lower bound > 0;
  - (b) Watauga transfer of the final AOI model: Δ AUC with a lower bound > 0 (bootstrap over test outlines as
    clusters and negative cells, as in M6).

**Reported without a gate:**
- each model vs slope alone (AOI, leave-one-county-out, Watauga)
- the Watauga 1940-trained model with and without geology
- ranking differences: Spearman between final scores, overlap of the top-10 % sets, top-10 % share by geology
  group, on the hillslope part of the uniform domain sample
- stability: share of the top-10 % sample cells that stay in the top 10 % in ≥ 90 % of 30 HUC-12 bootstrap
  refits, for both models, computed the same way

**Known limits, stated before the result:**
- The no-geology idea came from the M6 Watauga diagnosis, so Watauga is not an independent test of it.
  Leave-one-county-out is the cleaner test, which is why both are required.
- The Watauga test positives are Nearmap-imagery outlines (a different mapping method).
- The 1940 outlines are almost all location confidence "Low", which affects only the descriptive temporal model.
- With about 10 informative watersheds, intervals are wide; a null result is likely and acceptable.

**Result (2026-10-10; [`validation/NOGEO_TEST.md`](validation/NOGEO_TEST.md)): no replacement. The current
model stays as a local experiment, and the transfer problem is not resolved.**
- **R1 fails.** In the AOI the no-geology model loses on the rainfall-stratified AUC: −0.012 (CI −0.023 to
  +0.004). It is equal within watersheds: +0.000 (−0.012 to +0.009).
- **R2a fails.** Leave-one-county-out: +0.119 (CI −0.020 to +0.214). Without geology the model is about equal to
  slope alone there (−0.011, CI −0.056 to +0.042); the current model is worse than slope (point −0.130).
- **R2b passes.** Watauga: +0.179 (CI +0.133 to +0.214), and +0.132 over slope. It is not independent of the
  hypothesis.
- **Ranking:**
  - Spearman 0.85; 86 % of the current top 10 % is also in the no-geology top 10 %.
  - The current top 10 % over-represents geology group 3 (20 % vs 7 % of hillslopes) and contains no group-2
    cells (6 % of hillslopes). Without geology the shares match the area (8 % and 6 %).
- **Stability:** without geology, 2.3 % instead of 6.3 % of top-10 % cells fall below the top 20 % in their worst
  refits.

## Decision metric
Held-out capture of mapped Helene initiation sites in the top *k* % of hillslope area (*k* = 5/10/20 % scenarios),
with uncertainty and out-of-domain flags per unit. [planned]

*Do not use it as* a hazard or runout map, a site-specific stability assessment, or a probability of future
failure.

## Rust component
**Status: implemented and benchmarked (M2, 2026-10-09).**

**Kernels** (`rust/src/lib.rs`, PyO3 module `terrain_kernels`):
- `terrain3x3`: a single 3×3 pass giving slope (Horn 1981), northness/eastness of the downslope direction,
  profile and plan curvature (second derivatives from the Zevenbergen & Thorne 1987 coefficients; profile > 0
  concave, plan > 0 convergent) and TRI (Riley et al. 1999).
- `window_stats`: square (2r+1)² windows giving mean and sd (sliding sums in f64 on mean-centred values) and
  min/max (van Herk / Gil-Werman, O(1) per cell).

**Why Rust:**
- One nodata-aware pass produces all outputs; SciPy needs separate filters plus a nodata-count filter.
- The predictors are recomputed for two regions (290 M cells) and for the sensitivity runs.
- I/O, mosaicking and reprojection stay in GDAL/rasterio.

**Reference (oracle):** `landslide.terrain_ref`: vectorised NumPy for the 3×3 pass, explicit loops and SciPy C
filters for the windows. The oracle is itself tested on analytic surfaces (plane, paraboloid, cone).

**Semantics:** strict. Nodata, NaN or a window crossing the grid edge gives nodata. A gradient ≤ 1e-9 is flat,
so aspect and curvature are 0 there.

**Tolerances** (outputs are float32, computed in f64, rounded once):
- min, max, relief: exact
- mean / TPI: rtol 1e-6
- sd: atol 1e-4
- 3×3 outputs: rtol 1e-6, atol 1e-6
- These replace the planned "rtol 1e-9", which float32 storage cannot meet.

**Bug found by the benchmark and fixed:**
- The first version used summed-area tables. On 4096²–8192² grids its sd drifted by up to 3.7e-3 m, because
  rounding grows with grid totals.
- An exact check on sampled windows showed SciPy within 1e-7 and Rust off.
- The window sums are now sliding sums, and a regression test checks sd to 1e-5 against an exact two-pass
  computation on a 3000² grid.

**Benchmark** (`make bench`, `benchmarks/terrain_kernels.json`):
- Hardware: Apple M4, 16.0 GB, single-threaded (both implementations); rustc 1.99.0 (b940084d7 2026-09-28); NumPy 2.5.3, SciPy 1.18.1.
- Input: centre crops of the real 5 m DEM.
- Harness: `timeit.repeat`, median.

| Kernel | Cells | Window | Agree | Reference median (s) | Rust median (s) | Speed-up |
|---|---|---|---|---|---|---|
| terrain3x3 | 1024² | 3x3 | yes | 0.035 | 0.0125 | 2.8× |
| window_stats | 1024² | 3x3 | yes | 0.0492 | 0.0201 | 2.45× |
| window_stats | 1024² | 11x11 | yes | 0.0532 | 0.0198 | 2.69× |
| window_stats | 1024² | 21x21 | yes | 0.0514 | 0.0189 | 2.72× |
| window_stats | 1024² | 101x101 | yes | 0.0524 | 0.0177 | 2.96× |
| terrain3x3 | 4096² | 3x3 | yes | 0.5828 | 0.5449 | 1.07× |
| window_stats | 4096² | 3x3 | yes | 1.1584 | 0.4443 | 2.61× |
| window_stats | 4096² | 11x11 | yes | 1.1407 | 0.451 | 2.53× |
| window_stats | 4096² | 21x21 | yes | 1.1453 | 0.4469 | 2.56× |
| window_stats | 4096² | 101x101 | yes | 1.1583 | 0.4646 | 2.49× |
| terrain3x3 | 8192² | 3x3 | yes | 2.4408 | 0.8445 | 2.89× |
| window_stats | 8192² | 3x3 | yes | 5.4824 | 1.7218 | 3.18× |
| window_stats | 8192² | 11x11 | yes | 5.9472 | 1.8538 | 3.21× |
| window_stats | 8192² | 21x21 | yes | 6.3929 | 1.8003 | 3.55× |
| window_stats | 8192² | 101x101 | yes | 6.2342 | 2.0351 | 3.06× |

**Production run:**
- 132 kernel calls (derived in `terrain.run_region`) take 42 s of kernel time within 403 s of
  wall time for both regions. The rest is compressed GeoTIFF I/O.
- Peak RSS is 3.8 GB with 4096² tiles and a 54-cell halo.

**Honest reading:**
- Rust is 2.5–3.5× faster than SciPy's C filters for window statistics and ~1.1–2.9× for the 3×3 pass.
- Kernel time is ~10 % of a full predictor run, so the whole-run saving is about a minute.
- The value of the Rust kernels is the single strict-nodata pass with explicit, tested semantics rather than
  raw speed.
- No parallelism yet (not needed).

## Story sites and hand-check sample (M7, simplified; owner 2026-10-24)
Exposure was skipped by the owner. M7 produces display and review material only; none of it enters a model or a metric.
Both samples are drawn by fixed rules (`src/landslide/m7.py`, seeded) and frozen in `validation/`.
- **Story sites** (`validation/story_sites.json`): 2 km × 2 km squares on the UTM lattice (multiples of 2,000 m).
  - S1 / S2: most mapped primary initiation sites in Buncombe / Yancey (square ≥ 50 % in the domain).
  - S3, "ranked high, no mapped initiation": no mapped site, ≥ 80 % in the domain, mean 72 h rainfall ≥ 350 mm,
    largest share of top-10 % (final model) hillslope cells.
  - S4, "missed": most mapped sites whose held-out rank is outside the top 30 %.
  - Each site shows before/after orthoimagery, the top-10 % cells and the mapped sites (with held-out ranks). The sites
    are chosen to illustrate cases, so they say nothing about typical performance.
- **Hand-check sample** (`validation/hand_check_sample.csv`): 40 seeded locations: 15 held-out hits (mapped, top 10 %),
  15 top-10 % cells without a mapped initiation, 10 misses (mapped, outside the top 30 %). Columns for an AI-assisted
  and a human assessment are empty and every row is "not reviewed". Any AI-assisted pass must be labelled "AI-assisted,
  pending human review"; until a person reviews it, the sample supports no claim.
- **Why the second group matters:** a flagged slope with no mapped failure is not a false positive (mapped absence
  is not true absence; Helene did not test every slope). The review is meant to tell mapping gaps from real
  non-failures, using the Helene 2025 imagery.

## Limitations and omitted processes
Known before analysis:
- **One trigger event:** transfer to other storms is tested only in Watauga, with small n. [verified as a data limit]
- **Not modelled:** runout, deep-seated landslides, road-cut failures. Road-related source areas are > 50 % of
  Helene source areas and are excluded from the primary target. [verified]
- **Detection bias:** small, shallow and under-canopy failures are likely under-mapped. [assumption]
- **Mapped absence is not true absence**; county-wide inspection is assumed. [assumption]
- **Terrain after 2017** (new cuts and grading) is not represented.

## Decisions log
| Date | Decision | Alternatives considered | Reason |
|---|---|---|---|
| 2026-10-08 | Inventory = NCGS Landslide Inventory of NC (Helene source areas) | USGS US inventory v3; WA DNR; DOGAMI SLIDO | only candidate with pre-event lidar (2017), phase-separated polygons, confidence and modifier fields; WA/OR inventories are mapped on the predictor lidar |
| 2026-10-08 | AOI proposal: Buncombe + Yancey + Watauga temporal slice | +McDowell/Henderson; Yancey only | densest natural initiation mapping, uniform method; Watauga is the only area with two dated events on the same terrain |
| 2026-10-08 | Primary target = natural source areas (`None Apparent`), road-related as contrast | all source areas | road failures are a different process; including them makes road proximity a dominant artefact |
| 2026-10-08 | 5 m grid, slope units as reporting unit | 1–2 m; 10 m | median source polygon 84 m²; volume and micro-relief at 1–2 m; misregistration tolerance |
| 2026-10-08 | Elevation and distance-to-road excluded as predictors | include | trigger-footprint and mapping-access proxies |
| 2026-10-08 | No probabilities in the app; ranks + event-specific observed frequencies | calibrated probability map | single event, mapped-only labels; a probability would overstate the evidence |
| 2026-10-08 | Out-of-fold ranks for all validation views and slider metrics | final-model ranks everywhere | honest hit/miss display |
| 2026-10-08 | High-ranked units without mapped initiation are not called false positives | standard confusion terms in UI | mapped absence ≠ true absence; Helene did not test all slopes |
| 2026-10-08 | Slope units by half-basins with pysheds | GRASS r.slopeunits | no GRASS install; half-basins are the classical basis |
| 2026-10-08 | Before/after imagery only at curated sites | full-AOI swipe; hotlinked services | hundreds of GB; D10 self-contained cartography |
| 2026-10-08 | Owner: AOI Buncombe + Yancey; Watauga separate temporal test | +McDowell/Henderson | owner decision |
| 2026-10-08 | Triggered domain: MRMS 72 h ≥ 250 mm (200/300 sensitivity) | whole AOI | feasibility: < 250 mm covers 717 km² with 0.7 % of positives; absence there reflects no trigger |
| 2026-10-08 | Rainfall as adjustment covariate; product predicted at fixed reference rainfall; rainfall-stratified primary metrics | rainfall only for stratification (rev. 2) | positive density rises ~100× from < 250 to > 400 mm (ρ = 0.56 across HUC-12) |
| 2026-10-08 | Leave-one-HUC-12-out + per-watershed replicates (10 HUC-12 with ≥ 50 positives) | 5 balanced HUC-12 folds | top 2 HUC-12 hold 46 % of positives, 16 of 32 have none |
| 2026-10-08 | Watauga test indicative only: outlines natural/unassessed > 30 m from roads, smoothed predictors, recurrence baseline | primary temporal holdout | Watauga 2024 mapped on Nearmap imagery (different method), only 26 confirmed natural; 2017 terrain post-dates 1940 by 77 years |
| 2026-10-08 | NLCD 2021 land cover + canopy 2021 via MRLC WCS | Annual NLCD 2023 | 2023 not offered per year in WCS; consistent pre-event vintage |
| 2026-10-09 | DEM mosaic priority NC Phase 5 (2017) > NC Phase 4 (2016–17) > TN (2016) | alphabetical / first found | the AOI and Watauga use the same collection wherever it exists; cross-project overlaps have no vertical offset (|median| ≤ 0.09 m) |
| 2026-10-09 | Building footprints harvested for the buffered AOI only, local use | whole harvest bbox (430 k) | exposure is computed for the AOI only; licence unresolved |
| 2026-10-09 | NCGS channelized debris-flow model not treated as a pre-event reference | use as reference comparison | published 2025-04-28 (post-Helene), query disabled |
| 2026-10-09 | Window sums by sliding sums, not summed-area tables | summed-area tables | SAT sd drifted 3.7e-3 m on 8192² grids (found by benchmark agreement check); sliding sums accurate to 1e-5 |
| 2026-10-09 | Tolerances set for float32 outputs (exact / rtol 1e-6 / atol 1e-4) | rtol 1e-9 (plan) | float32 storage cannot meet 1e-9; both sides compute in f64 and round once |
| 2026-10-09 | Benchmark reference for the 3×3 pass runs in 1024-row bands | unchunked NumPy | unchunked needs ~16 GB at 8192² and swaps (12× slower), which would fake a speed-up |
| 2026-10-09 | Primary positives also require no runoff modifier (2,962 → 2,582) | slope modifier only | 99.5 % of "Road Embankment" sources carry "Road Runoff", i.e. road drainage is an anthropogenic trigger even on unmodified slopes; slope-only kept as variant |
| 2026-10-09 | Road corridor from TIGER ∪ OSM (ODbL, local only) | TIGER only | TIGER lacks private drives and service/forest roads (46,584 OSM `service` segments in the AOI) |
| 2026-10-09 | Modifier audit flags only primary positives near roads/buildings | flag road-coded far from roads | road-runoff failures start downslope of the road; distance is not diagnostic |
| 2026-10-09 | Hillslope domain = slope threshold only (20.9°); developed land split in reporting, not excluded | also exclude NLCD 24 | NLCD groups 22–24 together; the population split is done in reporting (forest vs developed) |
| 2026-10-09 | Lithology: 4 groups from NCGS 1985 unit descriptions | unit-level categories | 1:500 k units, many rare; groups follow weathering behaviour; all groups ≥ 2 % of the AOI |
| 2026-10-09 | SSURGO null bedrock depth = 250 cm + flag; clay not used | treat null as missing | null means no bedrock in the described profile; HSG covers infiltration |
| 2026-10-09 | pysheds 0.5 with an `np.in1d` shim (NumPy 2.5) | pin NumPy < 2.4; own D8 code | one-line documented shim; mature routing kept |
| 2026-10-09 | Unit labels from representative points of in-county positives; units kept if ≥ 50 % in the triggered domain | any positive cell | one source = one unit; low-rain units are not tested by Helene |
| 2026-10-09 | M4 gates G1/G2 fixed before the first fit (stratified AUC ≥ 0.70 with lower bound ≥ 0.60; within-watershed AUC > 0.60 in ≥ 7 of 9 replicates) | judge after seeing results | prevents moving the bar |
| 2026-10-09 | Rainfall-stratified (50 mm bins) and within-watershed AUC as primary; pooled AUC as contrast | pooled AUC | pooled AUC rewards the rainfall footprint (rainfall alone: pooled 0.74, stratified 0.54) |
| 2026-10-09 | Unit model includes log unit area as covariate; scored at median area; capture over unit domain area | rank by P(unit has a source) | larger units contain sources more often; the decision metric is per area |
| 2026-10-09 | Predictor selection by forward VIF in a fixed physical priority order (slope first) | greedy backward VIF (drop the largest) | **changed after the first M4 run:** backward pruning dropped slope p90 and mean (VIF 85/57) and kept roughness/relief proxies. First run: stratified AUC 0.744, LR − slope −0.023 (CI −0.091 to +0.022), gates also passed. Disclosed here because it was decided after seeing results |
| 2026-10-09 | M5 must beat slope p90 alone, not only the LR | compare only with the LR | the unit LR equals slope p90 (Δ 0.000) |
| 2026-10-09 | No external reference product scored in M4 | wait for ScienceBase | optional per owner; NCGS debris-flow model is post-event |
| 2026-10-09 | M5 criteria C1/C2 and the product rule fixed before the first M5 fit; 5 m scores aggregated to units as a per-area intensity | choose after seeing results | prevents choosing the bar after the fact |
| 2026-10-09 | **M5 stop rule applied:** no candidate passes C2; GBM not detectably better than LR | relax C2 after seeing that (d) beats slope within watersheds | the rule was fixed in advance; changing the product definition is an owner decision |
| 2026-10-10 | Owner: product = 5 m LR; GBM and slope alone as comparisons; slope units as summary layer | unit model; stop | M5: 5 m model beats slope, unit models do not |
| 2026-10-10 | M6 design (sensitivity list, ensemble, AOA, trigger check T1/T2, Watauga tests) fixed before computation | decide after results | pre-registration |
| 2026-10-10 | Watauga roads from a separate OSM extract of the same snapshot (sha checked) | re-extract the AOI file | keeps the AOI road corridor reproducible |
| 2026-10-10 | Geology confound reported, not fixed | drop geology terms now | found post hoc; changing the product model is an owner decision; a pre-registered re-test is proposed |
| 2026-10-10 | VIF selection skips constant columns | crash | a class absent from a subdomain (geology 2 above 300 mm) gave an undefined correlation |
| 2026-10-10 | No-geology test and decision rule (R1 non-inferiority ≥ −0.01 lower bound; R2 leave-one-county-out and Watauga lower bounds > 0) fixed before computation | judge on point estimates | owner instruction: intervals, not points |
| 2026-10-10 | No-geology test: rule not met (R1, R2a fail; R2b passes) → current model kept as a local experiment; geology distortion of the ranking documented | replace on the Watauga gain or the point estimates | pre-registered rule; Watauga not independent |
