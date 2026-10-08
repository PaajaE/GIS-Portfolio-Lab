# GIS Portfolio Lab
## Local-first · Rust-first · Analytical GIS portfolio

> **Goal:** build 5 small, technically serious GIS products from open data.
>
> **Core principle:** heavy analysis runs locally on my Mac; the public web serves precomputed results.
>
> **Portfolio message:**  
> **I use GIS, spatial statistics, remote sensing, numerical methods, graph algorithms and Rust to solve difficult spatial problems, then turn the results into usable web products.**

---

# 1. Architecture

## Decision

**Do not build a production GIS platform.**

No default:
- Kubernetes
- permanent geoprocessing server
- PostGIS
- live analysis APIs
- realtime processing
- cloud ETL
- microservices

Instead:

```text
open data
   ↓
local harvest
   ↓
GeoParquet / COG / GeoTIFF
   ↓
Python + GDAL/PROJ/GEOS
        +
      Rust
   ↓
validated derived data
   ↓
Parquet / PMTiles / COG / JSON
   ↓
static MapLibre web app
   ↓
GitHub Pages / Cloudflare Pages
```

**Cloud is the publishing layer, not the GIS engine.**

## Roles

**Python**
- acquisition / ETL
- orchestration
- statistics / ML
- validation
- experiment management
- web-data generation

**Rust**
- computationally interesting kernels
- raster neighborhood operations
- simulation
- cost-distance / graph algorithms
- spatial indexing
- parallel aggregation

**GDAL / PROJ / GEOS**
- format conversion
- reprojection
- clipping / warping / mosaicking
- geometry validation
- mature spatial operations

Do not rewrite mature GIS infrastructure just to use Rust.

## Data formats

| Need | Format |
|---|---|
| large vector analysis | GeoParquet |
| analytical tables | Parquet |
| large raster | COG |
| local interchange | GeoPackage |
| web vector tiles | PMTiles |
| small web payload | JSON |

DuckDB Spatial is **local analytics**, not infrastructure.

PostGIS / Supabase / Firebase / serverless functions are introduced only if a later project genuinely needs dynamic server-side functionality.

---

# 2. Common project workflow

Every project follows the same logic:

```text
1. Problem / decision
2. Study area + analytical unit
3. Source data + provenance
4. CRS / resolution / temporal harmonization
5. Data QA
6. Derived variables
7. Transparent baseline
8. Advanced method
9. Independent validation
10. Sensitivity / uncertainty
11. Decision metric
12. Rust benchmark where relevant
13. Derived artifacts
14. Static web presentation
15. Limitations
```

The important question at every stage is:

> **What are we measuring, why does this variable/method make sense, and how do we know the result is trustworthy?**

The web map is the final presentation layer, not the project itself.

## Minimum quality gate

A flagship project needs:

- real-world question
- ≥3 meaningful datasets
- non-trivial preprocessing
- baseline + advanced method
- validation
- uncertainty/sensitivity where appropriate
- meaningful Rust component
- benchmark when performance is claimed
- decision-oriented output
- reproducible pipeline
- limitations

`DEM → analysis → pretty map` does **not** pass.

---

# 3. Shared engineering rules

## Reproducibility

Each project should support a simple local pipeline such as:

```bash
uv sync
cargo build
make harvest
make analyze
make tiles
make web
```

The exact commands can evolve; the principle is that analysis is reproducible locally.

## Provenance

Every project has `DATA_SOURCES.md` containing:

- provider
- official source URL
- dataset / version / vintage
- acquisition date
- license
- AOI
- preprocessing
- output format
- limitations

Record source CRS, target CRS and relevant checksums/versions where practical.

## Testing

Keep tests proportional:

- geometry validity
- CRS / units / extent
- nulls and value ranges
- raster nodata behavior
- small deterministic fixtures
- Rust unit/integration tests
- benchmark inputs

For simulations, use deterministic seeds and known small cases.

## AI-assisted development

AI may help with:
- source discovery
- ETL
- Python/Rust drafts
- tests
- profiling
- documentation
- frontend

But the portfolio must make clear that I understand:

**problem → assumptions → data → method → validation → uncertainty → computation → decision**

The value is engineering judgment, not authorship of every line.

---

# 4. Portfolio

Build these **five first**:

| Project | Main capability | Priority |
|---|---|---:|
| Parcel Intelligence | vector GIS + spatial screening | ★★★★★ |
| Landslide Susceptibility | terrain + raster + ML | ★★★★★ |
| Wildfire Simulation | Rust + simulation + graphs | ★★★★★+ |
| Flood Exposure | inundation + exposure + network | ★★★★★ |
| Healthcare Accessibility | graph + accessibility + optimization | ★★★★★ |

