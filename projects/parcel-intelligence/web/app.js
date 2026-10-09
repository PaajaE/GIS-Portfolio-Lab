import * as maplibregl from "https://cdn.jsdelivr.net/npm/maplibre-gl@6.11.1/dist/maplibre-gl.mjs";

// ---------------------------------------------------------------------------
// vocabulary (single source for labels, colours and order)
// ---------------------------------------------------------------------------
const ROB = [
  { key: "robust", code: 3, color: "#0f4c5c", dark: true, label: "Robust", long: "qualifying patch in all three scenarios" },
  { key: "assumption-dependent", code: 2, color: "#2f8a8a", dark: true, label: "Assumption-dependent", long: "qualifying patch under moderate and aggressive assumptions only" },
  { key: "only aggressive", code: 1, color: "#9cd2c4", label: "Only aggressive", long: "qualifying patch only under the aggressive assumptions" },
  { key: "constrained", code: 0, color: "#ebe6da", label: "Constrained", long: "no qualifying patch in any scenario" },
  { key: "not screened", code: -1, color: "#b9b4a9", label: "Not screened", long: "tax-exempt public or institutional land (shown, not screened)" },
];
const ROB_BY_KEY = Object.fromEntries(ROB.map((r) => [r.key, r]));
const SCEN = ["conservative", "moderate", "aggressive"];
const SCEN_SHORT = { conservative: "con", moderate: "mod", aggressive: "agg" };
const CONS = {
  flood: "Flood zone",
  wetland_water: "Wetland, water or stream setback",
  protected: "Protected open space",
  priority_habitat: "Priority habitat",
  steep_slope: "Steep slope",
  yard_setback: "Setback from lot lines",
  existing_development: "Existing buildings and roads",
};
const nf = new Intl.NumberFormat("en-US");
const m2 = (v) => `${nf.format(Math.round(v))} m²`;
const ha = (v) => `${nf.format(Math.round(v))} ha`;
const pct = (v) => `${Math.round(v * 100)}%`;
const pct1 = (v) => `${(v * 100).toFixed(1)}%`;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const get = (o, path) => path.split(".").reduce((a, k) => (a == null ? a : a[k]), o);
const dataUrl = (p) => new URL(`data/${p}`, location.href).href;

let S = null; // summary.json
let D = null; // parcels.json (column-oriented)
let map = null;
let mode = "robustness";
let selected = null;
let ready = false; // style + images added (isStyleLoaded() is false while tiles load)

// ---------------------------------------------------------------------------
// summary-driven text, tables and charts
// ---------------------------------------------------------------------------
function fillValues() {
  document.querySelectorAll("[data-v]").forEach((el) => {
    const v = get(S, el.dataset.v);
    if (v == null) return;
    el.textContent = typeof v === "number" ? nf.format(el.dataset.fmt === "int" ? Math.round(v) : v) : v;
  });
}

function robustBar() {
  const fill = (id, counts, what) => {
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    const bar = document.getElementById(id);
    bar.innerHTML = ROB.map((r) => {
      const n = counts[r.key] || 0;
      return `<div class="seg-b${r.dark ? " on-dark" : ""}" style="flex:${n} 1 0;background:${r.color}" title="${esc(r.label)}: ${nf.format(n)}">
        <b>${nf.format(n)}</b><span>${esc(r.label)}</span></div>`;
    }).join("");
    bar.setAttribute("aria-label", `${what}, ${nf.format(total)} parcels: ` + ROB.map((r) => `${r.label}: ${nf.format(counts[r.key] || 0)} (${r.long})`).join("; ") + ".");
    return bar;
  };
  fill("robust-bar-vacant", S.results.robustness_vacant, "Vacant parcels");
  const bar = fill("robust-bar-built", S.results.robustness_built, "Built parcels");
  const keys = document.createElement("ul");
  keys.className = "robust-keys";
  keys.innerHTML = ROB.map((r) => `<li><i style="background:${r.color}"></i>${esc(r.label)}</li>`).join("");
  bar.after(keys);
}

