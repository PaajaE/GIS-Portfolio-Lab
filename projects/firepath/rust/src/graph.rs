//! Time-dependent label-setting on a stencil graph (METHOD.md "Propagation"; oracle:
//! `firepath.reference.propagate`). Same operations in the same order as the reference, so arrivals
//! agree to floating-point identity on the same platform; the acceptance tolerance is
//! |dt| <= 1e-9 * max(1, t) (PLAN §12).

use std::cmp::{Ordering, Reverse};
use std::collections::BinaryHeap;

pub const NOT_REACHED: u8 = 0;
pub const REACHED: u8 = 1;
pub const INITIAL: u8 = 2;
pub const BARRIER: u8 = 3;

/// One stencil move: exact traversal of the centre-to-centre segment (from `firepath.stencil`).
pub struct Traversal {
    pub dr: i64,
    pub dc: i64,
    pub length: f64,
    pub phi: f64,
    /// (dr, dc, share of the segment length) per crossed cell, in order.
    pub pieces: Vec<(i64, i64, f64)>,
    /// Pairs of side cells at grid vertices the segment passes through.
    pub sides: Vec<((i64, i64), (i64, i64))>,
}

/// Piecewise-constant (in time) elliptical spread field, row-major arrays.
pub struct Field<'a> {
    pub nr: usize,
    pub nc: usize,
    pub t_change: &'a [f64],
    pub r_head: &'a [f64], // (H, nr, nc)
    pub ecc: &'a [f64],
    pub theta: &'a [f64],
    pub burnable: &'a [bool], // (nr, nc)
    pub cell_m: f64,
    /// Optional slope-plane frame per cell: (cos s, ux, uy) (`firepath.slopeplane.frame`).
    pub slope: Option<(&'a [f64], &'a [f64], &'a [f64])>,
}

impl Field<'_> {
    /// (interval index containing t, end time of that interval)
    fn interval(&self, t: f64) -> (usize, f64) {
        let h = self.t_change.partition_point(|&s| t >= s);
        let end = if h < self.t_change.len() { self.t_change[h] } else { f64::INFINITY };
        (h, end)
    }

    fn speed(&self, h: usize, k: usize, phi: f64) -> f64 {
        let i = h * self.nr * self.nc + k;
        let e = self.ecc[i];
        let th = self.theta[i];
        match self.slope {
            None => self.r_head[i] * (1.0 - e) / (1.0 - e * (phi - th).cos()),
            Some((cs, ux, uy)) => {
                let (cs, ux, uy) = (cs[k], ux[k], uy[k]);
                let (dx, dy) = (phi.cos(), phi.sin());
                let (d1, d2) = ((dx * ux + dy * uy) / cs, -dx * uy + dy * ux);
                let (tx, ty) = (th.cos(), th.sin());
                let (w1, w2) = ((tx * ux + ty * uy) / cs, -tx * uy + ty * ux);
                let norm = d1.hypot(d2);
                let cos_psi = (d1 * w1 + d2 * w2) / (norm * w1.hypot(w2));
                self.r_head[i] * (1.0 - e) / (1.0 - e * cos_psi) / norm
            }
        }
    }
}

/// A_e(t_u): arrival at the centre of v when leaving the centre of u = (r, c) at t_u.
fn edge_arrival(f: &Field, r: i64, c: i64, t: &Traversal, t_u: f64, inside: Option<&[bool]>) -> f64 {
    let mut tau = t_u;
    let seg = t.length * f.cell_m;
    for &(dr, dc, frac) in &t.pieces {
        let k = ((r + dr) as usize) * f.nc + (c + dc) as usize;
        if let Some(ins) = inside {
            if ins[k] {
                continue;
            }
        }
        let mut rem = frac * seg;
        while rem > 0.0 {
            let (h, end) = f.interval(tau);
            let s = f.speed(h, k, t.phi);
            let dt = rem / s;
            if tau + dt <= end {
                tau += dt;
                rem = 0.0;
            } else {
                rem -= s * (end - tau);
                tau = end;
            }
        }
    }
    tau
}

fn edge_valid(barrier: &[bool], nr: i64, nc: i64, r: i64, c: i64, t: &Traversal) -> bool {
    for &(dr, dc, _) in &t.pieces {
        let (rr, cc) = (r + dr, c + dc);
        if rr < 0 || rr >= nr || cc < 0 || cc >= nc || barrier[(rr * nc + cc) as usize] {
            return false;
        }
    }
    for &((a0, a1), (b0, b1)) in &t.sides {
        if barrier[((r + a0) * nc + c + a1) as usize] && barrier[((r + b0) * nc + c + b1) as usize] {
            return false;
        }
    }
    true
}

#[derive(PartialEq)]
struct Key(f64, usize);
impl Eq for Key {}
impl PartialOrd for Key {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}
impl Ord for Key {
    fn cmp(&self, o: &Self) -> Ordering {
        self.0.total_cmp(&o.0).then(self.1.cmp(&o.1))
    }
}

pub struct Output {
    pub arrival: Vec<f64>,
    pub status: Vec<u8>,
}

