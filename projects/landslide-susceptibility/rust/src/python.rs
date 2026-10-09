use numpy::{IntoPyArray, PyArray2, PyReadonlyArray2, PyUntypedArrayMethods};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

type A2<'py> = Bound<'py, PyArray2<f32>>;

fn to2(py: Python<'_>, v: Vec<f32>, h: usize, w: usize) -> PyResult<A2<'_>> {
    let a = numpy::ndarray::Array2::from_shape_vec((h, w), v).map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(a.into_pyarray(py))
}

/// terrain3x3(z: float32[H,W], cell: float, nodata: float)
///   -> (slope_deg, northness, eastness, profile_curv, plan_curv, tri)
#[pyfunction]
fn terrain3x3<'py>(
    py: Python<'py>,
    z: PyReadonlyArray2<'py, f32>,
    cell: f64,
    nodata: f32,
) -> PyResult<(A2<'py>, A2<'py>, A2<'py>, A2<'py>, A2<'py>, A2<'py>)> {
    let (h, w) = (z.shape()[0], z.shape()[1]);
    let s = z.as_slice().map_err(|_| PyValueError::new_err("z must be C-contiguous"))?;
    let t = py.detach(|| crate::terrain3x3(s, h, w, cell, nodata));
    Ok((
        to2(py, t.slope_deg, h, w)?,
        to2(py, t.northness, h, w)?,
        to2(py, t.eastness, h, w)?,
        to2(py, t.profile_curv, h, w)?,
        to2(py, t.plan_curv, h, w)?,
        to2(py, t.tri, h, w)?,
    ))
}

/// window_stats(x: float32[H,W], r: int, nodata: float) -> (mean, sd, min, max); window (2r+1)^2
#[pyfunction]
fn window_stats<'py>(
    py: Python<'py>,
    x: PyReadonlyArray2<'py, f32>,
    r: usize,
    nodata: f32,
) -> PyResult<(A2<'py>, A2<'py>, A2<'py>, A2<'py>)> {
    let (h, w) = (x.shape()[0], x.shape()[1]);
    let s = x.as_slice().map_err(|_| PyValueError::new_err("x must be C-contiguous"))?;
    let o = py.detach(|| crate::window_stats(s, h, w, r, nodata));
    Ok((to2(py, o.mean, h, w)?, to2(py, o.sd, h, w)?, to2(py, o.min, h, w)?, to2(py, o.max, h, w)?))
}

#[pymodule]
fn terrain_kernels(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(terrain3x3, m)?)?;
    m.add_function(wrap_pyfunction!(window_stats, m)?)
}
