//! Per-parcel morphological opening + connected components in one raster pass.
//!
//! Semantics match `parcel_intel.patches.screen_patches_reference` exactly
//! (integer outputs, no tolerance):
//! - `parcel[i] == 0` means no parcel; cells of different parcels never interact.
//! - Opening by a k x k square: a cell survives iff some k x k square that is fully
//!   feasible and fully inside the cell's own parcel contains it. Cells outside the
//!   raster count as infeasible. k = 1 is the identity.
//! - Components use 4- or 8-connectivity within one parcel.
//! - Largest-component ties go to the component whose first cell (row-major) is first.
//!
//! The algorithm is single-threaded and deterministic.

#[cfg(feature = "python")]
mod python;

pub struct PatchStats {
    pub feasible_cells: Vec<i64>,
    pub largest_cells: Vec<i64>,
    pub n_patches: Vec<i64>,
    /// 0 = not feasible, 1 = feasible after opening, 2 = largest patch of its parcel.
    pub mask: Vec<u8>,
}

/// Erosion by a k x k square, separable: horizontal runs, then vertical runs of
/// horizontally-eroded cells of the same parcel.
fn erode(parcel: &[i32], feasible: &[bool], h: usize, w: usize, r: usize) -> Vec<bool> {
    let k = 2 * r + 1;
    let mut row_ok = vec![false; h * w];
    for y in 0..h {
        let row = y * w;
        let mut x = 0;
        while x < w {
            let p = parcel[row + x];
            if p == 0 || !feasible[row + x] {
                x += 1;
                continue;
            }
            let start = x;
            while x < w && parcel[row + x] == p && feasible[row + x] {
                x += 1;
            }
            // run [start, x): centres with a full window inside the run
            if x - start >= k {
                for c in start + r..x - r {
                    row_ok[row + c] = true;
                }
            }
        }
    }
    let mut out = vec![false; h * w];
    for x in 0..w {
        let mut y = 0;
        while y < h {
            let i = y * w + x;
            if !row_ok[i] {
                y += 1;
                continue;
            }
            let p = parcel[i];
            let start = y;
            while y < h && row_ok[y * w + x] && parcel[y * w + x] == p {
                y += 1;
            }
            if y - start >= k {
                for c in start + r..y - r {
                    out[c * w + x] = true;
                }
            }
        }
    }
    out
}

/// Dilation by a k x k square, separable. Exact for a symmetric square; any cell
/// reached lies inside the full window of an eroded cell, hence in the same parcel.
fn dilate(src: &[bool], h: usize, w: usize, r: usize) -> Vec<bool> {
    let mut tmp = vec![false; h * w];
    for y in 0..h {
        let row = y * w;
        // distance-based sweep: mark [x - r, x + r] for each set x
        let mut last: Option<usize> = None;
        for x in 0..w {
            if src[row + x] {
                last = Some(x);
            }
            if let Some(l) = last {
                if x - l <= r {
                    tmp[row + x] = true;
                }
            }
        }
        let mut next: Option<usize> = None;
        for x in (0..w).rev() {
            if src[row + x] {
                next = Some(x);
            }
            if let Some(n) = next {
                if n - x <= r {
                    tmp[row + x] = true;
                }
            }
        }
    }
    let mut out = vec![false; h * w];
    for x in 0..w {
        let mut last: Option<usize> = None;
        for y in 0..h {
            if tmp[y * w + x] {
                last = Some(y);
            }
            if let Some(l) = last {
                if y - l <= r {
                    out[y * w + x] = true;
                }
            }
        }
        let mut next: Option<usize> = None;
        for y in (0..h).rev() {
            if tmp[y * w + x] {
                next = Some(y);
            }
            if let Some(n) = next {
                if n - y <= r {
                    out[y * w + x] = true;
                }
            }
        }
    }
    out
}

fn find(parent: &mut [u32], mut i: u32) -> u32 {
    while parent[i as usize] != i {
        let p = parent[i as usize];
        parent[i as usize] = parent[p as usize]; // path halving
        i = p;
    }
    i
}

/// Union keeping the smaller index as root, so a root is its component's first cell.
fn union(parent: &mut [u32], a: u32, b: u32) {
    let ra = find(parent, a);
    let rb = find(parent, b);
    if ra < rb {
        parent[rb as usize] = ra;
    } else if rb < ra {
        parent[ra as usize] = rb;
    }
}