Optional later:
- Avalanche Terrain Explorer
- Wildlife Connectivity

This gives broad coverage without seven similar environmental maps.

---

# 5. Project 01 — Parcel Intelligence

## Question

> **Given a parcel and stated planning assumptions, how much of it remains potentially feasible, what constraints dominate, and how robust is that conclusion?**

### Data

- parcels
- roads / road class
- DEM
- FEMA flood zones
- protected/public land
- wetlands / hydrography where available
- zoning / utilities where available

### How

Parcel is the reporting unit, but feasibility is calculated spatially:

```text
parcel
 ↓
clip / harmonize constraints
 ↓
terrain derivatives
 ↓
hard constraint mask
 ↓
morphological cleanup
 ↓
connected components
 ↓
largest contiguous feasible area
 ↓
access metrics
 ↓
parcel metrics
```

Example:

```text
feasible =
    not_flood
    AND not_wetland
    AND not_protected
    AND slope < threshold
    AND setback_satisfied
    AND allowed_landuse
```

Calculate:
- total area
- constrained area
- potentially feasible area
- largest contiguous feasible patch
- patch count / distribution
- slope statistics
- frontage / road distance
- constraint breakdown

### Why

A parcel-wide average slope or one weighted score hides internal structure. Hard exclusions should not be mixed blindly with soft preferences.

### Scenarios

Use explicit assumptions, e.g.:

```text
              Conservative   Moderate   Aggressive
slope             20°           25°         30°
setback            50 m          30 m        15 m
```

The goal is **robustness**, not claiming one threshold is universally correct.

### Rust

- connected components / morphology
- high-throughput parcel × constraint aggregation
- spatial indexing where useful

Benchmark against a Python/reference implementation.

### Validation / caveat

There is no universal ground truth for "developable." Validate structural correctness and hand-check sample parcels.

Call the result:

> **potential feasibility under stated spatial screening assumptions**

—not legal development entitlement.

---

# 6. Project 02 — Landslide Susceptibility

## Question

> **Can we build a spatially transferable landslide susceptibility model and show where its predictions are reliable?**

### Data

- USGS Landslide Inventory
- 3DEP DEM
- soil
- geology
- land cover
- precipitation
- vegetation
- roads / buildings for exposure

### Analytical unit

Compare:

```text
pixel/grid baseline
        vs
slope units
```

Do not make a random pixel split the primary validation design.

### How

```text
inventory
 ↓
quality / confidence inspection
 ↓
positive + negative sampling design
 ↓
terrain / environmental predictors
 ↓
baseline logistic regression
 ↓
Random Forest / gradient boosting
 ↓
spatial validation
 ↓
calibration + uncertainty
 ↓
infrastructure exposure
```

Predictors may include:
- slope
- curvature
- TPI / TRI
- relative relief
- flow accumulation
- drainage density
- distance to channel
- soil / geology / precipitation / vegetation

Do not add variables merely because they are available; each needs a physical or empirical rationale.

### Why

Landslide inventories are biased and mapped absence is not necessarily true absence. Spatially correlated pixels can also leak information between train and test.

Therefore document:
- positive sampling
- negative sampling
- inventory density
- confidence
- spatial holdout
- temporal holdout if dates permit

### Validation

Report:
- ROC-AUC
- PR-AUC
- Brier score
- calibration
- confusion matrix at stated thresholds
- spatial error map

Also compare with an independent/reference susceptibility product where practical.

### Uncertainty

Show separately:

```text
susceptibility
prediction uncertainty
training-data density
extrapolation / out-of-domain area
```

### Rust

Rust owns expensive terrain kernels:
- local relief
- curvature
- roughness
- window statistics
- terrain preprocessing

ML remains in Python.

### Critical distinction

**Susceptibility ≠ hazard ≠ risk.**

Exposure analysis comes only after the susceptibility model is validated.

---

# 7. Project 03 — FirePath

## Question

> **Can a lightweight, reproducible fire-spread model reconstruct historical wildfire growth well enough to explore alternative fuel, terrain and wind scenarios?**

This is the technical flagship.

### Data

Use several historical western US fires with:
- observed perimeters
- ignition/start information where available
- time-aligned fuels
- DEM
- historical wind/weather where available
- roads
- buildings
- population

LANDFIRE is the main fuel/vegetation source; NIFC/MTBS provide historical fire information.

### Core design

Do **not** build a toy burn/no-burn cellular automaton.

Build an explicit simplified **rate-of-spread / arrival-time model**:

```text
fuel
 + slope
 + aspect
 + wind
 + stated modifiers
        ↓
local spread rate
        ↓
anisotropic propagation
        ↓
arrival_time[cell]
        ↓
predicted perimeter
```

