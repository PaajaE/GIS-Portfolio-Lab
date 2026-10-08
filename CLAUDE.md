# GIS Portfolio Lab

Five analytical GIS products built from open data. Heavy analysis runs locally; the web serves precomputed results.

**Source of truth:** `docs/GIS_Portfolio_Lab_v5.md`. Do not load it whole. Read the section the task needs:
§1 architecture · §2 project workflow + minimum gate · §3 engineering (reproducibility, provenance, testing) ·
§5–11 individual projects · §12 Rust story + benchmark fields · §13 web product · §14 deployment · §15 build order · §16 final quality gate · §17 final standard.
Never edit the spec unless asked.

## Architecture limits
- Local-first computation, static delivery. No database, API, server, cloud ETL, container orchestration or new framework unless a concrete project requirement justifies it. If one seems needed, propose it with the reason and stop; don't add it.
- Python: acquisition, orchestration, statistics/ML, validation, web-data generation.
- Rust: computational kernels where the algorithm or a measurement justifies it (see `.claude/rules/rust.md`).
- GDAL/PROJ/GEOS/DuckDB: mature operations. Use them; don't reimplement them.
- Prefer the simplest design that works: plain functions and files over frameworks, layers or plugin systems.
- Each new dependency needs a one-line justification. Prefer tools already in use.

## Analytical discipline
Every project follows: problem → data → analytical unit → preprocessing → baseline → advanced method → validation → uncertainty/sensitivity → decision metric → presentation.
Before designing or changing any analysis step, use the `gis-analysis` skill.
A map is the presentation layer, not the result. A beautiful map built on a weak method is a failure.

Wording guardrails (output must be no stronger than the evidence):
- susceptibility ≠ hazard ≠ risk; exposure is not risk without consequence/vulnerability
- distance is not accessibility; network travel time is
- a modeled scenario is not a forecast; a regulatory map is not an observed event
- feasibility is "potential feasibility under stated assumptions", not entitlement
- don't call something "validated against X" if X measures something different

## Working style
- Small change: inspect only what's relevant, make the smallest reasonable change, validate it.
- Architectural or multi-file change: inspect the existing system, list dependencies and consequences, propose the approach, and wait before making extensive edits.
- "It compiles/runs" is not correctness. When reporting, say what was verified, how, and what was not verified.
- Research current official documentation and primary sources for significant architectural, UX, accessibility or technology decisions, scaled to the decision's impact and uncertainty. Skip research for minor changes where an established pattern already applies.
- Don't decide open architectural questions (repo layout, Python↔Rust integration, deployment) ahead of need. Settle them when a project requires it and record them below.

## Context hygiene
- Inspect data with summaries (`gdalinfo`, `ogrinfo -so`, DuckDB `DESCRIBE`/`SUMMARIZE`, small `LIMIT` samples). Never read or print large data files.
- Raw and intermediate data are not committed.
- Per-project context lives in that project's `METHOD.md` and `DATA_SOURCES.md`. Read those first when working on a project.

## Skills
- `gis-analysis`: designing or reviewing analytical methods; starting a project's METHOD.md / DATA_SOURCES.md.
- `web-ux`: significant UX, information-architecture or visual decisions for a web app.
- `/quality-gate <project path>`: run by the user to get an independent, evidence-based review of finished work.

## Established layout and commands
None yet. Record them here once a project settles them.
