//! Level-set time loop (oracle: `firepath.levelset.propagate_levelset`, order 5, narrow band,
//! geometric reinitialization, extension velocities, local Lax-Friedrichs, TVD-RK3, work window).
//! Initialization (phi0, first reinitialization) and the final status are done in Python.
//! Expressions follow the NumPy reference term by term; differences come only from libm vs NumPy
//! transcendental functions and from tie-breaking between equidistant interface points (the reference
//! uses a KD-tree, this uses a bucket grid with lowest-index tie-break).

use crate::graph::Field;

pub struct Params {
    pub dx: f64,
    pub cfl: f64,
    pub band: f64,
    pub reinit_every: usize,
}

const MARGIN: usize = 5; // WENO5 stencil radius 3 + 2, as in the reference

// ---------------------------------------------------------------------------- Hamiltonian

#[inline]
fn ham(px: f64, py: f64, a: f64, e: f64, wx: f64, wy: f64) -> f64 {
    let pw = px * wx + py * wy;
    let pp = -px * wy + py * wx;
    a * (e * pw + (pw * pw + (1.0 - e * e) * pp * pp).sqrt())
}

#[inline]
fn grad_ham(px: f64, py: f64, a: f64, e: f64, wx: f64, wy: f64) -> (f64, f64) {
    let pw = px * wx + py * wy;
    let pp = -px * wy + py * wx;
    let mut s = (pw * pw + (1.0 - e * e) * pp * pp).sqrt();
    if !(s > 0.0) {
        s = 1.0;
    }
    let hw = a * (e + pw / s);
    let hp = a * (1.0 - e * e) * pp / s;
    (hw * wx - hp * wy, hw * wy + hp * wx)
}

/// Per-cell Hamiltonian parameters (after extension), planar or slope-plane.
#[derive(Clone, Copy)]
struct Cell {
    a: f64,
    e: f64,
    w1: f64,
    w2: f64,
    slope: Option<(f64, f64, f64)>, // (cs, ux, uy)
}

impl Cell {
    #[inline]
    fn h(&self, px: f64, py: f64) -> f64 {
        match self.slope {
            None => ham(px, py, self.a, self.e, self.w1, self.w2),
            Some((cs, ux, uy)) => {
                let q1 = cs * (px * ux + py * uy);
                let q2 = -px * uy + py * ux;
                ham(q1, q2, self.a, self.e, self.w1, self.w2)
            }
        }
    }

    #[inline]
    fn dabs(&self, px: f64, py: f64) -> (f64, f64) {
        match self.slope {
            None => {
                let (gx, gy) = grad_ham(px, py, self.a, self.e, self.w1, self.w2);
                (gx.abs(), gy.abs())
            }
            Some((cs, ux, uy)) => {
                let q1 = cs * (px * ux + py * uy);
                let q2 = -px * uy + py * ux;
                let (g1, g2) = grad_ham(q1, q2, self.a, self.e, self.w1, self.w2);
                ((g1 * cs * ux - g2 * uy).abs(), (g1 * cs * uy + g2 * ux).abs())
            }
        }
    }
}

// ---------------------------------------------------------------------------- interface points