For each neighbor, direction relative to wind and slope matters.

### Why

Arrival time supports much more than a final perimeter:

- burn timing
- road closure timing
- population exposure by hour
- evacuation scenarios
- sensitivity analysis

### Calibration / validation

Never tune and validate on the same fire.

Example:

```text
Fire A/B/C → calibration
Fire D/E   → validation
```

Tune explicit parameters such as:
- baseline spread coefficient
- fuel multiplier
- slope sensitivity
- wind sensitivity
- moisture multiplier

### Validation

Compare:
- burned area
- IoU
- Dice/Sorensen
- boundary distance
- Hausdorff distance
- arrival-time error where observations permit

### Sensitivity

Vary:
- wind speed/direction
- fuel map
- moisture
- slope coefficient

Produce scenario ensembles and probability-of-burning-by-time **only if the probabilistic interpretation is explicitly justified**.

### Network coupling

Only after the fire model is validated:

```text
arrival time
 ↓
road closure time
 ↓
network recomputation
 ↓
travel time / disconnected population
```

### Rust

Rust owns:
- cell state
- neighbor evaluation
- propagation
- parallel scenario execution

Benchmark:

```text
Python reference
vs
Rust single-thread
vs
Rust + Rayon
```

Across multiple grid sizes, steps and scenario counts.

### Explicit scope

Do not pretend this is FARSITE/FlamMap or an operational system.

Document omitted processes, e.g.:
- spotting
- crown-fire transitions
- dynamic moisture
- atmospheric feedback
- suppression
- sub-cell fuel heterogeneity

That is acceptable if the scope is explicit.

---

# 8. Project 04 — Flood Exposure

## Question

> **How does a flood scenario translate into water depth, building/property exposure and loss of network accessibility?**

Keep four layers separate:

```text
hazard
 ↓
depth
 ↓
exposure
 ↓
network consequence
```

### Data

- FEMA NFHL
- 3DEP
- 3DHP
- parcels
- buildings
- roads
- population

### How

**1. Regulatory reference**

Use FEMA NFHL as the official mapped reference; do not treat it as an observed footprint for every event.

**2. Portfolio scenario**

For a selected watershed/floodplain use a clearly stated method:
- HAND-style
- bathtub / water-level
- terrain-constrained flood fill
- external hydraulic result if available

**3. Depth**

Only after defining a scenario water surface:

```text
scenario water surface
 ↓
water surface − DEM
 ↓
positive depth
```

**4. Exposure**

Buildings:
- max depth
- mean depth
- exposed footprint fraction

Parcels:
- exposed area
- depth distribution

**5. Optional damage proxy**

```text
depth
 ↓
damage ratio
 ↓
asset value
 ↓
screening-level loss
```

Never call this insurance-grade valuation without appropriate data.

**6. Network**

```text
road segment
 ↓
flood depth
 ↓
documented closure threshold
 ↓
closed/open network
 ↓
accessibility impact
```

### Validation

Compare with independent evidence where available:
- FEMA mapping
- historical event footprint
- event imagery
- independent flood products

Do not say "validated against FEMA" if the two products represent different things.

### Rust

- parallel inundation / flood-fill
- depth calculation
- road-segment exposure aggregation

### Critical distinction

Always distinguish:

**regulatory mapping / screening scenario / hydraulic model / observed event.**

---

# 9. Project 05 — Healthcare Accessibility

## Question

> **Which populations lack reasonable access to healthcare, and where would one additional facility produce the largest improvement?**

### Data

- OSM road network
- hospitals / clinics
- Census population
- demographics
- optional GTFS
- road class / speed assumptions

### How

Define the population unit explicitly; centroids are an approximation.

Build a road graph:

```text
nodes = intersections + access points
edges = road segments
cost = length / speed + documented penalties
```

Do not use geometric distance as travel time.

### Accessibility

First:

**cumulative opportunity**
- facilities/capacity reachable within 10 / 15 / 30 / 45 min

Then optionally:

**gravity / 2SFCA-style accessibility**

```text
accessibility
≈ supply × travel friction × competition
```

Facility supply should use capacity/service information where available; otherwise state the simplification.

### Optimization

Use a named problem such as:

**maximum coverage**
> choose a candidate facility location that maximizes population served within a threshold.

Show:

```text
current coverage
 ↓
candidate site
 ↓
new coverage
 ↓
marginal population served
```

### Sensitivity

Vary:
- speed assumptions
- thresholds
- facility capacity
- decay parameters

### Rust

- multi-source Dijkstra
- shortest-path preprocessing
- isochrone generation

Compare selected routes / travel times against an independent routing engine on sample OD pairs.

---

# 10. Optional — Avalanche Terrain Explorer

## Question