function scenarioTable() {
  const rows = [
    ["Slope threshold (excluded at or above)", (p) => `${p.slope_pct}%`],
    ["Wetland and water-body buffer", (p) => `${p.wetland_buffer_m} m`],
    ["Perennial stream buffer", (p) => `${p.perennial_stream_buffer_m} m`],
    ["Intermittent stream / ditch buffer", (p) => `${p.other_stream_buffer_m} m`],
    ["Flood exclusion", (p) => ({ "sfha_and_0.2pct": "1% + 0.2% annual chance", sfha: "1% annual chance (SFHA)", floodway: "regulatory floodway only" })[p.flood]],
    ["Protected open space excluded", (p) => p.protection_levels.map((l) => ({ P: "in perpetuity", T: "term-limited", L: "limited" })[l]).join(", ")],
    ["Priority habitat excluded", (p) => (p.exclude_priority_habitat ? "yes" : "no")],
    ["Uniform setback from lot lines", (p) => `${p.yard_m} m`],
    ["Chapter 61/61A/61B land screened", (p) => (p.exclude_chapter_land ? "no (excluded)" : "yes")],
  ];
  document.querySelector("#scenario-table tbody").innerHTML = rows
    .map(([lab, f]) => `<tr><th scope="row">${lab}</th>${SCEN.map((s) => `<td>${esc(f(S.scenarios[s]))}</td>`).join("")}</tr>`)
    .join("");
}

function resultsTable() {
  document.querySelector("#results-table tbody").innerHTML = SCEN.map((s) => {
    const r = S.results.scenarios[s];
    return `<tr><th scope="row">${s[0].toUpperCase() + s.slice(1)}</th><td class="n"><strong>${nf.format(r.qualifying_vacant)}</strong> of ${nf.format(r.eligible_vacant)}</td>
      <td class="n">${nf.format(r.qualifying_built)} of ${nf.format(r.eligible_built)}</td>
      <td class="n">${ha(r.naive_area_ha)}</td><td class="n">${ha(r.net_area_ha)}</td><td class="n"><strong>${ha(r.largest_patch_area_ha)}</strong> (${ha(r.largest_patch_vacant_ha)})</td></tr>`;
  }).join("");
}

function benchTable() {
  const b = S.benchmark;
  document.querySelector("#bench-table caption").textContent = `${b.hardware.cpu}, ${b.hardware.ram_gb} GB RAM, ${b.hardware.threads}; median of repeated runs (${b.harness}).`;
  document.querySelector("#bench-table tbody").innerHTML = b.sizes
    .map((r) => `<tr><td class="n">${nf.format(r.cells)}</td><td class="n">${nf.format(r.parcels_present)}</td><td class="n">${r.reference_median_s.toFixed(3)}</td><td class="n">${r.rust_median_s.toFixed(3)}</td><td class="n">${r.speedup_median.toFixed(1)}×</td></tr>`)
    .join("");
  const pe = b.pipeline_estimate;
  document.getElementById("bench-note").textContent =
    `Honest reading: a ${b.sizes.at(-1).speedup_median.toFixed(1)}× speed-up, because the SciPy reference already runs in C per parcel. ` +
    `A full run makes ${pe.kernel_calls_per_full_run} kernel calls (scenarios, leave-one-out, sensitivity): ${pe.reference_s} s with the reference vs ${pe.rust_s} s with Rust. ` +
    `For one town this is a convenience, not a necessity; larger areas, finer grids or denser parameter sweeps were not benchmarked.`;
}