/// Zero crossings on grid edges and densified chord points, in global (row, col) coordinates.
/// Same construction and order as `_interface_points`.
fn interface_points(phi: &[f64], bar: &[bool], wr: usize, wc: usize, o0: usize, o1: usize) -> Vec<(f64, f64)> {
    let neg = |k: usize| phi[k] <= 0.0;
    let mut hx = vec![f64::NAN; wr * wc.saturating_sub(1)]; // (r, c) - (r, c+1)
    let mut vy = vec![f64::NAN; wr.saturating_sub(1) * wc]; // (r, c) - (r+1, c)
    let mut pts = Vec::new();
    for r in 0..wr {
        for c in 0..wc.saturating_sub(1) {
            let (k, k2) = (r * wc + c, r * wc + c + 1);
            if neg(k) != neg(k2) && !bar[k] && !bar[k2] {
                let (a, b) = (phi[k], phi[k2]);
                let f = a / (a - b);
                hx[r * (wc - 1) + c] = f;
                pts.push(((r + o0) as f64, (c + o1) as f64 + f));
            }
        }
    }
    for r in 0..wr.saturating_sub(1) {
        for c in 0..wc {
            let (k, k2) = (r * wc + c, (r + 1) * wc + c);
            if neg(k) != neg(k2) && !bar[k] && !bar[k2] {
                let (a, b) = (phi[k], phi[k2]);
                let f = a / (a - b);
                vy[r * wc + c] = f;
                pts.push(((r + o0) as f64 + f, (c + o1) as f64));
            }
        }
    }
    if wr < 2 || wc < 2 {
        return pts;
    }
    // squares with exactly two crossings: chord points at 0.25, 0.5, 0.75 (grouped by weight)
    let mut chords = Vec::new();
    for r in 0..wr - 1 {
        for c in 0..wc - 1 {
            let (rr, cc) = ((r + o0) as f64, (c + o1) as f64);
            let top = hx[r * (wc - 1) + c];
            let bot = hx[(r + 1) * (wc - 1) + c];
            let lef = vy[r * wc + c];
            let rig = vy[r * wc + c + 1];
            let cand = [(rr, cc + top), (rr + 1.0, cc + bot), (rr + lef, cc), (rr + rig, cc + 1.0)];
            let have = [top.is_finite(), bot.is_finite(), lef.is_finite(), rig.is_finite()];
            if have.iter().filter(|&&h| h).count() == 2 {
                let mut it = (0..4).filter(|&i| have[i]);
                let (i0, i1) = (it.next().unwrap(), it.next().unwrap());
                chords.push((cand[i0], cand[i1]));
            }
        }
    }
    for w in [0.25, 0.5, 0.75] {
        for &((y0, x0), (y1, x1)) in &chords {
            pts.push((y0 + w * (y1 - y0), x0 + w * (x1 - x0)));
        }
    }
    pts
}

/// Uniform bucket grid over integer cells for nearest-point queries.
struct Buckets {
    r0: i64,
    c0: i64,
    nr: i64,
    nc: i64,
    start: Vec<usize>,
    idx: Vec<usize>,
}

impl Buckets {
    fn new(pts: &[(f64, f64)]) -> Self {
        let (mut rmin, mut rmax, mut cmin, mut cmax) = (i64::MAX, i64::MIN, i64::MAX, i64::MIN);
        for &(r, c) in pts {
            let (ri, ci) = (r.floor() as i64, c.floor() as i64);
            rmin = rmin.min(ri);
            rmax = rmax.max(ri);
            cmin = cmin.min(ci);
            cmax = cmax.max(ci);
        }
        let (nr, nc) = (rmax - rmin + 1, cmax - cmin + 1);
        let mut count = vec![0usize; (nr * nc) as usize + 1];
        let key = |r: f64, c: f64| ((r.floor() as i64 - rmin) * nc + (c.floor() as i64 - cmin)) as usize;
        for &(r, c) in pts {
            count[key(r, c) + 1] += 1;
        }
        for i in 1..count.len() {
            count[i] += count[i - 1];
        }
        let start = count.clone();
        let mut fill = count;
        let mut idx = vec![0usize; pts.len()];
        for (j, &(r, c)) in pts.iter().enumerate() {
            let b = key(r, c);
            idx[fill[b]] = j;
            fill[b] += 1;
        }
        Buckets { r0: rmin, c0: cmin, nr, nc, start, idx }
    }

