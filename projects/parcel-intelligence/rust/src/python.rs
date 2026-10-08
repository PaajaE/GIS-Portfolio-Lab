use numpy::{IntoPyArray, PyArray1, PyArray2, PyReadonlyArray2, PyUntypedArrayMethods};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

type Out<'py> = (
    Bound<'py, PyArray1<i64>>,
    Bound<'py, PyArray1<i64>>,
    Bound<'py, PyArray1<i64>>,
    Bound<'py, PyArray2<u8>>,
);

/// screen_patches(parcel: int32[H,W], feasible: bool[H,W], n_parcels, open_size=1,
///                connectivity=4, min_cells=1)
///   -> (feasible_cells, largest_cells, n_patches, mask)
#[pyfunction]
#[pyo3(signature = (parcel, feasible, n_parcels, open_size=1, connectivity=4, min_cells=1))]
fn screen_patches<'py>(
    py: Python<'py>,
    parcel: PyReadonlyArray2<'py, i32>,
    feasible: PyReadonlyArray2<'py, bool>,
    n_parcels: usize,
    open_size: usize,
    connectivity: u8,
    min_cells: i64,
) -> PyResult<Out<'py>> {
    let (h, w) = (parcel.shape()[0], parcel.shape()[1]);
    if feasible.shape() != [h, w] {
        return Err(PyValueError::new_err("parcel and feasible shapes differ"));
    }
    let p = parcel.as_slice().map_err(|_| PyValueError::new_err("parcel must be C-contiguous"))?;
    let f = feasible.as_slice().map_err(|_| PyValueError::new_err("feasible must be C-contiguous"))?;
    let s = py
        .detach(|| crate::screen_patches(p, f, h, w, n_parcels, open_size, connectivity, min_cells))
        .map_err(PyValueError::new_err)?;
    let mask = numpy::ndarray::Array2::from_shape_vec((h, w), s.mask)
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok((
        s.feasible_cells.into_pyarray(py),
        s.largest_cells.into_pyarray(py),
        s.n_patches.into_pyarray(py),
        mask.into_pyarray(py),
    ))
}

#[pymodule]
fn parcel_kernels(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(screen_patches, m)?)
}
