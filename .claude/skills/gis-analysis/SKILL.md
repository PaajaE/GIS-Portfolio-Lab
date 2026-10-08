---
name: gis-analysis
description: Methodological checklist for designing, changing or reviewing a GIS analysis (data choice, analytical unit, CRS/resolution harmonization, sampling, baseline, validation, uncertainty, decision metric), and for starting a project's METHOD.md and DATA_SOURCES.md. Use before writing or changing analysis code.
---

# GIS analysis design

Goal: every result can be defended by answering the spec's guiding question:
*What are we measuring, why does this variable or method make sense, and how do we know the result is trustworthy?*

## How to use
1. Read the project's spec section (§5–11 of `docs/GIS_Portfolio_Lab_v5.md`) and its `METHOD.md` / `DATA_SOURCES.md` if they exist. Don't restate the spec; build on it.
2. Go through only the stages the task touches. For each, answer the questions and record the decisions in `METHOD.md` (decisions log).
3. If a question can't be answered yet, write it down as an open item. Don't paper over it.
4. Starting a project: copy `METHOD_TEMPLATE.md` and `DATA_SOURCES_TEMPLATE.md` (next to this file) into the project directory, then fill in what is known.

## Stages, questions and failure modes

**Problem / decision.** Who acts on the result and what do they decide? Which metric answers that? Watch for a question the data can't answer, or a metric that doesn't match the question.

**Data.** Why is each dataset needed, and which variable does it supply? What is its vintage, license, coverage and known bias? Don't add variables just because they're available. Watch for licenses with share-alike or attribution obligations on derived outputs.

**Analytical unit.** What is the unit of analysis versus the reporting unit (pixel, slope unit, parcel, block, segment)? Does aggregation hide internal structure (MAUP)? Are centroids standing in for areas?

**Harmonization.**
- CRS: a projected CRS suitable for distances and areas in the AOI. Is any computation still in geographic degrees? Are linear units consistent (m vs ft, including vertical units of DEMs)?
- Resolution: justified by the process and the input data, not the finest available. Is the resampling method right for the data type (nearest for categorical; bilinear/cubic or averaging for continuous)?
- Alignment: rasters share grid origin, cell size and extent. Do vector/raster overlays have explicit edge semantics (cell center vs touched)?
- Nodata: declared, propagated, never silently treated as zero. Does any edge/border effect come from a neighborhood kernel?
- Geometry: valid, consistent winding, no unintended duplicates or slivers after overlay.
- Time: are predictors temporally appropriate? Is any post-event data used as pre-event evidence?

**Baseline.** A transparent method (threshold rule, logistic regression, simple distance/cost model) that the advanced method must beat. Without one, "better" is meaningless.

**Advanced method.** What does it add, which assumptions does it make, and are they plausible here? For ML: predictor rationale, collinearity, class imbalance, sampling of positives and negatives (absence of mapping is not true absence).

**Validation.**
- Independence: spatial/block or region holdout for spatially autocorrelated data. Use a temporal holdout when dates allow. Never tune and evaluate on the same events or areas.
- Leakage: neighboring pixels across folds, preprocessing fitted on all data, target-derived features.
- Metrics suited to the claim: discrimination (ROC/PR-AUC), calibration (Brier, reliability) when probabilities are claimed, and geometric agreement (IoU, boundary distance) for extents.
- Reference products: state what they represent. Agreement with a different construct is comparison, not validation.
- Show where the model is wrong (error maps), not only aggregate scores.

**Uncertainty / sensitivity.** Treat thresholds and parameters as scenarios with stated ranges and reasons. Report whether conclusions change. Separate prediction uncertainty, training-data density and out-of-domain areas when relevant. Use probabilistic language only with a justified probabilistic model.

**Decision metric and interpretation.** The output a user acts on, with units and the stated assumptions it depends on. Check the wording guardrails in `CLAUDE.md`.

**Presentation.** Hand off to the `web-ux` skill. Show uncertainty and limitations alongside results, not hidden behind them.

## Testing proportional to risk
Small deterministic fixtures with hand-computable answers for each non-trivial transformation. Assertions on CRS, extent, units, value ranges, nulls and nodata at stage boundaries. Seeds for anything stochastic. Test more heavily where an error would change a conclusion.