    /// Nearest point to (qr, qc) within `limit` (squared distance, index); ties -> lowest index.
    fn nearest(&self, pts: &[(f64, f64)], qr: f64, qc: f64, limit: f64) -> Option<(f64, usize)> {
        let (br, bc) = (qr.floor() as i64 - self.r0, qc.floor() as i64 - self.c0);
        // rings beyond the farthest bucket cannot contain points
        let ring_max = br.abs().max((br - self.nr + 1).abs()).max(bc.abs()).max((bc - self.nc + 1).abs()) + 1;
        let mut best: Option<(f64, usize)> = None;
        for ring in 0..=ring_max {
            // every point in ring k is at least (k - 1) cells away
            let lo = (ring - 1).max(0) as f64;
            if lo > limit || best.is_some_and(|(d2, _)| lo * lo > d2) {
                break;
            }
            let (rlo, rhi, clo, chi) = (br - ring, br + ring, bc - ring, bc + ring);
            for r in rlo.max(0)..=rhi.min(self.nr - 1) {
                let full_row = r == rlo || r == rhi;
                let cols: Vec<i64> = if full_row || clo == chi { (clo..=chi).collect() } else { vec![clo, chi] };
                for c in cols {
                    if c < 0 || c >= self.nc {
                        continue;
                    }
                    let b = (r * self.nc + c) as usize;
                    for &j in &self.idx[self.start[b]..self.start[b + 1]] {
                        let (dr, dc) = (qr - pts[j].0, qc - pts[j].1);
                        let d2 = dr * dr + dc * dc;
                        match best {
                            Some((bd, bj)) if d2 > bd || (d2 == bd && j > bj) => {}
                            _ => best = Some((d2, j)),
                        }
                    }
                }
            }
        }
        best.filter(|&(d2, _)| d2.sqrt() <= limit)
    }

    /// Cells of a (wr, wc) window at global offset (o0, o1) within Chebyshev distance `radius`
    /// of any non-empty bucket (a superset of the cells within Euclidean distance `radius` of a point).
    fn mark(&self, radius: i64, wr: usize, wc: usize, o0: usize, o1: usize) -> Vec<bool> {
        let mut m = vec![false; wr * wc];
        for br in 0..self.nr {
            for bc in 0..self.nc {
                let b = (br * self.nc + bc) as usize;
                if self.start[b] == self.start[b + 1] {
                    continue;
                }
                let (gr, gc) = (br + self.r0 - o0 as i64, bc + self.c0 - o1 as i64);
                for r in (gr - radius).max(0)..=(gr + radius + 1).min(wr as i64 - 1) {
                    for c in (gc - radius).max(0)..=(gc + radius + 1).min(wc as i64 - 1) {
                        m[r as usize * wc + c as usize] = true;
                    }
                }
            }
        }
        m
    }
}

/// Geometric reinitialization on the whole grid (`_redistance`).
fn redistance(phi: &mut [f64], bar: &[bool], nr: usize, nc: usize, p: &Params) {
    let pts = interface_points(phi, bar, nr, nc, 0, 0);
    let (lo, hi) = (-p.band * p.dx, p.band * p.dx);
    if pts.is_empty() {
        for v in phi.iter_mut() {
            *v = v.clamp(lo, hi);
        }
        return;
    }
    let bk = Buckets::new(&pts);
    // cells farther than band + 1 from every point get d = band, as in the reference (upper bound)
    let near = bk.mark(p.band.ceil() as i64 + 2, nr, nc, 0, 0);
    for r in 0..nr {
        for c in 0..nc {
            let k = r * nc + c;
            if bar[k] {
                phi[k] = phi[k].clamp(lo, hi.max(phi[k]));
                continue;
            }
            let d = if !near[k] {
                f64::INFINITY
            } else {
                match bk.nearest(&pts, r as f64, c as f64, p.band + 1.0) {
                    Some((d2, _)) => d2.sqrt(),
                    None => f64::INFINITY,
                }
            };
            let d = d.min(p.band) * p.dx;
            let v = if phi[k] <= 0.0 { -d } else { d };
            phi[k] = v.clamp(lo, hi);
        }
    }
}

// ---------------------------------------------------------------------------- derivatives

