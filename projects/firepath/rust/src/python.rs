use numpy::{IntoPyArray, PyArray1, PyArray3, PyReadonlyArray1, PyReadonlyArray2, PyReadonlyArray3};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::graph::{propagate, Field, Traversal};
use crate::field;
use crate::levelset;

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

/// Level-set time loop. `phi` (initialized and reinitialized) and `arrival` are updated in place.
#[pyfunction]
#[pyo3(signature = (t_change, r_head, ecc, theta, burnable, cell_m, near_x, near_y, phi, arrival,
                    t_start, t_stop, slope=None, cfl=0.4, band=8.0, reinit_every=10))]
#[allow(clippy::too_many_arguments)]
fn levelset_run(
    py: Python<'_>,
    t_change: PyReadonlyArray1<f64>,
    r_head: PyReadonlyArray3<f64>,
    ecc: PyReadonlyArray3<f64>,
    theta: PyReadonlyArray3<f64>,
    burnable: PyReadonlyArray2<bool>,
    cell_m: f64,
    near_x: PyReadonlyArray2<bool>,
    near_y: PyReadonlyArray2<bool>,
    mut phi: numpy::PyReadwriteArray2<f64>,
    mut arrival: numpy::PyReadwriteArray2<f64>,
    t_start: f64,
    t_stop: f64,
    slope: Option<(PyReadonlyArray2<f64>, PyReadonlyArray2<f64>, PyReadonlyArray2<f64>)>,
    cfl: f64,
    band: f64,
    reinit_every: usize,
) -> PyResult<()> {
    let (nr, nc) = burnable.as_array().dim();
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
    let p = levelset::Params { dx: cell_m, cfl, band, reinit_every };
    let (nx, ny) = (near_x.as_slice()?, near_y.as_slice()?);
    let ph = phi.as_slice_mut()?;
    let ar = arrival.as_slice_mut()?;
    py.detach(|| levelset::run(&f, &p, nx, ny, ph, ar, t_start, t_stop));
    Ok(())
}

/// Spread field for the given hours (oracle `firepath.field.hour`). Static per-cell arrays are 2-D
/// (nr, nc); u, v are (hours, nr, nc) float64; returns r_head, ecc, theta as (hours, nr, nc).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn field_build<'py>(
    py: Python<'py>,
    r0: PyReadonlyArray2<f64>,
    sigma: PyReadonlyArray2<f64>,
    beta: PyReadonlyArray2<f64>,
    beta_op: PyReadonlyArray2<f64>,
    waf: PyReadonlyArray2<f64>,
    tan_slope: PyReadonlyArray2<f64>,
    upslope: PyReadonlyArray2<f64>,
    timber: PyReadonlyArray2<bool>,
    burnable: PyReadonlyArray2<bool>,
    u: PyReadonlyArray3<f64>,
    v: PyReadonlyArray3<f64>,
    k: f64,
    a_u: f64,
    a_s: f64,
    g: f64,
    wind_factor: f64,
) -> PyResult<(Bound<'py, PyArray3<f64>>, Bound<'py, PyArray3<f64>>, Bound<'py, PyArray3<f64>>)> {
    let (hours, nr, nc) = u.as_array().dim();
    if v.as_array().dim() != (hours, nr, nc) || burnable.as_array().dim() != (nr, nc) {
        return Err(PyValueError::new_err("shape mismatch between wind and static arrays"));
    }
    let st = field::Static {
        r0: r0.as_slice()?,
        sigma: sigma.as_slice()?,
        beta: beta.as_slice()?,
        beta_op: beta_op.as_slice()?,
        waf: waf.as_slice()?,
        tan_slope: tan_slope.as_slice()?,
        upslope: upslope.as_slice()?,
        timber: timber.as_slice()?,
        burnable: burnable.as_slice()?,
    };
    let p = field::Params { k, a_u, a_s, g, wind_factor };
    let (us, vs) = (u.as_slice()?, v.as_slice()?);
    let len = hours * nr * nc;
    let (mut r, mut e, mut t) = (vec![0.0; len], vec![0.0; len], vec![0.0; len]);
    py.detach(|| field::build(&st, &p, us, vs, &mut r, &mut e, &mut t));
    let shape = (hours, nr, nc);
    let to3 = |x: Vec<f64>| numpy::ndarray::Array3::from_shape_vec(shape, x).unwrap().into_pyarray(py);
    Ok((to3(r), to3(e), to3(t)))
}

#[pymodule]
fn firepath_kernels(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(propagate_graph, m)?)?;
    m.add_function(wrap_pyfunction!(levelset_run, m)?)?;
    m.add_function(wrap_pyfunction!(field_build, m)?)?;
    Ok(())
}