function validationList() {
  const v = S.validation;
  const ras = v.rasterization_vs_geos;
  const a = v.assessor_comparison;
  const b = v.post2000_buildings;
  const items = [
    ["ok", "Kernel correctness", `Rust and the SciPy reference give identical patch statistics for every parcel in the full-town moderate run (${nf.format(S.results.parcels)} parcels; one 14 m² parcel has no cell centre), plus 72 randomized fixtures and hand-computed edge cases (borders, ties, empty input, parcels narrower than the opening).`],
    ["ok", "Rasterization vs exact overlay", `Per-parcel constraint area from the 2 m grid vs GEOS polygon overlay: wetland/water setbacks ${ras.wetland_water.total_raster_ha} vs ${ras.wetland_water.total_vector_ha} ha town-wide; 95th percentile absolute error ${pct1(ras.wetland_water.abs_error_share_of_parcel_p95)} of parcel area (flood ${pct1(ras.flood.abs_error_share_of_parcel_p95)}, protected ${pct1(ras.protected.abs_error_share_of_parcel_p95)}).`],
    ["cmp", "Assessor land classes (comparison, not ground truth)", `The assessor classes some vacant land as developable or potentially developable (${a.n.developable} parcels, of which ${a.n_potentially_developable} “potentially”) or undevelopable (${a.n.undevelopable}). Ranking by the largest contiguous patch separates them with AUC ${a.auc.largest_mod.toFixed(2)} (moderate), the net-area baseline ${a.auc.net_mod.toFixed(2)}, the naive screen ${a.auc.naive_mod.toFixed(2)}, parcel size alone ${a.auc.parcel_area_only.toFixed(2)}. The gain over the naive screen is clear (95% CI ${a.auc_difference_95ci.largest_minus_naive_mod.join(" to ")}); over net area it is not detectable (${a.auc_difference_95ci.largest_minus_net_mod.join(" to ")}). Qualifying patch under moderate assumptions: ${pct(a.qualifying_share_mod.developable)} of the first group vs ${pct(a.qualifying_share_mod.undevelopable)} of “undevelopable” parcels.`],
    ["cmp", "Where recent houses stand", `Of building footprints on ${nf.format(b.parcels)} parcels built in 2000 or later, ${pct1(b.share_in_flood)} lie in the 1% flood zone, ${(b.share_in_wetland_water * 100).toFixed(1)}% in the moderate wetland/water setback, ${(b.share_in_steep_slope * 100).toFixed(1)}% on slopes ≥ 25% (biased low: lidar is post-construction).`],
    ["lim", "Hand checks — AI-assisted, pending human review", `${v.hand_check_sample.length} parcels (one vacant and one built per class, the screened parcels the naive screen overstates most, and documented cases) were checked visually by the AI coding assistant against hillshade and the same constraint layers — not independent, and not yet reviewed by a person. The checks exposed two defects that were fixed (mixed assessor records on multi-record parcels; private-way pavement counted as feasible). Figures and the review sheet are in the repository (validation/HAND_CHECKS.md, linked under Downloads and source).`],
  ];
  document.getElementById("validation-list").innerHTML = items
    .map(([t, h, txt]) => `<li><span class="tag ${t}">${{ ok: "verified", cmp: "comparison", lim: "manual" }[t]}</span><strong>${h}.</strong> ${esc(txt)}</li>`)
    .join("");
}

function tornado() {
  const rows = S.sensitivity;
  const ref = rows.find((r) => r.variant === "moderate").qualifying_vacant;
  const groups = [...new Set(rows.filter((r) => r.variant !== "moderate").map((r) => r.group))];
  const stricter = (v) => v === "conservative" || v === "14 m square";
  const data = groups.map((g) => {
    const rs = rows.filter((r) => r.group === g);
    const lo = rs.find((r) => stricter(r.variant));
    const hi = rs.find((r) => !stricter(r.variant));
    return { g, lo: lo ? lo.qualifying_vacant - ref : 0, hi: hi ? hi.qualifying_vacant - ref : 0, loV: lo?.variant, hiV: hi?.variant };
  }).sort((a, b) => b.hi - b.lo - (a.hi - a.lo));
  const max = Math.max(...data.map((d) => Math.max(Math.abs(d.lo), Math.abs(d.hi)))) || 1;
  const w = (v) => (Math.abs(v) / max) * 34; // leave room for value labels
  const el = document.getElementById("tornado");
  el.innerHTML =
    data.map((d) => `<div class="lab">${esc(d.g)}</div><div class="row">
      ${d.lo ? `<span class="neg" style="right:50%;width:${w(d.lo)}%"></span><span class="t" style="right:calc(50% + ${w(d.lo)}% + 4px)">${nf.format(d.lo)}</span>` : ""}
      ${d.hi ? `<span class="pos" style="left:50%;width:${w(d.hi)}%"></span><span class="t" style="left:calc(50% + ${w(d.hi)}% + 4px)">+${nf.format(d.hi)}</span>` : ""}
    </div>`).join("") +
    `<div class="axis"><span>stricter value</span><span>moderate: ${nf.format(ref)} vacant parcels</span><span>looser value</span></div>`;
  document.getElementById("tornado-text").textContent =
    `Change in vacant parcels with a qualifying patch relative to ${nf.format(ref)} under moderate assumptions: ` +
    data.map((d) => `${d.g}: ` + [d.loV ? `${d.lo} (stricter)` : null, d.hiV ? `+${d.hi} (looser)` : null].filter(Boolean).join(", ")).join("; ") + ".";
  el.setAttribute("aria-label", "Sensitivity of the number of vacant parcels with a qualifying patch to each assumption");
}