#[inline]
fn w5(v1: f64, v2: f64, v3: f64, v4: f64, v5: f64) -> f64 {
    let s1 = 13.0 / 12.0 * (v1 - 2.0 * v2 + v3).powi(2) + 0.25 * (v1 - 4.0 * v2 + 3.0 * v3).powi(2);
    let s2 = 13.0 / 12.0 * (v2 - 2.0 * v3 + v4).powi(2) + 0.25 * (v2 - v4).powi(2);
    let s3 = 13.0 / 12.0 * (v3 - 2.0 * v4 + v5).powi(2) + 0.25 * (3.0 * v3 - 4.0 * v4 + v5).powi(2);
    let eps = 1e-6 * (v1 * v1).max(v2 * v2).max(v3 * v3).max(v4 * v4).max(v5 * v5) + 1e-99;
    let a1 = 0.1 / (eps + s1).powi(2);
    let a2 = 0.6 / (eps + s2).powi(2);
    let a3 = 0.3 / (eps + s3).powi(2);
    let tot = a1 + a2 + a3;
    (a1 * (v1 / 3.0 - 7.0 * v2 / 6.0 + 11.0 * v3 / 6.0)
        + a2 * (-v2 / 6.0 + 5.0 * v3 / 6.0 + v4 / 3.0)
        + a3 * (v3 / 3.0 + 5.0 * v4 / 6.0 - v5 / 6.0))
        / tot
}

/// (xm, xp, ym, yp) per cell of a (wr, wc) window: WENO5 with edge replication, first-order
/// Neumann differences where a barrier is within the stencil (`near_x`, `near_y`).
#[allow(clippy::too_many_arguments)]
fn derivatives(ph: &[f64], bar: &[bool], nx: &[bool], ny: &[bool], wr: usize, wc: usize, dx: f64,
               out: &mut [[f64; 4]]) {
    let at = |r: i64, c: i64| -> f64 {
        let rr = r.clamp(0, wr as i64 - 1) as usize;
        let cc = c.clamp(0, wc as i64 - 1) as usize;
        ph[rr * wc + cc]
    };
    for r in 0..wr {
        for c in 0..wc {
            let k = r * wc + c;
            let (ri, ci) = (r as i64, c as i64);
            let p0 = ph[k];
            // first-order Neumann (ghost = own value across barrier faces; grid edge replicated)
            let nb = |rr: i64, cc: i64| -> f64 {
                if rr < 0 || rr >= wr as i64 || cc < 0 || cc >= wc as i64 {
                    at(rr, cc)
                } else if bar[rr as usize * wc + cc as usize] {
                    p0
                } else {
                    ph[rr as usize * wc + cc as usize]
                }
            };
            let (left, right, up, down) = (nb(ri, ci - 1), nb(ri, ci + 1), nb(ri - 1, ci), nb(ri + 1, ci));
            let (fxm, fxp) = ((p0 - left) / dx, (right - p0) / dx);
            let (fym, fyp) = (-(down - p0) / dx, -(p0 - up) / dx);
            let (xm, xp) = if nx[k] {
                (fxm, fxp)
            } else {
                let d = |j: i64| (at(ri, ci + j + 1) - at(ri, ci + j)) / dx;
                (w5(d(-3), d(-2), d(-1), d(0), d(1)), w5(d(2), d(1), d(0), d(-1), d(-2)))
            };
            let (ym, yp) = if ny[k] {
                (fym, fyp)
            } else {
                let d = |j: i64| (at(ri + j + 1, ci) - at(ri + j, ci)) / dx;
                let (rm, rp) = (w5(d(-3), d(-2), d(-1), d(0), d(1)), w5(d(2), d(1), d(0), d(-1), d(-2)));
                (-rp, -rm)
            };
            out[k] = [xm, xp, ym, yp];
        }
    }
}

// ---------------------------------------------------------------------------- time loop