pub fn screen_patches(
    parcel: &[i32],
    feasible: &[bool],
    h: usize,
    w: usize,
    n_parcels: usize,
    open_size: usize,
    connectivity: u8,
    min_cells: i64,
) -> Result<PatchStats, String> {
    if parcel.len() != h * w || feasible.len() != h * w {
        return Err("parcel and feasible must have h * w cells".into());
    }
    if open_size == 0 || open_size % 2 == 0 {
        return Err("open_size must be a positive odd integer".into());
    }
    if connectivity != 4 && connectivity != 8 {
        return Err("connectivity must be 4 or 8".into());
    }
    if h * w >= u32::MAX as usize {
        return Err("raster too large for u32 cell indices".into());
    }
    for &p in parcel {
        if p < 0 || p as usize > n_parcels {
            return Err(format!("parcel index {p} outside 0..={n_parcels}"));
        }
    }

    let r = open_size / 2;
    let opened: Vec<bool> = if r == 0 {
        parcel.iter().zip(feasible).map(|(&p, &f)| p != 0 && f).collect()
    } else {
        dilate(&erode(parcel, feasible, h, w, r), h, w, r)
    };

    // Union-find over opened cells, linking only to already-visited neighbours.
    let mut parent: Vec<u32> = (0..(h * w) as u32).collect();
    for y in 0..h {
        for x in 0..w {
            let i = y * w + x;
            if !opened[i] {
                continue;
            }
            let p = parcel[i];
            let mut link = |j: usize| {
                if opened[j] && parcel[j] == p {
                    union(&mut parent, i as u32, j as u32);
                }
            };
            if x > 0 {
                link(i - 1);
            }
            if y > 0 {
                link(i - w);
                if connectivity == 8 {
                    if x > 0 {
                        link(i - w - 1);
                    }
                    if x + 1 < w {
                        link(i - w + 1);
                    }
                }
            }
        }
    }

    let mut size = vec![0u32; h * w];
    for i in 0..h * w {
        if opened[i] {
            let root = find(&mut parent, i as u32);
            size[root as usize] += 1;
        }
    }

    let mut feasible_cells = vec![0i64; n_parcels + 1];
    let mut largest_cells = vec![0i64; n_parcels + 1];
    let mut n_patches = vec![0i64; n_parcels + 1];
    let mut best_root = vec![u32::MAX; n_parcels + 1];
    // Roots are visited in increasing index order, so `>` keeps the first among ties.
    for i in 0..h * w {
        let s = size[i] as i64;
        if s == 0 || parent[i] != i as u32 {
            continue;
        }
        let p = parcel[i] as usize;
        feasible_cells[p] += s;
        if s >= min_cells {
            n_patches[p] += 1;
        }
        if s > largest_cells[p] {
            largest_cells[p] = s;
            best_root[p] = i as u32;
        }
    }

    let mut mask = vec![0u8; h * w];
    for i in 0..h * w {
        if opened[i] {
            let root = parent[i]; // fully compressed by the size pass
            mask[i] = if root == best_root[parcel[i] as usize] { 2 } else { 1 };
        }
    }
    Ok(PatchStats { feasible_cells, largest_cells, n_patches, mask })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn grid(rows: &[&str]) -> (Vec<i32>, Vec<bool>, usize, usize) {
        // digit = parcel id (feasible), uppercase letter A.. = parcel 1.. infeasible, '.' = no parcel
        let h = rows.len();
        let w = rows[0].len();
        let mut parcel = Vec::new();
        let mut feas = Vec::new();
        for r in rows {
            for c in r.chars() {
                match c {
                    '.' => {
                        parcel.push(0);
                        feas.push(false);
                    }
                    '1'..='9' => {
                        parcel.push(c as i32 - '0' as i32);
                        feas.push(true);
                    }
                    'A'..='I' => {
                        parcel.push(c as i32 - 'A' as i32 + 1);
                        feas.push(false);
                    }
                    _ => panic!("bad fixture char"),
                }
            }
        }
        (parcel, feas, h, w)
    }

    #[test]
    fn empty_input() {
        let s = screen_patches(&[], &[], 0, 0, 0, 3, 4, 1).unwrap();
        assert!(s.mask.is_empty());
        assert_eq!(s.feasible_cells, vec![0]);
    }

    #[test]
    fn components_do_not_cross_parcels() {
        let (p, f, h, w) = grid(&["1122", "1122"]);
        let s = screen_patches(&p, &f, h, w, 2, 1, 4, 1).unwrap();
        assert_eq!(s.largest_cells, vec![0, 4, 4]);
        assert_eq!(s.n_patches, vec![0, 1, 1]);
    }

    #[test]
    fn diagonal_only_joins_with_8_connectivity() {
        let (p, f, h, w) = grid(&["1A", "A1"]);
        let s4 = screen_patches(&p, &f, h, w, 1, 1, 4, 1).unwrap();
        let s8 = screen_patches(&p, &f, h, w, 1, 1, 8, 1).unwrap();
        assert_eq!((s4.largest_cells[1], s4.n_patches[1]), (1, 2));
        assert_eq!((s8.largest_cells[1], s8.n_patches[1]), (2, 1));
    }

    #[test]
    fn opening_removes_thin_strip_and_respects_border() {
        // 3x3 block survives a 3x3 opening; the 1-cell-wide tail does not.
        let (p, f, h, w) = grid(&["1111111", "111AAAA", "111AAAA"]);
        let s = screen_patches(&p, &f, h, w, 1, 3, 4, 1).unwrap();
        assert_eq!(s.feasible_cells[1], 9);
        assert_eq!(&s.mask[0..7], &[2, 2, 2, 0, 0, 0, 0]);
    }

    #[test]
    fn opening_does_not_borrow_neighbour_parcel() {
        // Parcel 1 is only 2 wide; parcel 2 next to it must not help it pass a 3x3 opening.
        let (p, f, h, w) = grid(&["11222", "11222", "11222"]);
        let s = screen_patches(&p, &f, h, w, 2, 3, 4, 1).unwrap();
        assert_eq!(s.feasible_cells, vec![0, 0, 9]);
    }

    #[test]
    fn tie_goes_to_first_component() {
        let (p, f, h, w) = grid(&["11A11"]);
        let s = screen_patches(&p, &f, h, w, 1, 1, 4, 1).unwrap();
        assert_eq!(s.mask, vec![2, 2, 0, 1, 1]);
    }

    #[test]
    fn min_cells_filters_patch_count_only() {
        let (p, f, h, w) = grid(&["111A1"]);
        let s = screen_patches(&p, &f, h, w, 1, 1, 4, 2).unwrap();
        assert_eq!((s.feasible_cells[1], s.n_patches[1], s.largest_cells[1]), (4, 1, 3));
    }

    #[test]
    fn rejects_bad_arguments() {
        assert!(screen_patches(&[1], &[true], 1, 1, 1, 2, 4, 1).is_err());
        assert!(screen_patches(&[1], &[true], 1, 1, 1, 1, 6, 1).is_err());
        assert!(screen_patches(&[2], &[true], 1, 1, 1, 1, 4, 1).is_err());
    }
}
