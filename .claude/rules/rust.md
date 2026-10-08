---
paths:
  - "**/*.rs"
  - "**/Cargo.toml"
---

# Rust

- Use Rust for a kernel only when the algorithm is computationally interesting or a measurement shows Python/GDAL is the bottleneck. Record the reason in the project's `METHOD.md`. Never use it for branding, and never to reimplement GDAL/PROJ/GEOS I/O, reprojection or mature geometry operations.
- A reference implementation (Python/NumPy, GDAL, or a hand-checked case) comes first and is the oracle.
- Deterministic output: seeded RNG; no results that depend on thread scheduling. If a parallel float reduction can change the result, use a fixed order or document the tolerance.
- Every kernel defines its numerical tolerance and its edge, border and nodata semantics explicitly, and has tests against the reference on small fixtures, including edge cases (borders, nodata, flat areas, ties, empty input).
- Prefer clear, idiomatic code over clever abstractions: plain structs and functions, minimal crates, no generic frameworks before a second real use exists. Each new crate needs a one-line justification.
- Performance claims need a reproducible benchmark that reports the fields in spec §12 (input sizes, algorithm, hardware, reference vs Rust, speedup) across several sizes. Use a release build and an established harness. Report small or negative speedups honestly.
- Optimize only after measuring; correctness against the reference comes before speed.