> **How does terrain and historical avalanche evidence change route exposure under stated scenarios?**

This is a terrain-analysis project, **not an operational avalanche forecast**.

### Data

- high-resolution DEM
- trails / roads
- historical avalanche observations
- optional snow/weather context

### Method

Derive:
- slope
- aspect
- elevation
- curvature / convexity
- ruggedness
- gullies
- terrain traps

Classify terrain into documented analytical classes rather than using only `30–45°`.

Segment a drawn route and calculate:
- elevation profile
- ascent/descent
- slope distribution
- aspect
- terrain class
- proximity to historical evidence

Use explicit scenarios such as baseline / wind-loaded / heavy snowfall. Do not invent probabilities without a defensible probabilistic model.

Historical observation density is observationally biased; do not equate it automatically with true avalanche frequency.

---

# 11. Optional — Wildlife Connectivity

## Question

> **Which landscape corridors are important under a stated species/habitat resistance model, and where are the bottlenecks?**

Choose a focal species or ecological guild.

```text
habitat suitability
 ↓
resistance surface
 ↓
cost distance
 ↓
least-cost / near-optimal corridors
 ↓
bottlenecks
 ↓
road crossing priorities
```

Resistance must be justified ecologically, not chosen arbitrarily.

Use multiple near-optimal corridors where possible; a single least-cost path can be unstable.

Do not call modeled road intersections "wildlife crossing hotspots" without independent evidence.

Rust candidate:
**cost-distance / priority-queue graph traversal.**

---

# 12. Rust portfolio story

The Rust work should form one coherent narrative:

```text
Raster / arrays
      ↓
Wildfire simulation
      ↓
Graph algorithms
```

Target at least three credible stories:

1. **Raster engine** — terrain / neighborhood kernels
2. **Simulation** — wildfire arrival-time propagation
3. **Graph** — healthcare routing or wildlife cost-distance

Every performance claim needs:
- input size
- algorithm
- CPU / RAM
- Python/reference time
- Rust time
- speedup
- multiple input sizes

If Rust is only 1.2× faster and adds complexity, say so.

---

# 13. Web product

Common stack:

**MapLibre + PMTiles + static assets**

Shared UI:
- map
- layer toggle
- legend
- feature inspector
- metric cards
- scenario/time controls
- data sources / methodology
- download

Every project case study follows:

```text
Problem
Why it matters
Study area
Data
Method
Rust / algorithm
Validation
Results
Limitations
Interactive map
Source code
```

The first screen answers:

> **What problem did I solve?**

—not "what technologies did I use?"

---

# 14. Deployment

Default:

```text
local Mac
 ↓
derived artifacts
 ↓
GitHub / object storage
 ↓
static web
```

Start with:
- GitHub Pages, or
- Cloudflare Pages

Use object storage only when generated artifacts are too large for Git.

Backend / database is a project-specific exception, not a portfolio requirement.

---

# 15. Build order

### 1 — Parcel Intelligence
End-to-end GIS foundation.

### 2 — Landslide
Serious raster + statistical/ML modeling.

### 3 — FirePath
Rust + simulation + validation flagship.

### 4 — Flood
Inundation + exposure + network consequence.

### 5 — Healthcare
Graph algorithms + accessibility + optimization.

Only then decide whether Avalanche or Wildlife adds enough new signal.

---

# 16. Final quality gate

Before publishing any project, verify:

### Spatial
- CRS and units correct
- resolution justified
- raster/vector alignment checked
- nodata handled
- geometry valid

### Temporal
- source vintages recorded
- predictors are temporally appropriate
- post-event data is not used as pre-event evidence

### Statistical
- leakage checked
- sampling documented
- baseline exists
- validation is independent enough
- calibration evaluated when probabilities are claimed

### Model
- variables have a reason
- thresholds are justified or presented as scenarios
- scope and omitted processes are explicit

### Decision
- output is no stronger than evidence
- susceptibility is not called risk
- exposure is not called risk without consequence/vulnerability
- distance is not called accessibility
- modeled scenarios are not presented as official forecasts

### Engineering
- deterministic small fixture
- documented output schema
- reproducible benchmark
- Rust agrees with reference within tolerance

---

# 17. Final standard

A finished project should let me explain, without opening the code:

> **Here is the problem.**  
> **Here is the data and why I need it.**  
> **Here is the analytical unit.**  
> **Here is the baseline.**  
> **Here is the advanced method and why it is better.**  
> **Here is how I validated it.**  
> **Here is the uncertainty.**  
> **Here is what changes under different assumptions.**  
> **Here is the part Rust makes computationally interesting.**  
> **Here is the decision metric.**  
> **Here is what the model cannot tell you.**

That is the portfolio.
