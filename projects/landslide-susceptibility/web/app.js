// Landslide Susceptibility — preliminary prototype. All numbers come from data/summary.json (D13).
// The 5 m ranks arrive as one lossless WebP tile set; each colour channel is decoded as its own `raster-dem`
// source (custom encoding) and coloured by a `color-relief` layer, so the threshold slider only changes a paint
// property. Channel value: 0 outside the domain, 1 not ranked, 102 - r for the top r % of hillslope area.
// Decoding factors: the wanted channel 1, the other two 1/256 and 1/65536. MapLibre also packs the colour-stop
// elevations with these factors (dividing by the smallest one), so a zero factor breaks the ramp; with these,
// stops at half-integers round-trip exactly and the other channels add at most 0.40, below the 0.5 margin
// between classes.
import * as maplibregl from "https://cdn.jsdelivr.net/npm/maplibre-gl@6.11.1/dist/maplibre-gl.mjs";

const dataUrl = (f) => new URL(`data/${f}`, location.href).href;
const NB = " ";
const pct = (x, d = 0) => `${(100 * x).toFixed(d)}${NB}%`;
const fmtInt = (x) => Math.round(x).toLocaleString("en-US");

const VIEWS = {
  final: { layer: "rank-final", channel: [1 / 256, 1, 1 / 65536], series: "oof_lr", label: "Terrain model",
    note: "Map: the model fitted to all watersheds (the screening product). The numbers are its held-out estimate." },
  oof: { layer: "rank-oof", channel: [1, 1 / 256, 1 / 65536], series: "oof_lr", label: "Terrain model, held-out",
    note: "Map: each watershed ranked by a model that never saw it — exactly the ranking the numbers were measured on." },
  slope: { layer: "rank-slope", channel: [1 / 256, 1 / 65536, 1], series: "slope", label: "Slope alone",
    note: "Map: hillslopes ranked by slope alone, the simplest screening rule, for comparison." },
};
const RAMP = ["#fdcc8a", "#fc8d59", "#e34a33", "#b30000"];
let S, map, ready = false, view = "final", k = 10;
// overlay toggles: desired state is kept here and applied once the style has loaded (toggles may be used earlier)
const TOGGLES = { "t-sites": "sites", "t-nt": "nt", "t-huc": "huc", "t-aoa": "aoa" };
const layerOn = { sites: true, nt: true, huc: false, aoa: false };
let aoaLoaded = false;

async function applyLayers() {
  if (!ready) return;
  for (const [layer, on] of Object.entries(layerOn)) map.setLayoutProperty(layer, "visibility", on ? "visible" : "none");
  if (layerOn.aoa && !aoaLoaded) {
    aoaLoaded = true;
    map.getSource("aoa").setData(await (await fetch(dataUrl("outside_aoa.geojson"))).json());
  }
}

function get(obj, path) { return path.split(".").reduce((o, p) => (o == null ? o : o[p]), obj); }

function fillText() {
  for (const el of document.querySelectorAll("[data-v]")) {
    const v = get(S, el.dataset.v);
    el.textContent = el.dataset.fmt === "int" ? fmtInt(v) : String(v);
  }
  const a = S.cells_auc;
  const ci = (m) => `${m.value.toFixed(2)} (${m.ci95[0].toFixed(2)}–${m.ci95[1].toFixed(2)})`;
  document.getElementById("auc-lr").textContent = ci(a.lr.within_huc);
  document.getElementById("auc-slope").textContent = ci(a.slope.within_huc);
  const d = S.gbm_minus_lr_cells.auc_rain_stratified;
  document.getElementById("gbm-vs-lr").textContent = d.ci95[0] > 0
    ? "detectably better and is shown as a comparison"
    : `not detectably better (difference ${d.value >= 0 ? "+" : ""}${d.value.toFixed(3)}, 95${NB}% interval ${d.ci95[0].toFixed(3)} to +${d.ci95[1].toFixed(3)}), so the simpler model is used`;
  for (const id of ["aoa-share", "aoa-share2"]) document.getElementById(id).textContent = pct(S.m6.outside_aoa_share, 1);
  document.getElementById("stable-share").textContent = pct(S.m6.top10_stable_share);
  const i = S.per_k.k_pct.indexOf(10);
  const m = S.per_k.oof_lr, s = S.per_k.slope;
  document.getElementById("headline").innerHTML =
    `In watersheds the model never saw, the top <strong>10${NB}%</strong> of hillslope area held ` +
    `<strong>${pct(m.capture[i])}</strong> of mapped Helene initiation sites (95${NB}% interval ${pct(m.ci95_low[i])}–${pct(m.ci95_high[i])}); ` +
    `ranking by slope alone captured <strong>${pct(s.capture[i])}</strong> (${pct(s.ci95_low[i])}–${pct(s.ci95_high[i])}).`;
}

