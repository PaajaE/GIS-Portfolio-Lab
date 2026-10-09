# Design decisions — portfolio web apps

Living reference for the family of portfolio apps (see `.claude/skills/web-ux`). Only decisions that were
actually made and implemented. Each entry: decision · context · reason · source · apps.

Apps: **PI** = Parcel Intelligence (`projects/parcel-intelligence/web`).

## Page structure

**D1. One page: question → result → interactive workbench → case study.**
The first screen states the question in plain language (h1), a two-sentence lede with the wording
guardrail ("potential feasibility … not entitlement"), and the headline result. Below it: map + panel
("workbench"); below that the case study in the spec §13 order (Problem … Limitations, Downloads/Source).
*Reason:* spec §13 — the first screen answers "what problem did I solve", not "which technologies";
methodology and limitations stay reachable without a second page. · PI

**D2. Headline result doubles as the legend.**
The robustness distribution is a labelled stacked bar with counts; its colours are the map's parcel
colours, and it is stated as the legend. On phones the in-bar labels are replaced by a key list.
*Reason:* avoids KPI tiles (web-ux §6) and puts the main number next to its encoding; one legend, not two. · PI

**D3. Workbench layout: map left, panel right (≥ 900 px); stacked map → panel below (< 900 px).**
Panel order: search → view mode → layer toggles → report. The map is sticky on desktop.
On phones the map is 62 vh with MapLibre cooperative gestures (two-finger pan) so the page still scrolls.
*Reason:* inspection results are long text; a bottom sheet over the map would hide the map and is harder
to make accessible. · PI

## Interaction

**D4. Everything the map shows is reachable without the map.**
Search is a WAI-ARIA combobox with listbox popup (arrow keys, Enter, Escape, `aria-activedescendant`).
Selecting from search or by click produces the same text report; a skip link jumps to search.
The selected parcel is encoded in the URL hash (`#parcel=<LOC_ID>`) for sharing.
*Reason:* WCAG 2.2 1.1.1 / 2.1.1 — map canvas is not accessible; click-to-select is a convenience.
*Source:* WAI-ARIA APG Combobox pattern. · PI

**D5. No hover-only information.** Hover only changes the cursor; all detail appears on click/tap or
search. *Reason:* touch first-class (rules/web.md). · PI

**D6. Scenario switch = segmented radio group (native radios), not tabs or a slider.**
Values are discrete, named assumption sets; native radios give keyboard and screen-reader behaviour for
free. Four options in one row (≥ 441 px), 2 × 2 grid below. Touch targets ≥ 44 px high. · PI

**D7. The report always compares scenarios side by side.**
Even when the map shows one scenario, the report shows all three as bars against the whole parcel, with
the baseline (net unconstrained area, hatched) under the result (solid). The active scenario is marked.
*Reason:* the analytical claim is robustness; one number per parcel would hide it. · PI

## Visual encoding

**D8. Light, paper-like theme; system font stack; no web fonts for UI.**
Background `#f7f5f0`, ink `#1f2328`, secondary ink `#4a5059` (≈ 8:1). Dark mode not implemented yet.
*Reason:* reading-heavy case study, maps over hillshade read best on light; zero font payload. · PI

**D9. Ordered results use a single-hue sequential ramp; categories that are "not analysed" use a hatch.**
PI robustness: `#0f4c5c` → `#2f8a8a` → `#9cd2c4` → `#ebe6da` (darker = holds under stricter assumptions);
not screened = grey hatch pattern. Feasible area (the result geometry) = amber `#f59e0b` with darker
outline, consistent in map, report bars and validation figures.
*Reason:* ordinal data need a perceptually ordered ramp (no rainbow); the hatch makes "not analysed"
distinguishable without colour; labels and text carry the meaning too (WCAG 1.4.1). · PI

**D10. Self-contained cartography; no third-party basemap.**
Base = own hillshade (image overlay), water, streams, roads, buildings, town boundary from the project's
sources; street labels with self-hosted Noto Sans glyphs (0–255 range only).
*Reason:* no API keys, no extra licences/attribution obligations, the context layers are the analysis
inputs. *Trade-off:* no place labels beyond streets. · PI

**D11. Every layer toggle carries its swatch and units in the label** (e.g. "Slope ≥ 15 / 25 / 35 %").
*Reason:* every rendered layer needs a legend with units (rules/web.md). · PI

## Data delivery and performance

**D12. Static files only: PMTiles (vector) + small JSON + image overlays; MapLibre GL JS and PMTiles
from jsDelivr at pinned versions.** PI: maplibre-gl 6.11.1 (ESM), pmtiles 4.5.0.
Heavy or optional assets load lazily: the 1.4 MB slope overlay on first toggle; the 2.2 MB parcel detail
JSON on first search focus or selection. Development server must support HTTP Range (`npx http-server`).
*Reason:* rules/web.md (static delivery, small payloads); PMTiles needs range requests. · PI

**D13. App text that contains results is filled from the pipeline's `summary.json`, not typed by hand.**
*Reason:* numbers in the narrative cannot drift from the analysis. · PI

## Content

**D14. Validation items are tagged verified / comparison / manual.** A "comparison" is agreement with a
different construct and is never called validation; honest negatives (e.g. no detectable gain over a
baseline, small Rust speed-up) are stated in the same place as positives. · PI

**D15. Limitations section is titled "what this screen cannot tell you" and sits before downloads.** · PI
