# <Project> — Method

> Status: draft | in progress | gated. Spec section: §<n>.
> Answer every heading with something concrete. Write "unknown" or "not applicable — <reason>" rather than leaving a heading empty.

## Problem / decision
The question, who would act on the answer, and what decision it informs.

## Study area and analytical unit
AOI and why it was chosen. The unit of analysis and the reporting unit, and why they differ if they do.

## Data and rationale
For each dataset: why it is needed, and which variable it supplies. Full provenance is in `DATA_SOURCES.md`.

## Harmonization
Target CRS and units, resolution and resampling method, temporal alignment, nodata handling.

## Baseline
The transparent reference method and what it should show.

## Advanced method
What it adds over the baseline and why that should help. Assumptions.

## Validation
Design (why it is independent enough), metrics, results, and the leakage checks performed.

## Uncertainty and sensitivity
What was varied, the ranges and why, and how the conclusions change.

## Decision metric
The output a user acts on, and how it should and should not be interpreted.

## Rust component
The kernel, why Rust, the reference implementation, the tolerance and the benchmark result. Or "none — <reason>".

## Limitations and omitted processes

## Decisions log
| Date | Decision | Alternatives considered | Reason |
|---|---|---|---|
