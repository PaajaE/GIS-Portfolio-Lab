# FirePath — the approach checked against established practice

> 2026-10-09. Written after the owner asked whether M1a/M1a-2 follow field standards rather than ad-hoc
> experiments. Sources were reached by web search; most primary PDFs are blocked from this session, so
> statements are marked **[sourced: abstract/excerpt]** where the full text was not read. No experiment was
> run for this document.

## 1. Short answer

There is no single "standard test suite" for fire-spread models. There **is** an established practice,
built from three pieces:

1. **The generic verification-and-validation (V&V) framework** used for PDE-based simulation
   (Oberkampf & Roy, *Verification and Validation in Scientific Computing*):
   - **code verification:** does the code solve the equations as written? Tested with exact or
     manufactured solutions and the **observed order of accuracy**;
   - **solution verification:** how large is the numerical error in a given run? Estimated by
     **systematic grid refinement with the same scheme**, Richardson extrapolation and the Grid
     Convergence Index (GCI);
   - **validation:** does the model agree with observations, within stated uncertainty?

   Code verification and solution verification answer different questions and are kept separate
   [sourced: Roy's chapter abstract; NAFEMS summary].
2. **Fire-model verification cases used by the major codes.**
   - ELMFIRE publishes a verification suite: elliptical fire shape vs the exact ellipse, crown-fire
     ellipse, "Point" (no wind), "Windy", "Valley" (slopes) and "Fuel Quadrant" (four fuels)
     [sourced: elmfire.io excerpts].
   - Muñoz-Esparza et al. (2018, WRF-Fire) test rate-of-spread and area errors against analytic
     solutions with grid convergence. They report that common level-set implementations err by
     **10–35 %** at 12.5–100 m and **underestimate area**. WENO5 + RK3 **with reinitialization** brings
     the error below 1 %, nearly grid-independent [sourced: abstract/excerpt].
   - Bova, Mell & Hoffman (2016) compare a level set with FARSITE's marker method on cases of
     increasing terrain and fuel complexity. This is a code-to-code comparison [sourced: abstract].
3. **Fire-specific validation metrics.**
   - Sørensen/Dice, Jaccard, Kappa, and arrival-time and shape agreement (Filippi et al. 2014).
   - Area Difference Index, Shape Deviation Index, precision/recall (Duff et al. 2016). Secondary
     sources recommend ADI with over/under-prediction and F1 with precision/recall.
   - There are **no standard numeric pass thresholds**. Cruz & Alexander (2013) propose ±35 % (about one
     standard deviation) as a reasonable standard for predicted head ROS, and find under-prediction
     bias in 75 % of 49 evaluation datasets [sourced: abstract].

## 2. Where FirePath already follows practice

| Practice | FirePath status |
|---|---|
| Code verification against exact solutions | ✔ analytic fixtures: isotropic gauge (exact), focus-anchored ellipse, Minkowski-sum wind change, hand-computed heterogeneous strip, barrier geodesics, initial-perimeter distance. **More** than ELMFIRE's published cases on wind change and barriers |
| Independent oracle for the implementation | ✔ SciPy graph oracle and independent time-marching for the edge integral |
| Exact-ellipse shape test (ELMFIRE case 01, Muñoz-Esparza) | ✔ bake-off criteria 1–2, over wind angles |
| Pre-registration, held-out validation fires, model vs baseline | ✔ (stronger than typical practice) |
| Overlap + timing metrics for validation | ✔ Dice/IoU, growth-only Dice, boundary distances, interval-censored arrival error (in the spirit of Filippi's arrival-time agreement) |
| Rothermel/SB40 cross-checked against an independent implementation | partly (wind/slope equations; the fuel table is still open) |

## 3. Where FirePath deviates from practice (and what it cost)

| # | Gap | Evidence of cost | Correction |
|---|---|---|---|
| G1 | **The level set was judged before it matched the state of practice.** Our level set has no **reinitialization** (and no narrow band). Muñoz-Esparza et al. note that almost no wildfire level-set codes reinitialize, which they identify as a source of 10–35 % errors. | The flaws we attributed to "the level set" (O(Δx) delay at fuel contrasts, lateness behind gaps and around corners, the isotropic E1 anomaly) may be implementation defects, not limits of the method. **The D1 comparison was therefore not fair to option B.** | Implement the documented practice first: WENO5 + TVD-RK3 + periodic reinitialization (and a narrow band), as in WRF-Fire. Then re-verify. |
| G2 | **No observed order of accuracy.** Code verification normally shows the error falling at the scheme's design order under refinement. We used single-resolution tolerances. | We can't tell a converging scheme from a biased one. The graph's angular error is grid-independent (it does **not** converge), while a level set should converge. That difference is decision-relevant and was never measured as such. | For each scheme on 2–3 analytic cases: errors at Δ, Δ/2, Δ/4 → observed order. |
| G3 | **E1 used a cross-scheme "reference".** The mean or both of two different schemes' fine-grid solutions is a code-to-code comparison, not a reference solution. | The references disagreed (LB 4: median 2.8 %, p95 10.5 %; isotropic: 32 % median, which looks like a defect, §4). E1 could not separate the schemes. | Replace with **solution verification per scheme**: the same scheme on 3 grids (30/15/7.5 m), Richardson-extrapolated value and GCI. Cross-scheme agreement is reported only as a code-to-code comparison. Add a published reference for mosaics: Finney (2003) expected spread rates across random fuel landscapes (harmonic-mean / MTT construction; Fujioka 1985) [sourced: abstract], plus the ELMFIRE-style fuel quadrant. |
| G4 | **Graph (MTT-type) methods were tested under conditions they are not used for.** Finney's MTT (FlamMap) assumes constant weather per run; time-varying conditions are FARSITE's domain [sourced: MTT documentation, abstracts]. | E2 confirmed it: the radius-16 graph is 13.6 % off under a 90° wind turn, and long edges can't turn. A practitioner log reports that a 16-direction Dijkstra reaches only 64–77 % of the ellipse [sourced: GitHub PR, not peer reviewed], consistent with our 20–86 %. | Treat label-setting as verified for static fields and barriers, and as unsuitable as the sole scheme for hourly wind changes. |
| G5 | **Missing standard cases:** slope ("Valley"), four-fuel quadrant, merging fronts (two ignitions), expanding-circle order of accuracy. | — | Add them to the fixture set (slope after the slope-plane geometry exists). |
| G6 | **Acceptance thresholds were our own** (5 %/10 %, Dice ≥ 0.5, 12 h). | Fine as pre-registered judgements, but they were not tied to the literature. | Keep them, and label them as judgements. Add context: Muñoz-Esparza report < 1 % ROS error for a state-of-practice level set (verification); Cruz & Alexander's ±35 % is a *validation*-level ROS standard. Verification tolerances should be much tighter than validation error. |
| G7 | **Validation metric set** lacks the indices most often recommended. | — | Add ADI with over/under-prediction %, precision/recall/F1 and SDI next to Dice/arrival-time. Sørensen and Jaccard rank identically, so report one. |

## 4. Defects found during M1a-2 that must be resolved before more comparisons

- **Level-set domain-edge artefact (open).** In the isotropic E1 case, the level set marks a far
  corner cell (row 5, col 59) as burned at 347 min where the graph gives 2,792 min. That is physically
  impossible at ≤ 1 m/min. Uniform-fuel runs also show cells up to +86 % late. This points to the
  ghost-cell/boundary treatment or to missing reinitialization (G1). It was being diagnosed when the
  owner stopped the run. **Until fixed, no level-set result on a bounded domain should be used for D1.**
- **E1 scoring censoring (fixed).** Cells beyond the solver horizon counted as infinite error. Solvers
  now run to 6,000 min and are scored on reference arrivals ≤ 4,000 min. This is reported as a
  deviation from the pre-registration (an implementation fix; thresholds unchanged).

## 5. Fire selection, checked against practice

The 2024 USGS workshop on evaluating wildland fire models with remote-sensing data used **three Arizona
wildfire case studies** (QUIC-Fire and FDS; a figure shows the Mogollon Rim area, Coconino NF)
[sourced: report abstract; the fire names were **not** confirmed]. If those fires overlap our pool, their
remote-sensing compilations (USGS SIR 2025-5053) would be an independent observation source, and they
confirm that Arizona 2022 fires are a recognised test bed. To check: read the report's methods section
(blocked here).

## 6. Recommended revision of M1a (for owner approval)

1. **Stop scheme selection** until both candidates are implemented to the documented state of practice:
   - level set: WENO5 + RK3 + reinitialization (+ narrow band), boundary treatment fixed;
   - graph: unchanged, but scoped to the conditions it is verified for.
2. **Code verification per scheme:** the existing analytic fixtures, **plus observed order of
   accuracy** (Δ, Δ/2, Δ/4) on the circle, the ellipse and the wind change; plus the standard cases
   (quadrant, merging fronts, slope).
3. **Solution verification per scheme:** 3-grid GCI on the mosaic. This replaces the cross-scheme E1
   reference, under a **new pre-registration** that cites this review. The first E1 results stay in the
   record as "inconclusive: references disagree".
4. **Decision criteria (pre-registered again):** a scheme is acceptable if it (a) converges at a
   positive observed order on the analytic cases, (b) has a GCI-estimated discretisation error at
   30 m ≤ 5 % (median) on the mosaic, and (c) passes the barrier fixtures. Among acceptable schemes,
   the cheapest wins. This follows the V&V separation instead of mixing it.
5. **Validation metric set:** add ADI, precision/recall/F1 and SDI (Duff 2016) to PLAN §9.

## Sources

- Oberkampf & Roy, *Verification and Validation in Scientific Computing* (Cambridge UP), frontmatter
  and code-verification chapter: https://assets.cambridge.org/97805211/13601/frontmatter/9780521113601_frontmatter.htm ,
  https://www.cambridge.org/core/books/abs/verification-and-validation-in-scientific-computing/code-verification/733E362E9B977EA1E3745BF9FAF607A0 ;
  NAFEMS code/solution verification: https://www.nafems.org/training/learning-hub/introduction-to-simulation-credibility/code-and-solution-verification
- ELMFIRE verification: https://elmfire.io/verification.html , https://elmfire.io/verification/verification_01.html
- Muñoz-Esparza et al. (2018), JAMES 10:908–926: https://agupubs.onlinelibrary.wiley.com/doi/full/10.1002/2017MS001108 ;
  WRF-Fire user guide: https://www2.mmm.ucar.edu/wrf/users/docs/user_guide_v4/v4.1/users_guide_chap-fire.html
- Bova, Mell & Hoffman (2016), IJWF 25:229–241: https://research.fs.usda.gov/treesearch/59231
- Mallet, Keyes & Fendell (2009), level-set wildfire propagation: https://www.fs.usda.gov/psw/publications/4402/mallet.2009.modelingWildlandFirePropagation.pdf
- NIST TN 1611, fire-front propagation using the level-set method: https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=900149
- Finney (2002) MTT: https://cdnsciencepub.com/doi/abs/10.1139/x02-068 ; Finney (2003) random landscapes:
  https://publish.csiro.au/wf/WF03010 ; MTT technical documentation:
  https://iftdss.firenet.gov/firenetHelp/help/pageHelp/content/20-models/mtt/techdocmtt.htm
- Filippi et al. (2014) / Duff et al. (2016) indices: https://www.researchgate.net/publication/305392514_Indices_for_the_evaluation_of_wildfire_spread_simulations_using_contemporaneous_predictions_and_observations_of_burnt_area
- Cruz & Alexander (2013), EMS 47:16–28: https://d10.nrfirescience.org/sites/default/files/2023-07/09-S-03-1_CruzAlexander_2013_EMS_UncerModeledROS.pdf
- USGS SIR 2025-5053: https://pubs.usgs.gov/publication/sir20255053
- Practitioner log (not peer reviewed): https://github.com/Tphambolio/wildfire-simulator/pull/1
