---
paths:
  - "**/web/**"
  - "**/*.{ts,tsx,js,jsx,mjs,css,html}"
---

# Web apps

- The app presents precomputed, validated artifacts (PMTiles, COG, Parquet, small JSON). No heavy analysis in the browser; if a computation is needed, move it into the local pipeline.
- Keep payloads small: measure bundle and data size before and after a change. Load layers and secondary content lazily. Each dependency must earn its weight.
- Prefer static delivery. No backend or runtime API without a concrete project requirement.
- Mobile and touch are first-class: nothing essential is hover-only, touch targets are adequate, and the layout works at phone width.
- Accessibility basics on every change: semantic HTML, keyboard operability, visible focus, sufficient contrast, colour never the only carrier of meaning, text alternatives for map-only information.
- Every rendered layer has a legend with units. Results carry their uncertainty and limitations nearby, and methodology and data sources are reachable from the app.
- For significant UX, information-architecture or visual decisions, use the `web-ux` skill. Follow decisions already recorded in `docs/product/DESIGN_DECISIONS.md` if it exists.
- Verify in a browser at phone and desktop widths before reporting a UI change as done.
