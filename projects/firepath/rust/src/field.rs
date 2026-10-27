//! Spread-field builder (oracle: `firepath.field.hour`): per burnable cell and hour, head ROS, ellipse
//! eccentricity and max-spread direction from Rothermel/SB40 static terms, terrain and 10 m wind.
//! Expressions follow the NumPy reference term by term; differences come only from libm vs NumPy
//! transcendental functions (tested within 1e-12 relative).
//! Measured reason (PLAN §8 revision 5): in calibration the NumPy builder cost as much as the G8 run
//! (16-25 s per Mangum evaluation at 90 m) and its temporaries multiply memory per thread.

const FT_PER_M: f64 = 3.280839895;
const MS_TO_FTMIN: f64 = FT_PER_M * 60.0;
const U10_TO_U20: f64 = 1.0 / 1.15;

/// Per-cell static inputs (all of length n = nr * nc, row-major).
pub struct Static<'a> {
    pub r0: &'a [f64],
    pub sigma: &'a [f64],
    pub beta: &'a [f64],
    pub beta_op: &'a [f64],
    pub waf: &'a [f64],
    pub tan_slope: &'a [f64],
    pub upslope: &'a [f64],
    pub timber: &'a [bool],
    pub burnable: &'a [bool],
}

pub struct Params {
    pub k: f64,
    pub a_u: f64,
    pub a_s: f64,
    pub g: f64,
    pub wind_factor: f64,
}

fn lb_anderson_ms(u: f64) -> f64 {
    (0.936 * (0.2566 * u).exp() + 0.461 * (-0.1548 * u).exp() - 0.397).min(8.0)
}

/// Fills r, e, t (each hours * n) for wind u, v (hours * n, grid-relative, m/s). Non-burnable cells get 0.
pub fn build(st: &Static, p: &Params, u: &[f64], v: &[f64], r: &mut [f64], e: &mut [f64], t: &mut [f64]) {
    let n = st.burnable.len();
    let hours = u.len() / n;
    for i in 0..n {
        if !st.burnable[i] {
            for h in 0..hours {
                r[h * n + i] = 0.0;
                e[h * n + i] = 0.0;
                t[h * n + i] = 0.0;
            }
            continue;
        }
        let (sig, beta, bop) = (st.sigma[i], st.beta[i], st.beta_op[i]);
        let ratio = beta / bop;
        let c = 7.47 * (-0.133 * sig.powf(0.55)).exp();
        let bb = 0.02526 * sig.powf(0.54);
        let ee = 0.715 * (-3.59e-4 * sig).exp();
        let ts = st.tan_slope[i];
        let cs = 1.0 / (1.0 + ts * ts).sqrt();
        let (ux, uy) = (st.upslope[i].cos(), st.upslope[i].sin());
        let phi_s = p.a_s * 5.275 * beta.powf(-0.3) * ts * ts;
        let mut r0 = p.k * st.r0[i];
        if p.g != 1.0 && st.timber[i] {
            r0 *= p.g;
        }
        let ratio_m_ee = ratio.powf(-ee);
        let ratio_ee = ratio.powf(ee);
        for h in 0..hours {
            let j = h * n + i;
            let (uu, vv) = (u[j], v[j]);
            let w1 = cs * (uu * ux + vv * uy);
            let w2 = -uu * uy + vv * ux;
            let speed_plane = w1.hypot(w2);
            let u_mid = p.wind_factor * p.a_u * U10_TO_U20 * speed_plane * st.waf[i] * MS_TO_FTMIN;
            let phi_w = if u_mid > 0.0 { c * u_mid.powf(bb) * ratio_m_ee } else { 0.0 };
            let (dw1, dw2) = if speed_plane > 0.0 { (w1 / speed_plane, w2 / speed_plane) } else { (0.0, 0.0) };
            let e1 = phi_w * dw1 + phi_s;
            let e2 = phi_w * dw2;
            let phi_e = e1.hypot(e2);
            let u_e = if phi_e > 0.0 { (phi_e * ratio_ee / c).powf(1.0 / bb) } else { 0.0 };
            let mut r_head = r0 * (1.0 + phi_e);
            if u_e > 0.0 {
                r_head = r_head.min((u_e / FT_PER_M).max(r0));
            }
            let lb = lb_anderson_ms(u_e / MS_TO_FTMIN);
            let (d1, d2) = if phi_e > 0.0 { (e1, e2) } else { (1.0, 0.0) };
            let hx = d1 * cs * ux - d2 * uy;
            let hy = d1 * cs * uy + d2 * ux;
            r[j] = r_head;
            e[j] = (1.0 - 1.0 / (lb * lb)).sqrt();
            t[j] = hy.atan2(hx);
        }
    }
}
