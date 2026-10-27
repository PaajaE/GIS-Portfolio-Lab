//! FirePath propagation kernels (PLAN §12). Pure Rust; the `python` feature adds PyO3 bindings.

pub mod field;
pub mod graph;
pub mod levelset;

#[cfg(feature = "python")]
mod python;
