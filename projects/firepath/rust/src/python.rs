use numpy::{IntoPyArray, PyArray1, PyReadonlyArray1, PyReadonlyArray2, PyReadonlyArray3};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::graph::{propagate, Field, Traversal};

/// Graph propagation. Stencil tables come from `firepath.stencil` (flattened):
/// meta (n_t, 6) int64 = dr, dc, piece_start, piece_count, side_start, side_count;
/// geom (n_t, 2) = length, phi; pieces (n_p, 3) = dr, dc, frac; sides (n_s, 4) int64.
#[pyfunction]
#[pyo3(signature = (t_change, r_head, ecc, theta, burnable, cell_m, meta, geom, pieces, sides,
                    slope=None, inside=None, points=None, seed=None, t0=0.0, t_stop=f64::INFINITY))]
#[allow(clippy::too_many_arguments)]
fn propagate_graph<'py>(
    py: Python<'py>,
    t_change: PyReadonlyArray1<f64>,
    r_head: PyReadonlyArray3<f64>,
    ecc: PyReadonlyArray3<f64>,
    theta: PyReadonlyArray3<f64>,
    burnable: PyReadonlyArray2<bool>,
    cell_m: f64,
    meta: PyReadonlyArray2<i64>,
    geom: PyReadonlyArray2<f64>,
    pieces: PyReadonlyArray2<f64>,
    sides: PyReadonlyArray2<i64>,
    slope: Option<(PyReadonlyArray2<f64>, PyReadonlyArray2<f64>, PyReadonlyArray2<f64>)>,
    inside: Option<PyReadonlyArray2<bool>>,
    points: Option<PyReadonlyArray2<f64>>,
    seed: Option<PyReadonlyArray2<f64>>,
    t0: f64,
    t_stop: f64,
) -> PyResult<(Bound<'py, PyArray1<f64>>, Bound<'py, PyArray1<u8>>)> {
    let (nr, nc) = burnable.as_array().dim();
    let meta = meta.as_array();
    let geom = geom.as_array();
    let pcs = pieces.as_array();
    let sds = sides.as_array();
    let trs: Vec<Traversal> = (0..meta.shape()[0])
        .map(|i| {
            let (ps, pn, ss, sn) = (meta[[i, 2]] as usize, meta[[i, 3]] as usize, meta[[i, 4]] as usize, meta[[i, 5]] as usize);
            Traversal {
                dr: meta[[i, 0]],
                dc: meta[[i, 1]],
                length: geom[[i, 0]],
                phi: geom[[i, 1]],
                pieces: (ps..ps + pn).map(|j| (pcs[[j, 0]] as i64, pcs[[j, 1]] as i64, pcs[[j, 2]])).collect(),
                sides: (ss..ss + sn).map(|j| ((sds[[j, 0]], sds[[j, 1]]), (sds[[j, 2]], sds[[j, 3]]))).collect(),
            }
        })
        .collect();
    let slope_v = slope.as_ref().map(|(a, b, c)| (a.as_slice().unwrap(), b.as_slice().unwrap(), c.as_slice().unwrap()));
    let f = Field {
        nr,
        nc,
        t_change: t_change.as_slice()?,
        r_head: r_head.as_slice()?,
        ecc: ecc.as_slice()?,
        theta: theta.as_slice()?,
        burnable: burnable.as_slice()?,
        cell_m,
        slope: slope_v,
    };
    let pts: Vec<(usize, usize, f64)> = match &points {
        Some(p) => {
            let a = p.as_array();
            (0..a.shape()[0]).map(|i| (a[[i, 0]] as usize, a[[i, 1]] as usize, a[[i, 2]])).collect()
        }
        None => vec![],
    };
    let ins = inside.as_ref().map(|a| a.as_slice().unwrap());
    let sd = seed.as_ref().map(|a| a.as_slice().unwrap());
    let out = py
        .detach(|| propagate(&f, &trs, ins, &pts, sd, t0, t_stop))
        .map_err(PyValueError::new_err)?;
    Ok((out.arrival.into_pyarray(py), out.status.into_pyarray(py)))
}

#[pymodule]
fn firepath_kernels(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(propagate_graph, m)?)?;
    Ok(())
}
