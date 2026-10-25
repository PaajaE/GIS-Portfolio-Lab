//! FirePath propagation kernels (PLAN §12). Pure Rust; the `python` feature adds PyO3 bindings.

pub mod graph;

#[cfg(feature = "python")]
mod python;
