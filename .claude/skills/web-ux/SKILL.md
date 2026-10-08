---
name: web-ux
description: Decision process for significant UX, information-architecture, interaction, map-design or visual decisions in a portfolio web app — designing a new app or screen, choosing how to show scenarios/time/uncertainty, or changing shared patterns. Not for minor tweaks that follow established patterns.
---

# Web UX decisions

This is a process, not a style guide. The portfolio's apps should feel like one coherent family, yet each should be shaped by its own analytical task. They are not copies of one layout.

## 1. Start from the task, not the components
- Who is the primary user, what do they want to find out, and which decision does the app support? Take this from the project's `METHOD.md` decision metric. If the audience is unknown, ask.
- What must the first screen communicate? (Spec §13: the problem solved, not the technologies used.)
- List the 3–5 core user tasks, e.g. "compare scenarios for one parcel" or "see when roads close". The design serves these tasks.

## 2. Derive the information architecture from the analysis
- The analytical structure shapes the interface: a scenario comparison needs comparison views, an arrival-time model needs a time control, a lookup task needs search and a report, an optimization result needs a before/after view.
- Decide where the narrative (case study), the interactive map, the metrics and the methodology/limitations sit, and how users move between them on mobile and desktop.
- Uncertainty, assumptions and limitations belong next to the results they qualify.

## 3. Reuse before inventing
- Read `docs/product/DESIGN_DECISIONS.md` if it exists. Reuse the recorded decisions, patterns and components where they fit this app's task.
- Where this app needs something different, deviate deliberately and record why. Family coherence comes from shared principles and patterns, not identical screens.

## 4. Research in proportion to impact
- For significant or uncertain decisions (new interaction patterns, map encoding of uncertainty or time, accessibility of map interaction, colour scales, performance strategy), consult current primary sources: WCAG and WAI-ARIA guidance, MapLibre and PMTiles docs, browser platform docs (MDN, web.dev), and established cartography and scientific-visualization guidance. Cite what you used.
- Don't research decisions already covered by recorded decisions or well-established patterns.

## 5. Compare options, then decide
For significant decisions, sketch 2–3 options briefly and evaluate them against:
task fit · clarity of the analytical message and uncertainty · mobile/touch behavior · accessibility · payload and runtime performance · consistency with the family.
Don't choose an option because it is easier to implement. If implementation cost really matters, say so explicitly as a trade-off.

## 6. Avoid easy defaults unless they are justified for the task
- a generic dark "AI dashboard" with KPI tiles
- the map as decorative background
- rainbow or non-perceptual colour ramps; colour as the only encoding
- hover-only inspection
- numbers without units, baseline or uncertainty
- a technology-first hero section
- decorative animation that costs performance or attention

## 7. Verify
Check the result in a real browser at phone and desktop widths. Run automated accessibility checks if the tooling is already available, plus a keyboard-only pass. Measure payload and load behavior. Report what was and wasn't verified.

## 8. Record
`docs/product/DESIGN_DECISIONS.md` is the family's living reference. **Create it while designing the first web app.** Don't create it before there's a concrete app. Afterwards, update it whenever a decision should carry to other apps. Keep entries short: the decision, the context, the reason, the source if any, and the apps that use it. Record only decisions actually made and implemented. Don't add speculative design systems.