/// Label-setting propagation (Mode A `inside`, Mode B `points`, optional `seed` upper bounds).
pub fn propagate(
    f: &Field,
    trs: &[Traversal],
    inside: Option<&[bool]>,
    points: &[(usize, usize, f64)],
    seed: Option<&[f64]>,
    t0: f64,
    t_stop: f64,
) -> Result<Output, String> {
    let (nr, nc) = (f.nr, f.nc);
    let n = nr * nc;
    let barrier: Vec<bool> = f.burnable.iter().map(|b| !b).collect();
    let mut arrival = vec![f64::INFINITY; n];
    let mut status: Vec<u8> = barrier.iter().map(|&b| if b { BARRIER } else { NOT_REACHED }).collect();
    let mut done = vec![false; n];
    let mut heap: BinaryHeap<Reverse<Key>> = BinaryHeap::new();
    if let Some(ins) = inside {
        for k in 0..n {
            if ins[k] {
                done[k] = true;
                if f.burnable[k] {
                    arrival[k] = t0;
                    status[k] = INITIAL;
                    heap.push(Reverse(Key(t0, k)));
                    done[k] = false;
                }
            }
        }
    }
    for &(r, c, t) in points {
        let k = r * nc + c;
        if barrier[k] {
            return Err(format!("ignition on a barrier cell ({r}, {c})"));
        }
        if t < arrival[k] {
            arrival[k] = t;
            heap.push(Reverse(Key(t, k)));
        }
    }
    if let Some(sd) = seed {
        for k in 0..n {
            if sd[k].is_finite() && f.burnable[k] && !done[k] && sd[k] < arrival[k] {
                arrival[k] = sd[k];
                heap.push(Reverse(Key(sd[k], k)));
            }
        }
    }
    let (nri, nci) = (nr as i64, nc as i64);
    while let Some(Reverse(Key(t_u, k))) = heap.pop() {
        assert!(!t_u.is_nan(), "NaN arrival in heap");
        if done[k] || t_u > arrival[k] {
            continue;
        }
        if t_u > t_stop {
            break;
        }
        done[k] = true;
        let (r, c) = ((k / nc) as i64, (k % nc) as i64);
        for tr in trs {
            let (rv, cv) = (r + tr.dr, c + tr.dc);
            if rv < 0 || rv >= nri || cv < 0 || cv >= nci {
                continue;
            }
            let kv = (rv * nci + cv) as usize;
            if done[kv] || barrier[kv] {
                continue;
            }
            if let Some(ins) = inside {
                if ins[kv] {
                    continue;
                }
            }
            if !edge_valid(&barrier, nri, nci, r, c, tr) {
                continue;
            }
            let t_v = edge_arrival(f, r, c, tr, t_u, inside);
            if t_v < arrival[kv] {
                arrival[kv] = t_v;
                heap.push(Reverse(Key(t_v, kv)));
            }
        }
    }
    for k in 0..n {
        if status[k] == NOT_REACHED {
            if arrival[k].is_finite() && arrival[k] <= t_stop {
                status[k] = REACHED;
            } else {
                arrival[k] = f64::INFINITY;
            }
        }
    }
    Ok(Output { arrival, status })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn eight() -> Vec<Traversal> {
        // radius-1 stencil: straight moves cross two cells half each; diagonals pass a vertex
        let mut v = Vec::new();
        for (dr, dc) in [(-1i64, -1i64), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)] {
            let diag = dr != 0 && dc != 0;
            v.push(Traversal {
                dr,
                dc,
                length: ((dr * dr + dc * dc) as f64).sqrt(),
                phi: (-(dr as f64)).atan2(dc as f64),
                pieces: vec![(0, 0, 0.5), (dr, dc, 0.5)],
                sides: if diag { vec![((dr, 0), (0, dc))] } else { vec![] },
            });
        }
        v
    }

    #[test]
    fn isotropic_line_and_diagonal_wall() {
        let (nr, nc) = (5usize, 5usize);
        let ones = vec![1.0; nr * nc];
        let zeros = vec![0.0; nr * nc];
        let burn = vec![true; nr * nc];
        let f = Field { nr, nc, t_change: &[], r_head: &ones, ecc: &zeros, theta: &zeros, burnable: &burn,
                        cell_m: 1.0, slope: None };
        let out = propagate(&f, &eight(), None, &[(2, 2, 0.0)], None, 0.0, f64::INFINITY).unwrap();
        assert_eq!(out.arrival[2 * nc + 4], 2.0);
        assert!((out.arrival[4 * nc + 4] - 2.0 * 2f64.sqrt()).abs() < 1e-12);
        // a one-cell diagonal wall must not be crossed by a diagonal move
        let mut wall = burn.clone();
        wall[nc + 2] = false;
        wall[2 * nc + 1] = false;
        let f2 = Field { burnable: &wall, ..f };
        let out2 = propagate(&f2, &eight(), None, &[(2, 2, 0.0)], None, 0.0, f64::INFINITY).unwrap();
        assert!(out2.arrival[nc + 1] > 2f64.sqrt() + 1e-9);
        assert_eq!(out2.status[nc + 2], BARRIER);
    }

    #[test]
    fn ignition_on_barrier_is_an_error() {
        let ones = vec![1.0; 4];
        let zeros = vec![0.0; 4];
        let burn = vec![true, false, true, true];
        let f = Field { nr: 2, nc: 2, t_change: &[], r_head: &ones, ecc: &zeros, theta: &zeros, burnable: &burn,
                        cell_m: 1.0, slope: None };
        assert!(propagate(&f, &eight(), None, &[(0, 1, 0.0)], None, 0.0, 1.0).is_err());
    }
}
