# Test: 5 m logistic regression without geology predictors

Generated from `validation/nogeo_test.json`. Design and decision rule fixed before computation (METHOD §Validation, commit 0ae693d). Paired comparisons on the same bootstrap resamples; 95 % intervals. Scores are relative ranks, not probabilities.

## Decision

- R1 AOI non-inferiority (both lower bounds ≥ −0.01): **fail**
- R2a leave-one-county-out improvement (lower bound > 0): **fail**
- R2b Watauga transfer improvement (lower bound > 0): **pass**
- **Replace the current model: no**

## Results

### Inside the AOI (leave-one-HUC-12-out, 500 m buffer)

| Model | AUC rainfall-stratified | AUC within watershed |
|---|---|---|
| Current (with geology) | 0.867 (0.846–0.891) | 0.868 (0.852–0.897) |
| Without geology | 0.854 (0.833–0.882) | 0.869 (0.852–0.892) |
| Slope alone | 0.806 (0.772–0.844) | 0.814 (0.786–0.842) |

- Without − current: stratified -0.012 (-0.023 to +0.004); within +0.000 (-0.012 to +0.009)
- current − slope: stratified +0.061 (+0.029 to +0.088); within +0.054 (+0.042 to +0.076)
- no geology − slope: stratified +0.048 (+0.023 to +0.073); within +0.055 (+0.037 to +0.075)

### Leave-one-county-out

| Model | AUC rainfall-stratified | AUC within watershed |
|---|---|---|
| Current (with geology) | 0.676 (0.584–0.839) | 0.762 (0.651–0.867) |
| Without geology | 0.795 (0.762–0.838) | 0.830 (0.794–0.864) |
| Slope alone | 0.806 (0.772–0.844) | 0.814 (0.786–0.842) |

- Without − current: stratified +0.119 (-0.020 to +0.214); within +0.068 (-0.005 to +0.147)
- current − slope: stratified -0.130 (-0.205 to +0.023); within -0.051 (-0.163 to +0.047)
- no geology − slope: stratified -0.011 (-0.056 to +0.042); within +0.016 (-0.022 to +0.044)

### Watauga County (indicative)

129 test outlines, 1,066 proxy cells; bootstrap over outlines and negative cells. Test labels come from Nearmap imagery (a different method). The 1940 outlines are almost all location confidence "Low" and affect only the temporal model.

| Score | AUC | AUC rainfall-stratified |
|---|---|---|
| AOI model with geology, transferred | 0.500 (0.442–0.556) | 0.548 |
| AOI model without geology, transferred | 0.679 (0.610–0.733) | 0.677 |
| Slope alone | 0.547 (0.499–0.595) | 0.541 |
| 1940-trained, with geology (descriptive) | 0.787 (0.728–0.835) | 0.792 |
| 1940-trained, without geology (descriptive) | 0.803 (0.753–0.845) | 0.804 |

- Without − with geology (transfer): +0.179 (+0.133 to +0.214)
- Without geology − slope (transfer): +0.132 (+0.071 to +0.183)

### Ranking and stability (hillslope part of the uniform domain sample)

- Spearman between the final scores: 0.848; share of the current top-10 % that stays in the no-geology top-10 %: 85.8 %.
- Top-10 % share by geology group (hillslope share in brackets): group 1: current 80.1 %, no-geology 85.2 % (86.3 %); group 2: current 0.0 %, no-geology 6.2 % (6.0 %); group 3: current 19.9 %, no-geology 8.2 % (6.9 %); group 4: current 0.0 %, no-geology 0.3 % (0.8 %).
- Stability (30 HUC-12 bootstrap refits; top-10 % cells staying in the top 10 % in ≥ 90 % of refits / falling below the top 20 %): current 59.6 % / 6.3 %; no geology 61.5 % / 2.3 %.
