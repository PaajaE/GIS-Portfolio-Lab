//! Terrain kernels for the landslide susceptibility predictors (PLAN §10).
//!
//! * `terrain3x3`: one pass over 3 x 3 windows -> slope (Horn 1981), northness / eastness of the downslope
//!   direction, profile and plan curvature (Zevenbergen & Thorne 1987 coefficients), TRI (Riley et al. 1999).
//! * `window_stats`: square (2r+1) x (2r+1) windows -> mean, standard deviation (sliding sums in f64 on
//!   mean-centred values), min and max (van Herk / Gil-Werman, O(1) per cell).
//!
//! Semantics shared by both kernels (strict): a cell gets `nodata` if any cell of its window is nodata
//! (or non-finite) or if the window extends past the grid. Rows are north-up (row 0 = north), so `y`
//! increases northward and the row index increases southward. Single-threaded and deterministic.

#[cfg(feature = "python")]
mod python;

/// Outputs of [`terrain3x3`], each `h * w`, row-major.
pub struct Terrain {
    pub slope_deg: Vec<f32>,
    pub northness: Vec<f32>,
    pub eastness: Vec<f32>,
    /// Second derivative of z along the gradient direction (1/m); > 0 = concave (slope flattens downhill).
    pub profile_curv: Vec<f32>,
    /// Second derivative of z along the contour direction (1/m); > 0 = convergent (hollow).
    pub plan_curv: Vec<f32>,
    pub tri: Vec<f32>,
}

#[inline]
fn bad(v: f32, nodata: f32) -> bool {
    v == nodata || !v.is_finite()
}

/// Gradient below this magnitude (dimensionless) counts as flat: aspect and curvature directions are
/// undefined there, so northness = eastness = profile = plan = 0.
pub const FLAT_GRADIENT: f64 = 1e-9;

pub fn terrain3x3(z: &[f32], h: usize, w: usize, cell: f64, nodata: f32) -> Terrain {
    let n = h * w;
    let mut t = Terrain {
        slope_deg: vec![nodata; n],
        northness: vec![nodata; n],
        eastness: vec![nodata; n],
        profile_curv: vec![nodata; n],
        plan_curv: vec![nodata; n],
        tri: vec![nodata; n],
    };
    if h < 3 || w < 3 {
        return t;
    }
    let l2 = cell * cell;
    for i in 1..h - 1 {
        'cells: for j in 1..w - 1 {
            // z1 z2 z3 / z4 z5 z6 / z7 z8 z9, z1 = north-west
            let mut v = [0f64; 9];
            for (k, (di, dj)) in [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)]
                .iter()
                .enumerate()
            {
                let x = z[(i + di - 1) * w + (j + dj - 1)];
                if bad(x, nodata) {
                    continue 'cells;
                }
                v[k] = x as f64;
            }
            let [z1, z2, z3, z4, z5, z6, z7, z8, z9] = v;
            // Horn: dz/dx (east) and dz/dy (north)
            let p = ((z3 + 2.0 * z6 + z9) - (z1 + 2.0 * z4 + z7)) / (8.0 * cell);
            let q = ((z1 + 2.0 * z2 + z3) - (z7 + 2.0 * z8 + z9)) / (8.0 * cell);
            let g = (p * p + q * q).sqrt();
            // Zevenbergen-Thorne second-order coefficients (z_xx = 2D, z_yy = 2E, z_xy = F) and
            // first-order G = dz/dx, H = dz/dy used for the curvature directions
            let zxx = ((z4 + z6) / 2.0 - z5) * 2.0 / l2;
            let zyy = ((z2 + z8) / 2.0 - z5) * 2.0 / l2;
            let zxy = (-z1 + z3 + z7 - z9) / (4.0 * l2);
            let gx = (z6 - z4) / (2.0 * cell);
            let gy = (z2 - z8) / (2.0 * cell);
            let g2 = gx * gx + gy * gy;
            let idx = i * w + j;
            t.slope_deg[idx] = g.atan().to_degrees() as f32;
            if g > FLAT_GRADIENT {
                t.eastness[idx] = (-p / g) as f32;
                t.northness[idx] = (-q / g) as f32;
            } else {
                t.eastness[idx] = 0.0;
                t.northness[idx] = 0.0;
            }
            if g2.sqrt() > FLAT_GRADIENT {
                t.profile_curv[idx] = ((zxx * gx * gx + 2.0 * zxy * gx * gy + zyy * gy * gy) / g2) as f32;
                t.plan_curv[idx] = ((zxx * gy * gy - 2.0 * zxy * gx * gy + zyy * gx * gx) / g2) as f32;
            } else {
                t.profile_curv[idx] = 0.0;
                t.plan_curv[idx] = 0.0;
            }
            let tri: f64 = [z1, z2, z3, z4, z6, z7, z8, z9].iter().map(|x| (x - z5) * (x - z5)).sum();
            t.tri[idx] = tri.sqrt() as f32;
        }
    }
    t
}