function reliefColor(kk) {
  const lo = 101.5 - kk, hi = 101;
  const stops = RAMP.flatMap((c, j) => [lo + (hi - lo) * j / (RAMP.length - 1), c]);
  return ["interpolate", ["linear"], ["elevation"], 0, "rgba(0,0,0,0)", lo - 0.001, "rgba(0,0,0,0)", ...stops];
}

function updateReadout() {
  const v = VIEWS[view], i = S.per_k.k_pct.indexOf(k);
  const ser = S.per_k[v.series];
  const other = v.series === "slope" ? ["Terrain model", S.per_k.oof_lr] : ["Slope alone", S.per_k.slope];
  const area = S.hillslope_km2 * k / 100;
  document.getElementById("readout").innerHTML =
    `<p>Flagged: top ${k}${NB}% of hillslope area = <strong>${area.toFixed(0)}${NB}km²</strong>.</p>` +
    `<p>${v.series === "slope" ? "Slope alone (a fixed rule, nothing fitted):" : "Terrain model, scored in held-out watersheds:"}</p>` +
    `<p class="big">${pct(ser.capture[i])} of mapped initiation sites</p>` +
    `<p class="muted">95${NB}% interval ${pct(ser.ci95_low[i])}–${pct(ser.ci95_high[i])} · ` +
    `${(ser.capture[i] / (k / 100)).toFixed(1)}× the share expected by chance (${k}${NB}%)</p>` +
    `<p>${other[0]} at the same threshold: ${pct(other[1].capture[i])} (${pct(other[1].ci95_low[i])}–${pct(other[1].ci95_high[i])}).</p>`;
  document.getElementById("k-out").textContent = k;
  document.getElementById("ramp-k").textContent = `top ${k}${NB}%`;
  document.getElementById("k").setAttribute("aria-valuetext",
    `Top ${k} percent of hillslope area flagged; ${pct(ser.capture[i])} of mapped initiation sites captured in held-out watersheds`);
  document.getElementById("view-note").textContent = v.note;
  drawCurve();
}

function applyMap() {
  if (!ready) return;
  for (const [key, v] of Object.entries(VIEWS)) {
    map.setLayoutProperty(v.layer, "visibility", key === view ? "visible" : "none");
  }
  map.setPaintProperty(VIEWS[view].layer, "color-relief-color", reliefColor(k));
}