// ---------------------------------------------------------------------------
// map
// ---------------------------------------------------------------------------
function hatch() {
  const c = document.createElement("canvas");
  c.width = c.height = 8;
  const g = c.getContext("2d");
  g.fillStyle = "rgba(185,180,169,0.55)";
  g.fillRect(0, 0, 8, 8);
  g.strokeStyle = "rgba(90,86,78,0.7)";
  g.lineWidth = 1;
  g.beginPath();
  g.moveTo(0, 8); g.lineTo(8, 0);
  g.moveTo(-2, 2); g.lineTo(2, -2);
  g.moveTo(6, 10); g.lineTo(10, 6);
  g.stroke();
  return g.getImageData(0, 0, 8, 8);
}

// Built parcels (v = 0) are faded so that vacant parcels carry the visual weight.
function robOpacity() {
  const fade = document.getElementById("fade-built")?.checked ?? true;
  // MapLibre allows one zoom interpolation per expression, so the vacancy case sits inside the stops
  const vac = ["==", ["get", "v"], 1];
  const at = (full, faded) => (fade ? ["case", vac, full, faded] : full);
  return ["interpolate", ["linear"], ["zoom"], 12, at(0.82, 0.3), 17, at(0.5, 0.22)];
}

function style() {
  const ov = S.overlays.coordinates;
  const robColor = ["match", ["get", "rob"], ...ROB.flatMap((r) => [r.code, r.color]), "#ffffff"];
  return {
    version: 8,
    glyphs: new URL("fonts/", location.href).href + "{fontstack}/{range}.pbf", // tokens must stay unescaped
    sources: {
      hs: { type: "image", url: dataUrl("hillshade.jpg"), coordinates: ov },
      ctx: { type: "vector", url: `pmtiles://${dataUrl("context.pmtiles")}`, attribution: "MassGIS, MassDEP, MassDOT, NHESP, FEMA, USGS 3DEP" },
      parcels: { type: "vector", url: `pmtiles://${dataUrl("parcels.pmtiles")}` },
      patches: { type: "vector", url: `pmtiles://${dataUrl("patches.pmtiles")}` },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "#efece4" } },
      { id: "hillshade", type: "raster", source: "hs", paint: { "raster-opacity": 0.55, "raster-fade-duration": 0 } },
      { id: "water", type: "fill", source: "ctx", "source-layer": "wetlands", filter: ["==", ["get", "t"], "water"], paint: { "fill-color": "#9cc3e0" } },
      { id: "parcels-fill", type: "fill", source: "parcels", "source-layer": "parcels", filter: ["!=", ["get", "rob"], -1], paint: { "fill-color": robColor, "fill-opacity": robOpacity() } },
      { id: "parcels-ns", type: "fill", source: "parcels", "source-layer": "parcels", filter: ["==", ["get", "rob"], -1], paint: { "fill-pattern": "hatch", "fill-opacity": 0.85 } },
      { id: "patches", type: "fill", source: "patches", "source-layer": "patches", filter: ["==", ["get", "s"], 1], layout: { visibility: "none" }, paint: { "fill-color": "#f59e0b", "fill-opacity": 0.85 } },
      { id: "patches-line", type: "line", source: "patches", "source-layer": "patches", filter: ["==", ["get", "s"], 1], layout: { visibility: "none" }, paint: { "line-color": "#92400e", "line-width": ["interpolate", ["linear"], ["zoom"], 13, 0.3, 17, 1.2] } },
      { id: "flood", type: "fill", source: "ctx", "source-layer": "flood", layout: { visibility: "none" }, paint: { "fill-color": "#2b6cb0", "fill-opacity": ["match", ["get", "z"], "floodway", 0.6, "sfha", 0.42, 0.18] } },
      { id: "wetlands", type: "fill", source: "ctx", "source-layer": "wetlands", filter: ["==", ["get", "t"], "wetland"], layout: { visibility: "none" }, paint: { "fill-color": "#2c9c8f", "fill-opacity": 0.5 } },
      { id: "streams", type: "line", source: "ctx", "source-layer": "streams", paint: { "line-color": "#3b82c4", "line-width": ["match", ["get", "per"], 1, 1.4, 0.7], "line-dasharray": ["match", ["get", "per"], 1, ["literal", [1, 0]], ["literal", [3, 2]]] } },
      { id: "protected", type: "fill", source: "ctx", "source-layer": "protected", filter: ["in", ["get", "lev"], ["literal", ["P", "T", "L"]]], layout: { visibility: "none" }, paint: { "fill-color": "#4d7c0f", "fill-opacity": ["match", ["get", "lev"], "P", 0.38, 0.18] } },
      { id: "protected-line", type: "line", source: "ctx", "source-layer": "protected", filter: ["in", ["get", "lev"], ["literal", ["P", "T", "L"]]], layout: { visibility: "none" }, paint: { "line-color": "#365314", "line-width": 1 } },
      { id: "habitat", type: "line", source: "ctx", "source-layer": "habitat", layout: { visibility: "none" }, paint: { "line-color": "#7c3aed", "line-width": 2, "line-dasharray": [2, 1.5] } },
      { id: "parcels-line", type: "line", source: "parcels", "source-layer": "parcels", minzoom: 13, paint: { "line-color": "#5b5547", "line-opacity": 0.55, "line-width": ["interpolate", ["linear"], ["zoom"], 13, 0.2, 17, 0.9] } },
      { id: "buildings", type: "fill", source: "ctx", "source-layer": "buildings", minzoom: 14, paint: { "fill-color": "#5f5f5f", "fill-opacity": 0.75 } },
      { id: "roads-case", type: "line", source: "ctx", "source-layer": "roads", paint: { "line-color": "#8c877b", "line-width": ["interpolate", ["linear"], ["zoom"], 11, ["match", ["get", "cls"], [2, 3, 4], 1.6, 0.6], 17, ["match", ["get", "cls"], [2, 3, 4], 9, 6]] } },
      { id: "roads", type: "line", source: "ctx", "source-layer": "roads", paint: { "line-color": "#ffffff", "line-width": ["interpolate", ["linear"], ["zoom"], 11, ["match", ["get", "cls"], [2, 3, 4], 0.9, 0.2], 17, ["match", ["get", "cls"], [2, 3, 4], 7, 4.5]] } },
      { id: "town", type: "line", source: "ctx", "source-layer": "town", paint: { "line-color": "#1f2328", "line-width": 1.6, "line-dasharray": [4, 2] } },
      { id: "selected", type: "line", source: "parcels", "source-layer": "parcels", filter: ["==", ["get", "pid"], -1], paint: { "line-color": "#0b57d0", "line-width": 3.5 } },
      { id: "road-labels", type: "symbol", source: "ctx", "source-layer": "roads", minzoom: 14.5, layout: { "symbol-placement": "line", "text-field": ["get", "name"], "text-font": ["Noto Sans Regular"], "text-size": 11.5, "text-max-angle": 30 }, paint: { "text-color": "#33302a", "text-halo-color": "#ffffff", "text-halo-width": 1.6 } },
    ],
  };
}

