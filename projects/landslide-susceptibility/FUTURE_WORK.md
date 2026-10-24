# Landslide Susceptibility — future work and handoff

Status 2026-10-24: finished on the **simple path** chosen by the owner. The 5 m logistic regression is a **local
experiment** for Buncombe + Yancey: robust inside the AOI, not transferable, and distorted across geology
boundaries. Exposure is skipped. The app is public-ready once the items in "Open for completion" are done. The
public summary of this list is the "What could come next" section of `web/index.html`.

## Open for completion (can be done in a cloud session; no `data/` needed)
1. **Site root landing page** (owner decision 2026-10-24: a directory of apps; more apps will follow).
   - Add `site/index.html` with one card per app: title, one-sentence question, status ("local experiment"
     for this app), link.
   - Change `.github/workflows/pages.yml` to copy `site/` to `_site/` and both `projects/*/web/` folders.
   - Record the landing-page decision in `docs/product/DESIGN_DECISIONS.md`.
2. **Web data in git:** `web/data/` is committed as of 2026-10-24 (the published artifacts).
   - Re-generating it needs `data/` (`make data-restore`, then `make web`, then `python -m landslide.m7` for the
     site images), so that is a local or full-bundle task.
3. **Docs (M9):**
   - README (status, how to run, limits)
   - DATA_SOURCES (NC OneMap terms verified 2026-10-24, quoted in "Licence check" below; the site images and
     their credits)
   - METHOD (M7 rule and the hand-check sample)
   - PLAN status rows for M7–M9
4. **Browser checks still missing:** 320 / 400 / 768 px widths, a full keyboard-only pass, an automated
   accessibility check (if available), and the measured payload per first view.
5. **PR** `feat/landslide-susceptibility` → `main`. **Merging deploys to Pages (= publishing); the owner merges.**
6. `/quality-gate projects/landslide-susceptibility`, triggered by the owner.

## Licence check (verified 2026-10-24)
NC OneMap terms (Hub page item `e60514c3b78542ef9902e3d7f7a671c1`, read via the ArcGIS REST item data):
- "free and unrestricted use policy"
- written release agreements "are not required and will not be issued"
- citation: NC OneMap (2019)…
- no warranty

Service credits:
- before: NC911, NCCGIA
- after: NC Collaboratory at UNC Chapel Hill

The app uses four 2 km × 2 km excerpts at 1 m for display only, with citation and credits. Not legal advice;
consistent with the published terms.

## Analytical future work (each needs a pre-registered design, as in M4–M6)
- **Transferability through the trigger, not geology.**
  - The geology terms encode the rainfall gradient. Removing them failed the pre-registered rule
    (`validation/NOGEO_TEST.md`).
  - Candidate test: rainfall represented non-linearly (spline or bins) and/or the maximum 6 h intensity. The 6 h
    maximum explained *where* Helene's failures happened (M6 T1 passed) but did not change the ranking (T2).
  - Criteria as in the no-geology test: AOI non-inferiority, plus leave-one-county-out and Watauga improvements
    judged on intervals.
- **Rainfall-matched geology check:** compare geology groups only within overlapping rainfall ranges. This shows
  whether any real lithology effect remains.
- **Mapping completeness:** some well-watered watersheds have almost no mapped failure of any kind (e.g. Big
  Crabtree Creek, Bent Creek). Options: check them on the Helene 2025 imagery (a small frozen sample), or ask NCGS
  about mapping extent. Contacting NCGS needs owner approval.
- **Human review** of `validation/hand_check_sample.csv`: 40 frozen locations (15 hits, 15 top-10 % without a
  mapped initiation, 10 misses), with empty AI and human columns. Any AI-assisted pass must be labelled
  "AI-assisted, pending human review".
- **Exposure** (skipped by the owner): buildings and roads in flagged slopes per HUC-12.
  - It needs a footprint source with clear terms; the NC Composite Footprints state no licence, Microsoft US
    Building Footprints are ODbL.
  - Wording: "exposure to initiation-susceptible terrain", not risk.
- **Reference products:** the USGS national susceptibility map (ScienceBase, manual download) as a labelled
  comparison.
- **Other storms or regions:** they need their own inventories. Watauga 1940 → 2024 showed that a locally
  trained model can rank (AUC 0.79) where the AOI model cannot (0.50).

## App future work (only after the analysis supports it)
- Show the bootstrap rank spread (`ens_rank_p10/p90.tif`) as a view; today only the share is in the text.
- Per-unit report (click / search) on the slope-unit summary layer; vector PMTiles of the units.
- A held-out validation view with hits and misses by rank band, and a per-HUC capture choropleth with a
  "too few" hatch.
- A dark mode for the family (D8 says not implemented).

## What needs the local machine (or a full data bundle)
Everything that reads `data/`:
- `make prepare`, `make baseline`, `make advanced`, `make product`, `make m6`, `make nogeo`, `make web`, `m7`
- The bundle is restored with `make data-restore` (private repo `PaajaE/GIS-Portfolio-Lab-data`, about 0.9 GB);
  `make prepare` then needs about 12 GB of disk, 6–8 GB of RAM and hours.