// ---------- capture curve (SVG, drawn from summary.json) ----------
function drawCurve() {
  const svg = document.getElementById("curve");
  const W = 360, H = 230, L = 44, R = 12, T = 12, B = 34;
  const x = (kk) => L + (kk / 30) * (W - L - R);
  const y = (c) => T + (1 - c) * (H - T - B);
  const ks = S.per_k.k_pct;
  const line = (arr) => ks.map((kk, i) => `${i ? "L" : "M"}${x(kk).toFixed(1)},${y(arr[i]).toFixed(1)}`).join("");
  const band = (s) => line(s.ci95_high) + ks.slice().reverse().map((kk, j) =>
    `L${x(kk).toFixed(1)},${y(s.ci95_low[ks.length - 1 - j]).toFixed(1)}`).join("") + "Z";
  const P = S.per_k;
  const last = ks.length - 1;
  let g = "";
  for (const c of [0, 0.25, 0.5, 0.75, 1]) {
    g += `<line x1="${L}" x2="${W - R}" y1="${y(c)}" y2="${y(c)}" stroke="#e6e1d6"/>` +
      `<text x="${L - 6}" y="${y(c) + 4}" text-anchor="end" font-size="11" fill="#4a5059">${100 * c}%</text>`;
  }
  for (const kk of [0, 10, 20, 30]) {
    g += `<text x="${x(kk)}" y="${H - B + 16}" text-anchor="middle" font-size="11" fill="#4a5059">${kk}%</text>`;
  }
  g += `<text x="${(L + W - R) / 2}" y="${H - 4}" text-anchor="middle" font-size="11" fill="#4a5059">flagged share of hillslope area</text>`;
  g += `<path d="M${x(0)},${y(0)}L${x(30)},${y(0.3)}" stroke="#8a8f96" stroke-dasharray="2 3"/>`;
  g += `<path d="${band(P.slope)}" fill="#4a5059" opacity="0.15"/><path d="${band(P.oof_lr)}" fill="#b30000" opacity="0.15"/>`;
  g += `<path d="${line(P.slope.capture)}" fill="none" stroke="#4a5059" stroke-width="2"/>`;
  g += `<path d="${line(P.oof_gbm.capture)}" fill="none" stroke="#7a3e00" stroke-width="1.5" stroke-dasharray="5 3"/>`;
  g += `<path d="${line(P.oof_lr.capture)}" fill="none" stroke="#b30000" stroke-width="2.5"/>`;
  g += `<line x1="${x(k)}" x2="${x(k)}" y1="${T}" y2="${H - B}" stroke="#1f2328" stroke-width="1"/>`;
  g += `<text x="${x(30) - 2}" y="${y(P.oof_lr.capture[last]) - 6}" text-anchor="end" font-size="11" fill="#b30000" font-weight="600">model</text>`;
  g += `<text x="${x(30) - 2}" y="${y(P.slope.capture[last]) + 14}" text-anchor="end" font-size="11" fill="#4a5059" font-weight="600">slope alone</text>`;
  g += `<text x="${x(30) - 2}" y="${y(0.3) + 14}" text-anchor="end" font-size="10" fill="#6b6f76">chance</text>`;
  svg.innerHTML = g;
}

function curveTable() {
  const P = S.per_k;
  let h = "<table><thead><tr><th>Top k % area</th><th>Model</th><th>Gradient boosting</th><th>Slope alone</th></tr></thead><tbody>";
  for (const kk of [1, 5, 10, 15, 20, 25, 30]) {
    const i = P.k_pct.indexOf(kk);
    h += `<tr><td>${kk}%</td><td>${pct(P.oof_lr.capture[i])}</td><td>${pct(P.oof_gbm.capture[i])}</td><td>${pct(P.slope.capture[i])}</td></tr>`;
  }
  document.getElementById("curve-table").innerHTML = h + "</tbody></table>";
}

// ---------- map ----------
function hatchImage() {
  const n = 8, data = new Uint8Array(n * n * 4);
  for (let yy = 0; yy < n; yy++) for (let xx = 0; xx < n; xx++) {
    if ((xx + yy) % n === 0 || (xx + yy) % n === 1) {
      const o = (yy * n + xx) * 4; data[o] = 107; data[o + 1] = 111; data[o + 2] = 118; data[o + 3] = 200;
    }
  }
  return { width: n, height: n, data };
}

function crossHatchImage() {
  const n = 8, data = new Uint8Array(n * n * 4);
  for (let yy = 0; yy < n; yy++) for (let xx = 0; xx < n; xx++) {
    if (xx === yy || xx === n - 1 - yy) {
      const o = (yy * n + xx) * 4; data[o] = 61; data[o + 1] = 63; data[o + 2] = 68; data[o + 3] = 220;
    }
  }
  return { width: n, height: n, data };
}