function setMode(m) {
  mode = m;
  if (!ready) return;
  const sIdx = SCEN.indexOf(m);
  const help = document.getElementById("mode-help");
  if (m === "robustness") {
    map.setPaintProperty("parcels-fill", "fill-color", ["match", ["get", "rob"], ...ROB.flatMap((r) => [r.code, r.color]), "#ffffff"]);
    map.setPaintProperty("parcels-fill", "fill-opacity", robOpacity());
    ["patches", "patches-line"].forEach((l) => map.setLayoutProperty(l, "visibility", "none"));
    help.textContent = "Parcel colour = in how many scenarios a qualifying patch remains (legend: the bars above the map). Built parcels are faded.";
  } else {
    // nesting: qualifying(conservative) => rob 3; (moderate) => rob >= 2; (aggressive) => rob >= 1
    const minRob = 3 - sIdx;
    map.setPaintProperty("parcels-fill", "fill-color", ["case", [">=", ["get", "rob"], minRob], "#cfe8e0", "#f3f0e9"]);
    map.setPaintProperty("parcels-fill", "fill-opacity", 0.55);
    ["patches", "patches-line"].forEach((l) => {
      map.setFilter(l, ["==", ["get", "s"], sIdx]);
      map.setLayoutProperty(l, "visibility", "visible");
    });
    help.innerHTML = `<span class="sw" style="display:inline-block;background:#f59e0b;vertical-align:-1px"></span> Largest contiguous potentially feasible patch per parcel under <strong>${m}</strong> assumptions. Light green parcels have a qualifying patch (≥ ${nf.format(S.patch_definition.min_patch_m2)} m²).`;
  }
  if (selected) renderReport(selected);
}