/// Advances `phi` and fills `arrival` (minutes) from t_start to t_stop. `barrier`, `near_x`, `near_y`
/// as in the reference; `phi` must already be initialized and reinitialized.
#[allow(clippy::too_many_arguments)]
pub fn run(f: &Field, p: &Params, near_x: &[bool], near_y: &[bool], phi: &mut [f64], arrival: &mut [f64],
           t_start: f64, t_stop: f64) {
    let (nr, nc) = (f.nr, f.nc);
    let n = nr * nc;
    let bar: Vec<bool> = f.burnable.iter().map(|b| !b).collect();
    let mut frozen = bar.clone();
    let mut t = t_start;
    let mut step = 0usize;
    let band_lim = (p.band - 0.5) * p.dx;
    let reinit = p.reinit_every > 0;
    loop {
        if !(t < t_stop) || !(0..n).any(|k| !arrival[k].is_finite() && !bar[k]) {
            break;
        }
        let h = f.t_change.partition_point(|&s| t >= s);
        let end = if h < f.t_change.len() { f.t_change[h] } else { f64::INFINITY };
        // window
        let (mut rmin, mut rmax, mut cmin, mut cmax) = (usize::MAX, 0usize, usize::MAX, 0usize);
        for r in 0..nr {
            for c in 0..nc {
                let k = r * nc + c;
                let live = !frozen[k] || (reinit && phi[k].abs() < band_lim && !bar[k]);
                if live {
                    rmin = rmin.min(r);
                    rmax = rmax.max(r);
                    cmin = cmin.min(c);
                    cmax = cmax.max(c);
                }
            }
        }
        if rmin == usize::MAX {
            break;
        }
        let r0 = rmin.saturating_sub(MARGIN) / 2 * 2;
        let c0 = cmin.saturating_sub(MARGIN) / 2 * 2;
        let (r1, c1) = ((rmax + MARGIN + 1).min(nr), (cmax + MARGIN + 1).min(nc));
        let (wr, wc) = (r1 - r0, c1 - c0);
        let wn = wr * wc;
        let gk = |i: usize| (r0 + i / wc) * nc + c0 + i % wc;
        let ph_w: Vec<f64> = (0..wn).map(|i| phi[gk(i)]).collect();
        let bar_w: Vec<bool> = (0..wn).map(|i| bar[gk(i)]).collect();
        // extension: each cell takes the parameters of the cell holding its nearest interface point
        let pts = interface_points(&ph_w, &bar_w, wr, wc, r0, c0);
        let src: Vec<usize> = if pts.is_empty() {
            (0..wn).collect()
        } else {
            let bk = Buckets::new(&pts);
            // only cells near the front need their parameters extended: active cells and their
            // neighbours lie within band + 1.5 of the interface; elsewhere the values are masked
            let near = bk.mark(p.band.ceil() as i64 + 3, wr, wc, r0, c0);
            (0..wn)
                .map(|i| {
                    if bar_w[i] || !near[i] {
                        return i;
                    }
                    let (qr, qc) = ((r0 + i / wc) as f64, (c0 + i % wc) as f64);
                    let (_, j) = bk.nearest(&pts, qr, qc, f64::INFINITY).unwrap();
                    let cr = ((pts[j].0.round_ties_even() as i64) - r0 as i64).clamp(0, wr as i64 - 1) as usize;
                    let cc = ((pts[j].1.round_ties_even() as i64) - c0 as i64).clamp(0, wc as i64 - 1) as usize;
                    cr * wc + cc
                })
                .collect()
        };
        let base = h * n;
        let cells: Vec<Cell> = (0..wn)
            .map(|i| {
                let g = gk(src[i]);
                let a = f.r_head[base + g] / (1.0 + f.ecc[base + g]);
                let e = f.ecc[base + g];
                let th = f.theta[base + g];
                let (wx, wy) = (th.cos(), th.sin());
                match f.slope {
                    None => Cell { a, e, w1: wx, w2: wy, slope: None },
                    Some((cs, ux, uy)) => {
                        let (cs, ux, uy) = (cs[g], ux[g], uy[g]);
                        let t2 = wy.atan2(wx);
                        let (dx, dy) = (t2.cos(), t2.sin());
                        let (w1, w2) = ((dx * ux + dy * uy) / cs, -dx * uy + dy * ux);
                        let nn = w1.hypot(w2);
                        Cell { a, e, w1: w1 / nn, w2: w2 / nn, slope: Some((cs, ux, uy)) }
                    }
                }
            })
            .collect();
        // LF bounds: half extents along x and y, neighbour max (edge replicated), masked by old frozen
        let ex: Vec<f64> = cells.iter().map(|c| c.h(1.0, 0.0).max(c.h(-1.0, 0.0))).collect();
        let ey: Vec<f64> = cells.iter().map(|c| c.h(0.0, 1.0).max(c.h(0.0, -1.0))).collect();
        let mut ax = vec![0.0; wn];
        let mut ay = vec![0.0; wn];
        let mut amax = 0.0f64;
        for r in 0..wr {
            for c in 0..wc {
                let i = r * wc + c;
                let l = r * wc + c.saturating_sub(1);
                let rr = r * wc + (c + 1).min(wc - 1);
                let u = r.saturating_sub(1) * wc + c;
                let d = (r + 1).min(wr - 1) * wc + c;
                let fz = frozen[gk(i)];
                ax[i] = if fz { 0.0 } else { ex[i].max(ex[l]).max(ex[rr]) };
                ay[i] = if fz { 0.0 } else { ey[i].max(ey[u]).max(ey[d]) };
                amax = amax.max(ax[i] + ay[i]);
            }
        }
        if amax == 0.0 {
            break;
        }
        let mut dt = p.cfl * p.dx / amax;
        dt = dt.min(end - t).min(t_stop - t);
        if dt <= 0.0 {
            t = end;
            continue;
        }
        if reinit {
            for k in 0..n {
                frozen[k] = bar[k] || !(phi[k].abs() < band_lim);
            }
        } else {
            frozen.copy_from_slice(&bar);
        }
        let fr_w: Vec<bool> = (0..wn).map(|i| frozen[gk(i)]).collect();
        let nx_w: Vec<bool> = (0..wn).map(|i| near_x[gk(i)]).collect();
        let ny_w: Vec<bool> = (0..wn).map(|i| near_y[gk(i)]).collect();
        let mut der = vec![[0.0f64; 4]; wn];
        let mut rhs = |ph: &[f64], out: &mut [f64]| {
            derivatives(ph, &bar_w, &nx_w, &ny_w, wr, wc, p.dx, &mut der);
            for i in 0..wn {
                if fr_w[i] {
                    out[i] = 0.0;
                    continue;
                }
                let [xm, xp, ym, yp] = der[i];
                let c = &cells[i];
                let (px, py) = (0.5 * (xm + xp), 0.5 * (ym + yp));
                let hm = c.h(px, py);
                let (mut cx, mut cy) = (0.0f64, 0.0f64);
                for gx in [xm, xp] {
                    for gy in [ym, yp] {
                        let (hx, hy) = c.dabs(gx, gy);
                        cx = cx.max(hx);
                        cy = cy.max(hy);
                    }
                }
                cx = cx.min(ax[i]);
                cy = cy.min(ay[i]);
                let diss = cx * 0.5 * (xp - xm) + cy * 0.5 * (yp - ym);
                out[i] = -(hm - diss);
            }
        };
        let mut k1 = vec![0.0; wn];
        rhs(&ph_w, &mut k1);
        let p1: Vec<f64> = (0..wn).map(|i| ph_w[i] + dt * k1[i]).collect();
        rhs(&p1, &mut k1);
        let p2: Vec<f64> = (0..wn).map(|i| 0.75 * ph_w[i] + 0.25 * (p1[i] + dt * k1[i])).collect();
        rhs(&p2, &mut k1);
        for i in 0..wn {
            let new = ph_w[i] / 3.0 + 2.0 / 3.0 * (p2[i] + dt * k1[i]);
            let g = gk(i);
            if ph_w[i] > 0.0 && new <= 0.0 && !arrival[g].is_finite() {
                arrival[g] = t + dt * (ph_w[i] / (ph_w[i] - new));
            }
            phi[g] = new;
        }
        t += dt;
        step += 1;
        if reinit && step % p.reinit_every == 0 {
            redistance(phi, &bar, nr, nc, p);
        }
    }
}