async function initMap() {
  const protocol = new pmtiles.Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
  const counties = await (await fetch(dataUrl("counties.geojson"))).json();
  const [x0, y0, x1, y1] = S.bounds_lonlat;
  const susc = `pmtiles://${dataUrl("susceptibility.pmtiles")}`;
  const dem = (rgb) => ({ type: "raster-dem", url: susc, tileSize: 256, encoding: "custom",
    redFactor: rgb[0], greenFactor: rgb[1], blueFactor: rgb[2], baseShift: 0 });
  const relief = (id, src) => ({ id, type: "color-relief", source: src, layout: { visibility: "none" },
    paint: { "color-relief-color": reliefColor(k), "color-relief-opacity": 0.9, "resampling": "nearest" } });
  map = new maplibregl.Map({
    container: "map",
    bounds: [[x0, y0], [x1, y1]],
    fitBoundsOptions: { padding: 12 },
    maxZoom: 16, minZoom: 8,
    cooperativeGestures: matchMedia("(max-width: 900px)").matches,
    attributionControl: { compact: true },
    style: {
      version: 8,
      sources: {
        hs: { type: "raster", url: `pmtiles://${dataUrl("hillshade.pmtiles")}`, tileSize: 256,
          attribution: "Hillshade: USGS 3DEP lidar · Inventory: NC Geological Survey · Rainfall: NOAA MRMS" },
        s_oof: dem(VIEWS.oof.channel), s_final: dem(VIEWS.final.channel), s_slope: dem(VIEWS.slope.channel),
        counties: { type: "geojson", data: counties },
        nt: { type: "geojson", data: dataUrl("not_tested.geojson") },
        huc: { type: "geojson", data: dataUrl("huc12.geojson") },
        sites: { type: "geojson", data: dataUrl("initiations.geojson") },
        aoa: { type: "geojson", data: { type: "FeatureCollection", features: [] } }, // loaded on first toggle
      },
      layers: [
        { id: "bg", type: "background", paint: { "background-color": "#f7f5f0" } },
        { id: "hs", type: "raster", source: "hs", paint: { "raster-opacity": 1 } },
        relief("rank-oof", "s_oof"), relief("rank-final", "s_final"), relief("rank-slope", "s_slope"),
        { id: "nt", type: "fill", source: "nt", paint: { "fill-pattern": "hatch", "fill-opacity": 0.8 } },
        { id: "aoa", type: "fill", source: "aoa", layout: { visibility: "none" },
          paint: { "fill-pattern": "xhatch", "fill-opacity": 0.9 } },
        { id: "huc", type: "line", source: "huc", layout: { visibility: "none" },
          paint: { "line-color": "#2b4a6b", "line-width": 1.4 } },
        { id: "counties", type: "line", source: "counties", paint: { "line-color": "#1f2328", "line-width": 1.6 } },
        { id: "sites", type: "circle", source: "sites",
          paint: { "circle-color": "#1f2328", "circle-stroke-color": "#ffffff", "circle-stroke-width": 0.8,
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 1.4, 14, 4] } },
      ],
    },
  });
  map.on("error", (e) => console.error("map error:", e.error && e.error.message));
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
  map.on("styleimagemissing", (e) => {
    if (e.id === "hatch" && !map.hasImage("hatch")) map.addImage("hatch", hatchImage());
    if (e.id === "xhatch" && !map.hasImage("xhatch")) map.addImage("xhatch", crossHatchImage());
  });
  map.on("load", () => { ready = true; applyMap(); applyLayers(); });
}