/// Outputs of [`window_stats`], each `h * w`, row-major.
pub struct WindowStats {
    pub mean: Vec<f32>,
    pub sd: Vec<f32>,
    pub min: Vec<f32>,
    pub max: Vec<f32>,
}

/// van Herk / Gil-Werman sliding min or max over windows of length k; `out[s]` = op over a[s..s+k].
fn vhgw(a: &[f32], k: usize, is_max: bool, g: &mut Vec<f32>, hbuf: &mut Vec<f32>, out: &mut Vec<f32>) {
    let n = a.len();
    let op = |x: f32, y: f32| if is_max { x.max(y) } else { x.min(y) };
    g.clear();
    g.resize(n, 0.0);
    hbuf.clear();
    hbuf.resize(n, 0.0);
    for i in 0..n {
        g[i] = if i % k == 0 { a[i] } else { op(g[i - 1], a[i]) };
    }
    for i in (0..n).rev() {
        hbuf[i] = if i % k == k - 1 || i == n - 1 { a[i] } else { op(hbuf[i + 1], a[i]) };
    }
    out.clear();
    for s in 0..=n - k {
        out.push(op(hbuf[s], g[s + k - 1]));
    }
}

pub fn window_stats(x: &[f32], h: usize, w: usize, r: usize, nodata: f32) -> WindowStats {
    let n = h * w;
    let mut out = WindowStats {
        mean: vec![nodata; n],
        sd: vec![nodata; n],
        min: vec![nodata; n],
        max: vec![nodata; n],
    };
    let k = 2 * r + 1;
    if h < k || w < k {
        return out;
    }
    // centre on the mean of valid values (sequential f64 sum: deterministic) to limit cancellation
    let (mut s, mut c) = (0f64, 0usize);
    for &v in x {
        if !bad(v, nodata) {
            s += v as f64;
            c += 1;
        }
    }
    if c == 0 {
        return out;
    }
    let off = s / c as f64;
    // nodata replaced by 0 for min/max (those windows are masked by the nodata count anyway)
    let mut clean = vec![0f32; n];
    for (c, &v) in clean.iter_mut().zip(x) {
        if !bad(v, nodata) {
            *c = v;
        }
    }
    // min / max: row pass then column pass
    let wo = w - k + 1;
    let ho = h - k + 1;
    let mut rowmin = vec![0f32; h * wo];
    let mut rowmax = vec![0f32; h * wo];
    let (mut g, mut hb, mut o) = (Vec::new(), Vec::new(), Vec::new());
    for i in 0..h {
        let row = &clean[i * w..(i + 1) * w];
        vhgw(row, k, false, &mut g, &mut hb, &mut o);
        rowmin[i * wo..(i + 1) * wo].copy_from_slice(&o);
        vhgw(row, k, true, &mut g, &mut hb, &mut o);
        rowmax[i * wo..(i + 1) * wo].copy_from_slice(&o);
    }
    let mut col = vec![0f32; h];
    let (mut cmin, mut cmax) = (Vec::new(), Vec::new());
    for jo in 0..wo {
        for i in 0..h {
            col[i] = rowmin[i * wo + jo];
        }
        vhgw(&col, k, false, &mut g, &mut hb, &mut cmin);
        for i in 0..h {
            col[i] = rowmax[i * wo + jo];
        }
        vhgw(&col, k, true, &mut g, &mut hb, &mut cmax);
        for io in 0..ho {
            let idx = (io + r) * w + jo + r;
            out.min[idx] = cmin[io];
            out.max[idx] = cmax[io];
        }
    }
    // mean / sd: sliding sums of mean-centred values. Column sums over the current k-row band are
    // updated by adding the entering row and subtracting the leaving one; each output row then slides
    // along the columns. Rounding error scales with window sums, not grid totals (unlike summed-area
    // tables, which lost ~1e-3 m in sd on 8192^2 grids). Nodata counts are exact integers.
    let mut cs = vec![0f64; w];
    let mut cq = vec![0f64; w];
    let mut cn = vec![0u32; w];
    let add_row = |i: usize, sign: f64, cs: &mut Vec<f64>, cq: &mut Vec<f64>, cn: &mut Vec<u32>| {
        for j in 0..w {
            let v = x[i * w + j];
            if bad(v, nodata) {
                if sign > 0.0 { cn[j] += 1 } else { cn[j] -= 1 }
            } else {
                let d = v as f64 - off;
                cs[j] += sign * d;
                cq[j] += sign * d * d;
            }
        }
    };
    for i in 0..k {
        add_row(i, 1.0, &mut cs, &mut cq, &mut cn);
    }
    let kk = (k * k) as f64;
    for io in 0..ho {
        if io > 0 {
            add_row(io - 1, -1.0, &mut cs, &mut cq, &mut cn);
            add_row(io + k - 1, 1.0, &mut cs, &mut cq, &mut cn);
        }
        let (mut s, mut q, mut nb) = (0f64, 0f64, 0u32);
        for j in 0..k {
            s += cs[j];
            q += cq[j];
            nb += cn[j];
        }
        for jo in 0..wo {
            if jo > 0 {
                s += cs[jo + k - 1] - cs[jo - 1];
                q += cq[jo + k - 1] - cq[jo - 1];
                nb = nb + cn[jo + k - 1] - cn[jo - 1];
            }
            let idx = (io + r) * w + jo + r;
            if nb > 0 {
                out.min[idx] = nodata;
                out.max[idx] = nodata;
                continue;
            }
            let m = s / kk;
            out.mean[idx] = (m + off) as f32;
            out.sd[idx] = (q / kk - m * m).max(0.0).sqrt() as f32;
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    const ND: f32 = -9999.0;

    /// Deterministic pseudo-random field (LCG), values in [lo, lo + span).
    fn field(h: usize, w: usize, seed: u64, lo: f32, span: f32) -> Vec<f32> {
        let mut s = seed;
        (0..h * w)
            .map(|_| {
                s = s.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
                lo + span * ((s >> 33) as f32 / (1u64 << 31) as f32)
            })
            .collect()
    }

    fn brute(x: &[f32], h: usize, w: usize, r: usize, i: usize, j: usize) -> Option<(f64, f64, f32, f32)> {
        if i < r || j < r || i + r >= h || j + r >= w {
            return None;
        }
        let mut v = Vec::new();
        for a in i - r..=i + r {
            for b in j - r..=j + r {
                let t = x[a * w + b];
                if bad(t, ND) {
                    return None;
                }
                v.push(t);
            }
        }
        let n = v.len() as f64;
        let m = v.iter().map(|&t| t as f64).sum::<f64>() / n;
        let var = v.iter().map(|&t| (t as f64 - m).powi(2)).sum::<f64>() / n;
        let mn = v.iter().cloned().fold(f32::INFINITY, f32::min);
        let mx = v.iter().cloned().fold(f32::NEG_INFINITY, f32::max);
        Some((m, var.sqrt(), mn, mx))
    }

    #[test]
    fn window_stats_match_brute_force_with_holes_and_edges() {
        for &(h, w, r, seed) in &[(17, 23, 1, 1u64), (31, 19, 3, 2), (40, 40, 5, 3), (12, 12, 5, 4), (9, 30, 4, 5)] {
            let mut x = field(h, w, seed, 400.0, 1600.0);
            x[(h / 2) * w + w / 3] = ND;
            x[w + 1] = f32::NAN;
            let s = window_stats(&x, h, w, r, ND);
            for i in 0..h {
                for j in 0..w {
                    let idx = i * w + j;
                    match brute(&x, h, w, r, i, j) {
                        None => {
                            assert_eq!(s.mean[idx], ND);
                            assert_eq!(s.max[idx], ND);
                        }
                        Some((m, sd, mn, mx)) => {
                            assert!((s.mean[idx] as f64 - m).abs() < 1e-3, "mean {} vs {}", s.mean[idx], m);
                            assert!((s.sd[idx] as f64 - sd).abs() < 1e-3);
                            assert_eq!(s.min[idx], mn);
                            assert_eq!(s.max[idx], mx);
                        }
                    }
                }
            }
        }
    }

    #[test]
    fn window_stats_degenerate_inputs() {
        let s = window_stats(&[], 0, 0, 1, ND);
        assert!(s.mean.is_empty());
        let s = window_stats(&[5.0], 1, 1, 0, ND);
        assert_eq!((s.mean[0], s.sd[0], s.min[0], s.max[0]), (5.0, 0.0, 5.0, 5.0));
        let s = window_stats(&[5.0; 4], 2, 2, 1, ND); // window larger than grid
        assert!(s.mean.iter().all(|&v| v == ND));
        let s = window_stats(&[ND; 25], 5, 5, 1, ND); // all nodata
        assert!(s.max.iter().all(|&v| v == ND));
        let s = window_stats(&[7.0; 25], 5, 5, 1, ND); // flat, ties
        assert_eq!((s.mean[12], s.sd[12], s.min[12], s.max[12]), (7.0, 0.0, 7.0, 7.0));
    }

    #[test]
    fn terrain_plane_is_exact() {
        // z = 0.3 x - 0.4 y (x east, y north), cell 5 m: gradient 0.5, downslope towards west-north-west
        let (h, w, c) = (6, 7, 5.0);
        let z: Vec<f32> = (0..h * w)
            .map(|k| {
                let (i, j) = (k / w, k % w);
                (100.0 + 0.3 * (j as f64 * c) - 0.4 * (-(i as f64) * c)) as f32
            })
            .collect();
        let t = terrain3x3(&z, h, w, c, ND);
        let idx = 2 * w + 3;
        assert!((t.slope_deg[idx] as f64 - 0.5f64.atan().to_degrees()).abs() < 1e-4);
        assert!((t.eastness[idx] - (-0.6)).abs() < 1e-5 && (t.northness[idx] - 0.8).abs() < 1e-5);
        assert!(t.profile_curv[idx].abs() < 1e-6 && t.plan_curv[idx].abs() < 1e-6);
        // edges are nodata
        assert_eq!(t.slope_deg[0], ND);
        assert_eq!(t.tri[w - 1], ND);
    }

    #[test]
    fn terrain_curvature_signs() {
        // valley along y: z = 0.05 x^2 + 0.2 y -> contour concave up (convergent), z_xx = 0.1
        let (h, w, c) = (7, 7, 5.0);
        let z: Vec<f32> = (0..h * w)
            .map(|k| {
                let x = (k % w) as f64 * c - 15.0;
                let y = -((k / w) as f64) * c;
                (500.0 + 0.05 * x * x + 0.2 * y) as f32
            })
            .collect();
        let t = terrain3x3(&z, h, w, c, ND);
        let idx = 3 * w + 3; // valley axis x = 0: gradient along y only
        assert!((t.plan_curv[idx] - 0.1).abs() < 1e-4, "plan {}", t.plan_curv[idx]);
        assert!(t.profile_curv[idx].abs() < 1e-4);
    }

    #[test]
    fn terrain_flat_and_nodata() {
        let mut z = vec![10.0f32; 25];
        let t = terrain3x3(&z, 5, 5, 5.0, ND);
        assert_eq!((t.slope_deg[12], t.northness[12], t.plan_curv[12], t.tri[12]), (0.0, 0.0, 0.0, 0.0));
        z[6] = ND;
        let t = terrain3x3(&z, 5, 5, 5.0, ND);
        assert_eq!(t.slope_deg[12], ND); // (1,1) is in the window of (2,2)
        assert_eq!(t.slope_deg[18], 0.0); // (3,3) is not affected
        let t = terrain3x3(&[1.0, 2.0], 1, 2, 5.0, ND);
        assert!(t.slope_deg.iter().all(|&v| v == ND));
    }
}
