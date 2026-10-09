# Hand checks — status: AI-assisted only, **pending human review**

The figures in `figures/` are rendered by `make validate` (`parcel_intel.validate`): left = hard
constraints of the moderate scenario over a hillshade, right = feasible area after the 10 m opening for
each scenario (nested). Sample: one vacant and one built parcel (> 4,000 m²) per screened robustness
class (seeded), the two screened parcels where the naive baseline overstates most, and parcels
discussed in `METHOD.md`.

The **"AI notes"** column is a visual plausibility check by the coding assistant (Claude), made against
the same input layers the model uses. It is not independent and not a human review. The **"Human
review"** column is empty on purpose: a person should fill it in, ideally comparing against
recent MassGIS orthoimagery and local knowledge, and recording *agree / disagree / unsure* with a
reason. Until it is filled in, no result here counts as human-validated.

Areas: largest contiguous patch, conservative / moderate / aggressive (m²).

| pid | Address · assessor use | Patch con/mod/agg | Class · vacancy | AI notes (2026-10-08) | Human review |
|---|---|---|---|---|---|
| 209 | University Dr · Developable Commercial Land | 3,140 / 3,732 / 5,420 | robust · vacant (by use code) | Two mapped buildings on a parcel coded *vacant* land → counted vacant by the code rule although footprints exist. Steep bank along the north edge. Patch avoids buildings. Plausible geometry; **vacancy flag questionable** (outdated code or footprint?). | |
| 850 | 100 Cowls Rd · Single family | 820 / 1,308 / 2,804 | robust · built | Patch is the yard south of the house; slope cells and a small wetland buffer in the north. Plausible; patch is yard, not a separate lot. | |
| 2181 | Montague Rd · Ch. 61A Christmas trees | 58,184 / 71,320 / 85,880 | assumption-dependent · vacant | Large open field; wetland buffers on both ends. Class driven by Chapter 61 eligibility (excluded in conservative), not by physical constraints — the right panel shows physical feasibility only. Plausible. | |
| 6048 | 29 Stagecoach Rd · Single family | 272 / 1,588 / 2,944 | assumption-dependent · built | Scattered slope cells split the lot; the 10 m conservative setback fragments it below 500 m². Plausible; yard space. | |
| 302 | Snell St · Undevelopable residential | 0 / 0 / 1,092 | only aggressive · vacant | Wetland setback covers almost all of the parcel; only the 15 m aggressive buffer frees the SE corner. Consistent with the assessor's "undevelopable". | |
| 5868 | 39 Trillium Way · Single family | 0 / 320 / 576 | only aggressive · built | Flag lot: private-way surface along the stem, wetland buffer over the east half. Plausible. | |
| 5167 | Shutesbury Rd · Agricultural | 0 / 0 / 0 | constrained · vacant | Fully covered by protected open space (likely an agricultural restriction) plus stream buffers. Plausible. | |
| 2020 | 23 South Mt Holyoke Dr · Single family | 0 / 0 / 0 | constrained · built | Entirely in SFHA and wetland buffer; binding constraint "none" because flood and wetland overlap (dropping either alone frees nothing). Plausible. House footprint hidden under the flood colour. | |
| 4193 | Henry St · Developable residential land | 61,048 / 258,656 / 374,348 | robust · vacant | 57 ha forested parcel; slope bands along stream ravines and a perennial-stream buffer split it. Large contiguous upland remains. Naive screen counts the whole 56.7 ha. Plausible. | |
| 2755 | West St · Ch. 61A field crops | 180,068 / 249,944 / 280,168 | assumption-dependent · vacant | Open fields; wetland/stream buffers cut it into two large pieces. Class driven by Chapter 61 eligibility. Plausible. | |
| 1090 | 60 Hobart Ln · Single family | 220 / 2,064 / 3,160 | assumption-dependent · built | Northern edge cut by the buffer of a wetland outside the parcel; conservative 50 m buffer + 10 m setback leave 220 m². Plausible; yard space. | |
| 3424 | South Middle St · Undevelopable residential | 0 / 408 / 656 | only aggressive · vacant | Private-way strip with a cul-de-sac. Stem excluded as road surface (added after an earlier check); the bulb remains partly feasible because centrelines do not represent it — **known false positive** under aggressive assumptions. | |
| 4907 | Belchertown Rd · Undevelopable residential | 0 / 0 / 0 | constrained · vacant | Entirely in the 1 % flood zone along the Fort River. Consistent with the assessor. | |
| 1795 | North Pleasant St · UMass | 70,056 / 208,860 / 278,204 | not screened · built | Tax-exempt campus; physical results shown for context only. An earlier run classed it "robust" because assessor records were mixed — fixed. | |

## Defects found by these checks (fixed)
1. Mixed assessor records on multi-record parcels (pid 1795) → one representative record + any-exempt flag.
2. Private-way pavement counted as feasible (pid 3424) → road surface added to existing development.

## Open questions for the human reviewer
- Is the vacancy rule (no footprint **or** vacant-land use code) right for parcels like 209?
- Are the Chapter 61 parcels (2181, 2755) appropriately "assumption-dependent", or should Chapter land be reported separately?
- Do the wetland buffers look right against orthoimagery (1090, 302, 5868)?