function bind() {
  for (const r of document.querySelectorAll("input[name=view]")) {
    r.addEventListener("change", () => { view = r.value; updateReadout(); applyMap(); });
  }
  const slider = document.getElementById("k");
  const set = (v) => { k = Math.max(1, Math.min(30, v)); slider.value = k; updateReadout(); applyMap(); };
  slider.addEventListener("input", () => set(+slider.value));
  document.getElementById("k-dec").addEventListener("click", () => set(k - 1));
  document.getElementById("k-inc").addEventListener("click", () => set(k + 1));
  for (const [id, layer] of Object.entries(TOGGLES)) {
    document.getElementById(id).addEventListener("change", (e) => { layerOn[layer] = e.target.checked; applyLayers(); });
  }
}

// ---------- before / after sites (static images; the range input clips the after image) ----------
let SITES, site;

function showSite(id) {
  site = SITES.sites.find((x) => x.id === id);
  const src = (f) => dataUrl(`sites/${f}`);
  const before = document.getElementById("img-before"), after = document.getElementById("img-after");
  before.src = src(`${id}_before.jpg`);
  after.src = src(`${id}_after.jpg`);
  before.alt = `${site.title}: imagery before Helene (2020–2023)`;
  after.alt = `${site.title}: imagery after Helene (spring 2025)`;
  document.getElementById("img-top10").src = src(`${id}_top10.png`);
  const svg = document.getElementById("site-points");
  svg.innerHTML = site.points.map((p) => {
    const missed = p.held_out_rank === 0 || p.held_out_rank > 30;
    return missed
      ? `<circle cx="${p.fx}" cy="${p.fy}" r="0.007" fill="none" stroke="#fff" stroke-width="0.006"/><circle cx="${p.fx}" cy="${p.fy}" r="0.007" fill="none" stroke="#1f2328" stroke-width="0.003"/>`
      : `<circle cx="${p.fx}" cy="${p.fy}" r="0.0055" fill="#1f2328" stroke="#fff" stroke-width="0.002"/>`;
  }).join("");
  const missed = site.points.filter((p) => p.held_out_rank === 0 || p.held_out_rank > 30).length;
  document.getElementById("site-cap").textContent =
    `${site.title} (${site.county}). ${site.points.length} mapped natural initiation sites, ${missed} of them outside the ` +
    `held-out top 30 %; ${pct(site.top10_share_of_hillslope)} of its hillslopes are in the final top 10 %; mean 72-h ` +
    `rainfall ${Math.round(site.rain_mean_mm)} mm. Before: ${site.before_credit}. After: ${site.after_credit}. ` +
    `Area 2 km × 2 km, north up.`;
}

function setReveal(v) {
  document.getElementById("img-after").style.clipPath = `inset(0 0 0 ${v}%)`;
  document.getElementById("compare-line").style.left = `calc(${v}% - 1px)`;
  document.getElementById("reveal").setAttribute("aria-valuetext", `Line at ${v} percent from the left; after-Helene image to the right`);
}

async function initSites() {
  SITES = await (await fetch(dataUrl("sites/sites.json"))).json();
  const pick = document.getElementById("site-pick");
  SITES.sites.forEach((x, j) => {
    const l = document.createElement("label");
    l.innerHTML = `<input type="radio" name="site" value="${x.id}" ${j ? "" : "checked"}> <span>${x.title}</span>`;
    l.querySelector("input").addEventListener("change", () => showSite(x.id));
    pick.appendChild(l);
  });
  const r = document.getElementById("reveal");
  r.addEventListener("input", () => setReveal(r.value));
  document.getElementById("t-site-top10").addEventListener("change", (e) => { document.getElementById("img-top10").hidden = !e.target.checked; });
  document.getElementById("t-site-pts").addEventListener("change", (e) => { document.getElementById("site-points").style.display = e.target.checked ? "" : "none"; });
  setReveal(r.value);
  showSite(SITES.sites[0].id);
}

async function main() {
  S = await (await fetch(dataUrl("summary.json"))).json();
  fillText();
  curveTable();
  bind();
  updateReadout();
  initSites();
  await initMap();
}
main();
