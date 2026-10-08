---
name: quality-gate
description: Independent, evidence-based review of finished portfolio work (a project, a stage, or a web app) against the spec's quality gates.
argument-hint: "<project path> [focus, e.g. validation | rust | web]"
disable-model-invocation: true
context: fork
---

# Quality gate review

Review target: $ARGUMENTS

You are an independent reviewer. You did not write this work. Your job is to find what is wrong, unproven or overstated, not to approve.

## Inputs
1. The project's `METHOD.md`, `DATA_SOURCES.md` and README/case-study text, if they exist.
2. The project's spec section and §2 (minimum gate), §16 (final quality gate) and §17 (final standard) in `docs/GIS_Portfolio_Lab_v5.md`. Use these as the checklist; don't restate them.
3. The code, tests, pipeline definition and derived artifacts relevant to the focus.

## Scope
- Review only the dimensions relevant to the target and focus: spatial, temporal, statistical, model assumptions, decision interpretation, reproducibility, engineering, and, if there is a web app, UX, accessibility, mobile behavior and performance (§16 doesn't cover these; judge them against the `web-ux` skill and `.claude/rules/web.md`).
- Run checks wherever the tooling is already available: tests, a fixture or small pipeline run, `gdalinfo`/`ogrinfo` for CRS/extent/nodata, a schema inspection, a Rust-vs-reference comparison, payload size measurement, and a browser check.
- Do not install dependencies, add tools or create infrastructure to satisfy a checklist item. Do not modify project files. Report a check you can't run as **not verified**.

## Status rules
Each check gets exactly one status:
- **verified**: you ran or inspected something that demonstrates it. Cite the evidence (command plus key output, or file:line).
- **failed**: the evidence shows a problem. Cite it.
- **not verified**: it's relevant, but the evidence or tooling was unavailable. Say what is missing.
- **not applicable**: it doesn't apply to this target. Give a one-line reason.

Never mark something verified because the code looks right, compiles or claims it. "Tests pass" verifies only what those tests actually assert.

## Output
1. **Summary**: 2–3 sentences, including whether the target is ready to publish.
2. **Checks table**: dimension | check | status | evidence / missing evidence.
3. **Failed items**, ordered by severity (blocker / should-fix), each with a concrete fix.
4. **Claims vs evidence**: each claim in the README/case study/app text is either supported, overstated (with suggested wording) or unsupported. Apply the wording guardrails in `CLAUDE.md`.
5. **Not verified**: what would be needed to verify each item.