function initMap() {
  const protocol = new pmtiles.Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
  const lons = S.overlays.coordinates.map((c) => c[0]);
  const lats = S.overlays.coordinates.map((c) => c[1]);
  map = new maplibregl.Map({
    container: "map",
    style: style(),
    bounds: [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
    fitBoundsOptions: { padding: 10 },
    minZoom: 10.5,
    maxZoom: 18,
    attributionControl: { compact: true },
    cooperativeGestures: window.matchMedia("(max-width: 900px)").matches,
  });
  window.parcelMap = map; // handle for debugging in the console
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
  map.on("styleimagemissing", (e) => {
    if (e.id === "hatch" && !map.hasImage("hatch")) map.addImage("hatch", hatch());
  });
  map.on("load", () => {
    if (!map.hasImage("hatch")) map.addImage("hatch", hatch());
    ready = true;
    // start with the compact attribution collapsed so it does not cover the map on phones
    map.getContainer().querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
    setMode(mode);
    document.querySelectorAll("[data-layer]").forEach((cb) => applyLayer(cb));
    if (selected) highlight(selected);
  });
  for (const l of ["parcels-fill", "parcels-ns"]) {
    map.on("click", l, (e) => {
      const pid = e.features?.[0]?.properties?.pid;
      if (pid) select(pid, { fly: false }).then(() => offerReport());
    });
    map.on("mouseenter", l, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", l, () => (map.getCanvas().style.cursor = ""));
  }
}

const LAYER_GROUPS = {
  flood: ["flood"],
  wetlands: ["wetlands"],
  protected: ["protected", "protected-line"],
  habitat: ["habitat"],
  slope: ["slope"],
  buildings: ["buildings"],
};
function applyLayer(cb) {
  if (!ready) return;
  if (cb.dataset.layer === "slope" && cb.checked && !map.getSource("slope")) {
    // 1.4 MB image: fetched only when first switched on
    map.addSource("slope", { type: "image", url: dataUrl("slope.png"), coordinates: S.overlays.coordinates });
    map.addLayer({ id: "slope", type: "raster", source: "slope", paint: { "raster-opacity": 0.85, "raster-fade-duration": 0 } }, "flood");
  }
  if (cb.dataset.layer === "slope" && !map.getLayer("slope")) return;
  for (const l of LAYER_GROUPS[cb.dataset.layer]) map.setLayoutProperty(l, "visibility", cb.checked ? "visible" : "none");
}

// On narrow screens the report is below the map: after a tap, offer a jump to it.
function offerReport() {
  const btn = document.getElementById("to-report");
  if (!matchMedia("(max-width: 900px)").matches || selected == null) return;
  btn.textContent = `View report: ${D.addr[selected - 1] || "selected parcel"} ↓`;
  btn.hidden = false;
}

function highlight(pid) {
  if (ready) map.setFilter("selected", ["==", ["get", "pid"], pid]);
}

// ---------------------------------------------------------------------------
// parcel report
// ---------------------------------------------------------------------------
async function details() {
  if (!D) D = await fetch(dataUrl("parcels.json")).then((r) => r.json());
  return D;
}

function row(i, k) { return D[k][i]; }

async function select(pid, { fly = true } = {}) {
  await details();
  const i = pid - 1;
  if (D.pid[i] !== pid) return;
  selected = pid;
  highlight(pid);
  if (fly && map) {
    const [x0, y0, x1, y1] = D.bbox[i];
    map.fitBounds([[x0, y0], [x1, y1]], { padding: 40, maxZoom: 17, duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 600 });
  }
  history.replaceState(null, "", `#parcel=${encodeURIComponent(D.loc[i])}`);
  renderReport(pid);
}

function renderReport(pid) {
  const i = pid - 1;
  const r = (k) => row(i, k);
  const rob = ROB_BY_KEY[r("rob")];
  const area = r("area");
  const screened = r("rob") !== "not screened";
  const scenBars = SCEN.map((s) => {
    const k = SCEN_SHORT[s];
    const lg = r(`lg_${k}`), nt = r(`nt_${k}`);
    const ok = lg >= S.patch_definition.min_patch_m2 && r(`el_${k}`);
    return `<span>${s[0].toUpperCase() + s.slice(1)}${mode === s ? " ◂" : ""}</span>
      <div class="track" role="img" aria-label="${s}: largest contiguous patch ${m2(lg)}, net unconstrained ${m2(nt)}, of ${m2(area)} parcel area${ok ? ", qualifies" : ", does not qualify"}">
        <div class="net" style="width:${Math.min(100, (nt / area) * 100)}%"></div>
        <div class="lg" style="width:${Math.min(100, (lg / area) * 100)}%"></div>
        <span class="val">${m2(lg)}${ok ? "" : " · does not qualify"}</span>
      </div>`;
  }).join("");
  const cons = Object.entries(CONS).map(([c, lab]) => [c, lab, r(`c_${c}`)]).filter((x) => x[2] > 0).sort((a, b) => b[2] - a[2]);
  const bind = r("bind");
  const relief = bind !== "none" ? r(`r_${bind}`) : 0;
  const yardRelief = r("r_yard_setback");
  const el = document.getElementById("report");
  el.innerHTML = `
    <h2 class="sr-only">Parcel report</h2>
    <p class="addr">${esc(r("addr") || "No site address")}</p>
    <p class="meta">${esc(r("use"))} · zoning ${esc(r("zone") || "n/a")} · ${m2(area)} (${(area / 4046.86).toFixed(2)} ac) · ID ${esc(r("loc"))}</p>
    <span class="badge"><i style="background:${rob.color}"></i>${esc(rob.label)}</span>
    <p class="claim">${esc(rob.long[0].toUpperCase() + rob.long.slice(1))}.${screened ? "" : " Physical results below are shown for context only."}</p>
    <p class="claim">${r("vac") ? `<strong>Vacant</strong>: no mapped building footprint and no assessor year built.` : (r("conf") ? `<strong>Counted as built</strong> because a structure is mapped or assessed, although the assessor codes it as vacant land (possibly a barn or garage, or an outdated record). Whether the patch is a separate site is unknown — check.` : `<strong>Built</strong>: the patch is unconstrained land beside the existing structure (for example a yard), not a separate building site.`)}</p>

    <h3>Largest contiguous potentially feasible patch</h3>
    <div class="bars">${scenBars}</div>
    <div class="bar-key"><span><i style="background:#f59e0b"></i>largest patch</span><span><i style="background:repeating-linear-gradient(90deg,#d7d2c6 0 2px,#fff 2px 5px)"></i>net unconstrained (baseline)</span><span>bar = whole parcel</span></div>
    <p class="muted">Qualifies = at least ${nf.format(S.patch_definition.min_patch_m2)} m² in one piece outside all mapped hard constraints. A parcel-average screen (naive baseline, moderate) would count ${m2(r("nv_mod"))}. Patches ≥ ${nf.format(S.patch_definition.min_patch_m2)} m² under moderate assumptions: ${r("np_mod")}.</p>

    <h3>What constrains it (moderate)</h3>
    ${cons.length ? `<ul class="cons">${cons.map(([c, lab, a]) => `<li><span>${esc(lab)}</span><span class="mini" aria-hidden="true"><b style="width:${Math.min(100, (a / area) * 100)}%"></b></span><span class="num">${pct(a / area)}</span></li>`).join("")}</ul>
    <p class="muted">Share of parcel area; categories overlap, so shares can add up to more than 100%.</p>` : `<p class="muted">No hard constraint touches this parcel.</p>`}
    <p class="claim">${bind !== "none" && relief > 0 ? `Binding site constraint: <strong>${esc(CONS[bind].toLowerCase())}</strong> — dropping it alone would enlarge the largest patch by ${m2(relief)}.` : "No single site constraint, if dropped alone, enlarges the largest patch."} Dropping the lot-line setback (an assumption, not a site constraint) would add ${m2(yardRelief)}; existing buildings and roads are not treated as removable.</p>

    <h3>Access and servicing</h3>
    <dl class="kv">
      <dt>Boundary near a public road (frontage proxy)</dt><dd>${nf.format(r("front"))} m</dd>
      <dt>Straight-line distance, patch to road</dt><dd>${r("rdist") >= 0 ? `${nf.format(r("rdist"))} m` : "no patch"}</dd>
      <dt>Nearest road</dt><dd>${esc(r("road") || "—")}</dd>
      <dt>In Amherst sewer service area</dt><dd>${pct(r("sewer"))} of area</dd>
      <dt>Mean / 90th percentile slope</dt><dd>${r("slope") == null ? "n/a" : `${(+r("slope")).toFixed(1)}% / ${(+r("slope90")).toFixed(1)}%`}</dd>
      ${r("yb") ? `<dt>Year built (assessor)</dt><dd>${r("yb")}</dd>` : ""}
    </dl>
    <p class="caveat">Screening under stated assumptions — not a legal determination, survey or wetland delineation. Zoning dimensional rules, soils and septic suitability are not modelled.</p>`;
}

// ---------------------------------------------------------------------------
// search (WAI-ARIA combobox with listbox popup)
// ---------------------------------------------------------------------------
function initSearch() {
  const input = document.getElementById("q");
  const list = document.getElementById("q-list");
  let items = [];
  let active = -1;
  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); active = -1; };
  const setActive = (n) => {
    active = n;
    [...list.children].forEach((li, k) => li.setAttribute("aria-selected", k === n ? "true" : "false"));
    if (n >= 0) { input.setAttribute("aria-activedescendant", list.children[n].id); list.children[n].scrollIntoView({ block: "nearest" }); }
  };
  const choose = (n) => { const it = items[n]; if (!it) return; input.value = D.addr[it] || D.loc[it]; close(); select(D.pid[it]); };
  input.addEventListener("focus", details, { once: true });
  input.addEventListener("input", async () => {
    await details();
    const q = input.value.trim().toUpperCase();
    if (q.length < 2) return close();
    items = [];
    for (let i = 0; i < D.pid.length && items.length < 12; i++) {
      if ((D.addr[i] || "").toUpperCase().includes(q) || (D.loc[i] || "").toUpperCase().includes(q)) items.push(i);
    }
    list.innerHTML = items.length
      ? items.map((i, k) => `<li id="opt-${k}" role="option" aria-selected="false" data-k="${k}">${esc(D.addr[i] || "(no address)")}<small>${esc(D.use[i])} · ${m2(D.area[i])}</small></li>`).join("")
      : `<li role="option" aria-disabled="true">No matching parcel</li>`;
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    setActive(-1);
  });
  input.addEventListener("keydown", (e) => {
    if (list.hidden) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive(Math.min(items.length - 1, active + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(Math.max(0, active - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); choose(active >= 0 ? active : 0); }
    else if (e.key === "Escape") { close(); }
  });
  list.addEventListener("mousedown", (e) => { const li = e.target.closest("li[data-k]"); if (li) { e.preventDefault(); choose(+li.dataset.k); } });
  input.addEventListener("blur", () => setTimeout(close, 120));
}

// ---------------------------------------------------------------------------
async function main() {
  S = await fetch(dataUrl("summary.json")).then((r) => r.json());
  fillValues();
  robustBar();
  scenarioTable();
  resultsTable();
  benchTable();
  validationList();
  tornado();
  initSearch();
  document.querySelectorAll('input[name="mode"]').forEach((r) => r.addEventListener("change", () => setMode(r.value)));
  document.querySelectorAll("[data-layer]").forEach((cb) => cb.addEventListener("change", () => applyLayer(cb)));
  document.getElementById("fade-built").addEventListener("change", () => {
    if (ready && mode === "robustness") map.setPaintProperty("parcels-fill", "fill-opacity", robOpacity());
  });
  document.getElementById("to-report").addEventListener("click", (e) => {
    e.currentTarget.hidden = true;
    const rep = document.getElementById("report");
    rep.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    rep.querySelector(".addr")?.setAttribute("tabindex", "-1");
    rep.querySelector(".addr")?.focus({ preventScroll: true });
  });
  await new Promise((res) => (window.pmtiles ? res() : window.addEventListener("load", res, { once: true })));
  initMap();
  const m = location.hash.match(/parcel=([^&]+)/);
  if (m) {
    await details();
    const i = D.loc.indexOf(decodeURIComponent(m[1]));
    if (i >= 0) select(D.pid[i]);
  }
}
main().catch((err) => {
  console.error(err);
  document.getElementById("report").insertAdjacentHTML("beforeend", `<p role="alert">The results could not be loaded (${esc(err.message)}).</p>`);
});
