/* Solar Rankine Lab - interface (all thermodynamics lives in core.js). */
(function () {
"use strict";
const L = Lab, K = L.K;
const WEB = !!window.__WEB__;
const PAGES = WEB ? ["Free Play", "Steady-State Calculator"] : ["Main Menu", "Free Play", "Steady-State Calculator", "Missions", "Comparison", "Validation", "Assumptions"];
const app = { page: "Main Menu", completed: new Set(), fp: Object.assign({}, L.DEFAULT_PLANT), fpTab: "Plant (animated)", fpHour: 12.5,
  missionKey: "rankine", mission: {}, steadyIn: Object.assign({}, L.DEFAULT_STEADY), cmp: { A: null, B: null, presetA: "Baseline", presetB: "Large tank (all-night operation)" },
  disposers: [] };
const dispose = () => { while (app.disposers.length) { try { app.disposers.pop()(); } catch (e) {} } };
const chart = (el, cfg) => { const c = new Chart(el, cfg); app.disposers.push(() => c.destroy()); return c; };
const decimals = (step) => { const s = String(step); return s.includes(".") ? s.split(".")[1].length : 0; };
function fmtNum(v) { const a = Math.abs(v); if (a === 0) return "0"; if (a >= 100) return Math.round(v).toLocaleString("en-US"); if (a >= 0.01) return String(+v.toPrecision(3)); return v.toExponential(2); }
const exp1 = (v) => v.toExponential(1);

// ---------------------------------------------------------------- small components
function metric(label, value, sub) { return h("div", { class: "metric" }, h("div", { class: "ml" }, label), h("div", { class: "mv" }, value), sub ? h("div", { class: "ms" }, sub) : null); }
function callout(level, text) { const ic = { success: "ok", info: "i", warning: "!", error: "x" }[level]; return h("div", { class: "callout " + level }, h("span", { class: "ci" }, ic), h("span", null, text)); }
function table(headers, rows, cls) { return h("div", { class: "tw" }, h("table", { class: cls || "" }, h("thead", null, h("tr", null, headers.map((x) => h("th", null, x)))), h("tbody", null, rows.map((r) => h("tr", null, r.map((c) => (c && c.nodeType ? h("td", null, c) : h("td", { html: esc(c) }))))))));
}
function sliderEl(label, min, max, step, value, onInput, fmt) {
  const d = decimals(step), f = fmt || ((v) => v.toFixed(d));
  const out = h("span", { class: "sv" }, f(value)), inp = h("input", { type: "range", min, max, step, value });
  inp.addEventListener("input", () => { const v = parseFloat(inp.value); out.textContent = f(v); onInput(v); });
  const el = h("label", { class: "slider" }, h("span", { class: "sl" }, label, out), inp);
  el.setValue = (v) => { inp.value = v; out.textContent = f(parseFloat(inp.value)); };
  return el;
}
function toggleEl(label, checked, onChange) {
  const inp = h("input", { type: "checkbox" }); inp.checked = checked; inp.addEventListener("change", () => onChange(inp.checked));
  return h("label", { class: "toggle" }, inp, h("span", { class: "tr" }), h("span", null, label));
}
function tabs(names, key, render) {
  const body = h("div", { class: "tabbody" }), bar = h("div", { class: "tabs", role: "tablist" });
  let cur = names.includes(app[key]) ? app[key] : names[0], tabDisposers = [];
  const show = (n) => { app[key] = cur = n;
    for (const b of bar.children) b.classList.toggle("on", b.textContent === n);
    while (tabDisposers.length) tabDisposers.pop()();
    const before = app.disposers.length; body.replaceChildren(render(n));
    tabDisposers = app.disposers.splice(before).reverse(); };
  names.forEach((n) => bar.append(h("button", { class: "tab", role: "tab", onclick: () => show(n) }, n)));
  const wrap = h("div", null, bar, body);
  wrap.refresh = () => show(cur);
  app.disposers.push(() => { while (tabDisposers.length) tabDisposers.pop()(); });
  show(cur);
  return wrap;
}
function tsData(cycles) {   // T-s diagram series
  let tmin = 0; for (const c of cycles) tmin = Math.min(tmin, c.Tc - 3);
  const dome = L.saturation_dome(tmin, L.T_CRIT_C - 0.3, 60);
  const series = [{ name: "Saturation dome", x: dome.sf.concat(dome.sg.slice().reverse()), y: dome.T.concat(dome.T.slice().reverse()), color: GREY, width: 1.5 }];
  const points = [], cols = [BLUE, ORANGE, AQUA];
  cycles.forEach((c, i) => {
    const path = L.cycle_path(c);
    series.push({ name: c.label || "Cycle", x: path.S, y: path.T, color: cols[i % 3], width: 2.5 });
    const off = [[-14, 16], [8, 16], [8, -8], [8, 16]];
    path.ms.forEach((s, j) => points.push({ x: s, y: path.mt[j], color: cols[i % 3], text: String(j + 1), dx: off[j][0], dy: off[j][1], title: `State ${j + 1}: s = ${s.toFixed(3)} kJ/kg-K, T = ${path.mt[j].toFixed(1)} C` }));
  });
  return { series, points, ylim: [Math.floor(tmin / 20) * 20 < tmin - 2 ? Math.floor((tmin - 4) / 20) * 20 : tmin, 108] };
}
function tsChart(box, cycles, labels, height = 400) {
  cycles.forEach((c, i) => (c.label = labels[i]));
  const d = tsData(cycles);
  return chart(box, { height, xlim: [0.15, 1.0], ylim: d.ylim, xlabel: "Entropy s [kJ/kg-K]", ylabel: "Temperature [C]", series: d.series, points: d.points, hover: false, legend: true, xticks: [0.2, 0.4, 0.6, 0.8, 1.0] });
}
function statesTable(c) {
  const rows = [["pump inlet, saturated liquid", c.s1], ["pump exit, compressed liquid", c.s2], ["turbine inlet", c.s3], ["turbine exit", c.s4]]
    .map(([role, s], i) => [String(i + 1), role, s.T.toFixed(2), s.P.toFixed(1), s.h.toFixed(2), s.s.toFixed(4), s.x === null ? s.phase : (s.phase === "liquid" || s.phase === "vapor" ? s.phase : `two-phase, x = ${s.x.toFixed(3)}`)]);
  return table(["State", "Description", "T [C]", "P [kPa]", "h [kJ/kg]", "s [kJ/kg-K]", "Phase"], rows, "num");
}
function feedbackBox(items) { return h("div", { class: "fb" }, items.map(([l, t]) => callout(l, t))); }
function dateOf(day) { return new Date(2026, 0, day).toLocaleDateString("en-GB", { day: "2-digit", month: "short" }); }

// ---------------------------------------------------------------- parameter panel
const GROUPS = {
  "Site and weather": [["lat", "Latitude [deg N]", -60, 60, 0.5], ["day", "Day of year", 1, 365, 1], ["clearness", "Sky clearness [-]", 0.2, 1.0, 0.05],
    ["T_mean", "Mean ambient temperature [C]", -5, 40, 0.5], ["T_swing", "Daily ambient swing [K]", 0, 25, 0.5]],
  "Collector": [["area", "Collector area [m^2]", 2, 20, 0.5], ["tilt", "Tilt from horizontal [deg]", 0, 80, 1], ["eta0", "Optical efficiency [-]", 0.5, 0.85, 0.01],
    ["a1", "Loss coefficient a1 [W/m^2-K]", 0.5, 5, 0.1], ["a2", "Loss coefficient a2 [W/m^2-K^2]", 0, 0.02, 0.001]],
  "Storage tank": [["tank_L", "Water volume [L]", 100, 2000, 50], ["UA", "Heat-loss coefficient UA [W/K]", 0.5, 10, 0.5], ["T_tank0", "Initial tank temperature [C]", 20, 90, 1]],
  "Power cycle": [["pump_W", "Pump input power at full flow [W]", 5, 100, 1], ["eta_t", "Turbine isentropic efficiency [-]", 0.5, 0.9, 0.01],
    ["eta_p", "Pump isentropic efficiency [-]", 0.4, 0.9, 0.01], ["pinch", "Tank to turbine-inlet temperature drop [K]", 2, 15, 0.5],
    ["approach_cond", "Condenser above ambient [K]", 3, 15, 0.5], ["superheat", "Superheat [K]", 0, 12, 0.5]],
  "Controller": [["T_cut", "Plant starts at tank temperature [C]", 40, 90, 1], ["T_full", "Full flow at tank temperature [C]", 50, 98, 1], ["T_max", "Collector defocuses near [C]", 90, 99, 0.5]],
};
function paramPanel(state, { only, switches = true, onChange, open = true }) {
  const box = h("div", { class: "params" });
  for (const [gname, items] of Object.entries(GROUPS)) {
    const sel = items.filter((i) => !only || only.includes(i[0])); if (!sel.length) continue;
    const det = h("details", { open: (open && (gname === "Collector" || gname === "Power cycle") && !only) || (only && gname === "Collector") ? "" : null }, h("summary", null, gname));
    let cap = null;
    const upd = () => { if (cap) cap.textContent = `${dateOf(state.day)}: ${L.daylight_hours(state.lat, Math.round(state.day)).toFixed(1)} h of daylight`; };
    for (const [n, label, lo, hi, step] of sel) {
      det.append(sliderEl(label, lo, hi, step, state[n], (v) => { state[n] = n === "day" ? Math.round(v) : v; if (n === "day" || n === "lat") upd(); onChange(n); }));
      if (n === "day" && sel.some((i) => i[0] === "lat")) { cap = h("div", { class: "cap" }); det.append(cap); upd(); }
    }
    box.append(det);
  }
  if (switches) box.append(h("details", { open: "" }, h("summary", null, "Equipment operation"),
    toggleEl("Pump running", state.pump_on, (v) => { state.pump_on = v; onChange("pump_on"); }),
    toggleEl("Turbine valve open (off = throttle bypass)", state.valve_open, (v) => { state.valve_open = v; onChange("valve_open"); }),
    toggleEl("Collector exposed to the sun", state.collector_on, (v) => { state.collector_on = v; onChange("collector_on"); })));
  return box;
}
function prep(state) { const p = Object.assign({}, state); let warn = null;
  if (p.T_full <= p.T_cut + 1) { p.T_full = p.T_cut + 1; warn = "Full-flow temperature was raised to stay above the start temperature."; }
  return [p, warn]; }
function kpiRow(r) { const k = r.kpi;
  return h("div", { class: "kpis" }, metric("Daily net work", (k.W_net_Wh / 1000).toFixed(2) + " kWh"), metric("Peak net power", k.peak_W_net.toFixed(0) + " W"),
    metric("Cycle efficiency", (k.eta_cycle * 100).toFixed(1) + " %"), metric("Solar to work", (k.eta_daily * 100).toFixed(1) + " %"),
    metric("Second-law efficiency", (k.eta_II * 100).toFixed(0) + " %"), metric("Run time", k.run_hours.toFixed(1) + " h", k.night_run_hours.toFixed(1) + " h after sunset")); }
function cycleAt(r, k) { const S = r.series, p = r.params; if (S.frac[k] <= 0.01) return null;
  return L.solve_cycle(S.Te[k], S.Tc[k], p.superheat, p.eta_t, p.eta_p, p.valve_open); }

// ---------------------------------------------------------------- plant animation
const heatColour = (T, lo = 20, hi = 98) => { const f = Math.max(0, Math.min(1, (T - lo) / (hi - lo))), a = [37, 125, 224], b = [220, 60, 61];
  return `rgb(${[0, 1, 2].map((i) => Math.round(a[i] + f * (b[i] - a[i]))).join(",")})`; };
function schematic(r, k, qmax) {
  const S = r.series, X = (x) => (x * 80).toFixed(1), Y = (y) => ((8.7 - y) * 80).toFixed(1);
  const P = (a) => a.map(([x, y]) => X(x) + "," + Y(y)).join(" ");
  const frac = S.frac[k], run = frac > 0.01, off = "#c9c9c9", liq = run ? BLUE : off, vap = run ? ORANGE : off, w = (2 + 9 * frac) * 1.5;
  const Ts = S.Ts[k], Qcol = S.Qcol[k], alt = S.alt[k], hour = r.t[k];
  const e = qmax > 0 ? Math.max(0, Math.min(1, Qcol / qmax)) : 0;
  const pipe = (pts, col, wd) => `<polyline points="${P(pts)}" fill="none" stroke="${col}" stroke-width="${wd.toFixed(1)}" stroke-linejoin="round" stroke-linecap="butt"/>`;
  const sx = Math.max(0.3, Math.min(5.6, 0.5 + 4.3 * (hour - 5.0) / 14.0)), sy = 7.0 + 0.6 * Math.sin(Math.max(alt, 0) * Math.PI / 180);
  let g = `<svg viewBox="0 0 864 736" class="plantsvg" role="img" aria-label="Plant schematic at ${hour.toFixed(2)} h solar time">`;
  g += `<polygon points="${P([[0.4, 4.9], [2.8, 6.1], [2.8, 6.6], [0.4, 5.4]])}" fill="rgba(244,114,48,${(0.10 + 0.8 * e).toFixed(2)})" stroke="${INK}" stroke-width="1.5"/>`;
  g += `<rect x="${X(3.4)}" y="${Y(5.2)}" width="${(1.6 * 80)}" height="${(3.0 * 80)}" fill="${heatColour(Ts)}" stroke="${INK}" stroke-width="1.5"/>`;
  g += pipe([[2.8, 5.7], [4.2, 5.7], [4.2, 5.2]], Qcol > 1 ? ORANGE : off, (2 + 7 * e) * 1.5);
  g += pipe([[5.0, 3.7], [6.0, 3.7]], run ? ORANGE : off, w);
  g += pipe([[6.7, 4.4], [6.7, 6.0], [9.4, 6.0], [9.4, 5.1]], vap, w);
  g += pipe([[9.4, 2.9], [9.4, 1.8]], vap, w);
  g += pipe([[8.6, 1.2], [7.1, 1.2]], liq, w);
  g += pipe([[6.7, 1.6], [6.7, 3.0]], liq, w);
  g += `<rect x="${X(6.0)}" y="${Y(4.4)}" width="${1.4 * 80}" height="${1.4 * 80}" fill="rgba(244,114,48,0.12)" stroke="${INK}" stroke-width="1.5"/>`;
  g += `<polygon points="${P([[8.6, 3.6], [10.2, 2.8], [10.2, 5.2], [8.6, 4.4]])}" fill="rgba(37,125,224,0.12)" stroke="${INK}" stroke-width="1.5"/>`;
  g += `<rect x="${X(8.6)}" y="${Y(1.8)}" width="${1.6 * 80}" height="${1.2 * 80}" fill="rgba(0,184,148,0.14)" stroke="${INK}" stroke-width="1.5"/>`;
  g += `<circle cx="${X(6.7)}" cy="${Y(1.2)}" r="28" fill="#fff" stroke="${INK}" stroke-width="1.5"/>`;
  g += `<circle cx="${X(sx)}" cy="${Y(sy)}" r="${alt > 0 ? 17 : 8}" fill="${alt > 0 ? YELLOW : GREY}" stroke="#fff" stroke-width="2"/>`;
  const lbl = (x, y, lines, o = {}) => { const size = (o.size || 19) * 1.35, fill = o.fill || INK;
    return `<text text-anchor="middle" font-size="${size}" fill="${fill}" ${o.bold ? 'font-weight="700"' : ""}>${lines.map((t, i) => `<tspan x="${X(x)}" y="${(parseFloat(Y(y)) + size * 0.35 + (i - (lines.length - 1) / 2) * (size * 1.18)).toFixed(1)}">${esc(t)}</tspan>`).join("")}</text>`; };
  g += lbl(9.4, 4.0, ["Turbine"], { size: 16 }) + lbl(6.7, 1.2, ["P"], { size: 18 });
  g += lbl(1.6, 4.42, ["Collector"], { size: 16, fill: INK2 });
  g += lbl(4.2, 3.7, ["Tank", `${Ts.toFixed(1)} C`], { bold: true, size: 20, fill: "#fff" });
  g += run ? lbl(6.7, 3.7, ["Evaporator", `${S.Te[k].toFixed(1)} C`, `${(S.Qev[k] / 1e3).toFixed(2)} kW in`], { size: 15 }) : lbl(6.7, 3.7, ["Evaporator", "idle"], { size: 15 });
  g += run ? lbl(9.4, 1.2, ["Condenser", `${S.Tc[k].toFixed(1)} C`, `${(S.Qc[k] / 1e3).toFixed(2)} kW out`], { size: 15 }) : lbl(9.4, 1.2, ["Condenser", "idle"], { size: 15 });
  if (run) g += lbl(7.95, 6.4, [`${S.Pe[k].toFixed(0)} kPa`], { size: 18 }) + lbl(7.85, 1.65, [`${S.Pc[k].toFixed(0)} kPa`], { size: 16, fill: INK2 });
  g += lbl(2.6, 8.2, [`Sun ${alt.toFixed(0)} deg, beam ${S.g_eff[k].toFixed(0)} W/m^2`, `collector ${(Qcol / 1e3).toFixed(2)} kW`], { size: 18 });
  g += lbl(6.7, 0.45, [run ? `Pump ${S.Wp[k].toFixed(0)} W` : "Pump off"], { size: 18 });
  g += lbl(9.5, 7.0, [run ? `W_net ${S.Wnet[k].toFixed(0)} W` : "Plant idle"], { bold: true, size: 22 });
  return g + "</svg>";
}
function plantView(r) {
  const S = r.series, N = r.t.length, qmax = Math.max(S.Qcol.reduce((m, v) => Math.max(m, v), 1), 1);
  let k = 0, best = -1; for (let i = 0; i < N; i++) if (S.Wnet[i] > best) { best = S.Wnet[i]; k = i; } if (best <= 0) k = Math.floor(N / 2);
  let timer = null;
  const svgBox = h("div", { class: "schem" }), tsBox = h("div", { class: "tsbox" });
  const lab = h("span", { class: "hl" }), slider = h("input", { type: "range", min: 0, max: N - 1, step: 1, value: k, "aria-label": "Solar time" });
  const play = h("button", { class: "btn" }, "Play");
  let tsc = null;
  const draw = () => { svgBox.innerHTML = schematic(r, k, qmax); lab.textContent = `Solar time ${r.t[k].toFixed(2)} h`; slider.value = k;
    const c = cycleAt(r, k), d = tsData(c ? [Object.assign(c, { label: "Cycle" })] : []);
    const cfg = { height: 400, xlim: [0.15, 1.0], ylim: [0, 108], xlabel: "Entropy s [kJ/kg-K]", ylabel: "Temperature [C]", series: d.series, points: c ? d.points.map((p) => Object.assign(p, {})) : [], hover: false, legend: false, xticks: [0.2, 0.4, 0.6, 0.8, 1.0], title: "Cycle on T-s axes" };
    if (!tsc) tsc = chart(tsBox, cfg); else tsc.update(cfg); };
  const stop = () => { if (timer) { clearInterval(timer); timer = null; play.textContent = "Play"; } };
  play.onclick = () => { if (timer) return stop(); play.textContent = "Pause"; timer = setInterval(() => { k = (k + 3) % N; draw(); }, 90); };
  slider.addEventListener("input", () => { k = parseInt(slider.value, 10); draw(); });
  app.disposers.push(stop);
  draw();
  return h("div", { class: "plant" }, h("div", { class: "cap" }, "Press Play, or drag the slider through the day. Pipe width follows mass flow; the tank colour follows temperature."),
    h("div", { class: "pgrid" }, h("div", null, h("div", { class: "ctitle" }, "Plant (flow width follows mass flow)"), svgBox), tsBox),
    h("div", { class: "pctl" }, play, slider, lab));
}

// ---------------------------------------------------------------- day plots
function dayPlots(r, height = 150) {
  const S = r.series, t = Array.from(r.t), box = h("div", { class: "stack" });
  const shade = []; let start = null;
  for (let i = 0; i < t.length; i++) { const nt = S.alt[i] <= 0; if (nt && start === null) start = t[i]; if ((!nt || i === t.length - 1) && start !== null) { shade.push([start, t[i]]); start = null; } }
  const A = (a, f = 1) => Array.from(a, (v) => v * f), common = { group: "day" + Math.random().toString(36).slice(2), xlim: [0, 24], xticks: [0, 3, 6, 9, 12, 15, 18, 21, 24], shade, height, xfmt: (v) => `${v.toFixed(2)} h solar time` };
  const mk = (title, series, extra) => { const el = h("div"); box.append(el); chart(el, Object.assign({}, common, { title, series: series.map((s) => Object.assign({ x: t }, s)) }, extra)); };
  mk("Beam irradiance on the collector [W/m^2]", [{ name: "Beam on aperture", y: A(S.g_eff), color: BLUE }], { includeZero: true, tipfmt: (v) => v.toFixed(0) });
  mk("Temperatures [C]", [{ name: "Tank", y: A(S.Ts), color: BLUE }, { name: "Evaporator", y: A(S.Te), color: ORANGE }, { name: "Condenser", y: A(S.Tc), color: AQUA }, { name: "Ambient", y: A(S.Ta), color: GREY, dash: "2 4" }], { tipfmt: (v) => v.toFixed(1) });
  mk("Heat rates [kW]", [{ name: "Collector", y: A(S.Qcol, 1e-3), color: BLUE }, { name: "To evaporator", y: A(S.Qev, 1e-3), color: ORANGE }, { name: "Tank loss", y: A(S.Qloss, 1e-3), color: AQUA }], { includeZero: true, tipfmt: (v) => v.toFixed(2) });
  mk("Power [W]", [{ name: "Turbine", y: A(S.Wt), color: BLUE }, { name: "Pump", y: A(S.Wp), color: ORANGE }, { name: "Net", y: A(S.Wnet), color: AQUA }], { includeZero: true, tipfmt: (v) => v.toFixed(0) });
  mk("Working-fluid mass flow [g/s]", [{ name: "Mass flow", y: A(S.mdot, 1e3), color: BLUE }], { includeZero: true, xlabel: "Solar time [h]", tipfmt: (v) => v.toFixed(2), height: height + 22 });
  box.append(h("div", { class: "cap" }, "Shaded bands: night (sun below the horizon). One axis per panel; hover for values."));
  return box;
}

// ---------------------------------------------------------------- free play
function freePlayPage() {
  const root = h("div", { class: "fp" }), ctl = h("aside", { class: "controls" }), res = h("section", { class: "results" });
  const kpiBox = h("div"), fbBox = h("div"); let r = null, tabEl = null, pending = false;
  const compute = () => { const [p, warn] = prep(app.fp);
    try { r = L.simulate(p); } catch (e) { r = null; kpiBox.replaceChildren(callout("error", e.message)); fbBox.replaceChildren(); return; }
    kpiBox.replaceChildren(kpiRow(r)); fbBox.replaceChildren(warn ? callout("warning", warn) : "", feedbackBox(L.feedback(r))); };
  const renderTab = (n) => {
    if (!r) return h("div");
    if (n === "Plant (animated)") return plantView(r);
    if (n === "Day plots") return dayPlots(r, 160);
    if (n === "Cycle") return cycleTab(r);
    if (n === "Energy balance") return energyTab(r);
    return dataTab(r);
  };
  const onChange = () => { if (pending) return; pending = true; requestAnimationFrame(() => { pending = false; compute(); tabEl.refresh(); }); };
  const build = () => { ctl.replaceChildren(h("div", { class: "chead2" }, h("h3", null, "Controls"), h("button", { class: "btn ghost", onclick: () => { Object.assign(app.fp, L.DEFAULT_PLANT); build(); onChange(); } }, "Reset all controls")), paramPanel(app.fp, { onChange })); };
  build(); compute();
  tabEl = tabs(["Plant (animated)", "Day plots", "Cycle", "Energy balance", "Data"], "fpTab", renderTab);
  res.append(h("h1", null, "Free Play"), kpiBox, fbBox, tabEl);
  root.append(ctl, res);
  return root;
}
function cycleTab(r) {
  const S = r.series, p = r.params, wrap = h("div"), body = h("div");
  const lab = h("div", { class: "hl" });
  const sl = sliderEl("Solar time [h]", 0, 24, 0.25, app.fpHour, (v) => { app.fpHour = v; draw(); }, (v) => v.toFixed(2));
  function draw() {
    let k = 0, b = 1e9; r.t.forEach((v, i) => { if (Math.abs(v - app.fpHour) < b) { b = Math.abs(v - app.fpHour); k = i; } });
    const c = cycleAt(r, k); dispose2();
    if (!c) { body.replaceChildren(callout("info", "The plant is idle at this time (tank below the start temperature, pump off, or lift too small).")); return; }
    const m = S.mdot[k], Tsrc = S.Ts[k] - p.pinch, g = L.entropy_generation(c, Tsrc, S.Ta[k]);
    const cbox = h("div"), side = h("div", { class: "side" });
    body.replaceChildren(h("div", { class: "two" }, cbox, side), statesTable(c));
    cycChart = chart(cbox, Object.assign({}, { height: 400, xlim: [0.15, 1.0], xlabel: "Entropy s [kJ/kg-K]", ylabel: "Temperature [C]", hover: false, legend: true, xticks: [0.2, 0.4, 0.6, 0.8, 1.0] },
      (() => { const d = tsData([Object.assign(c, { label: `Cycle at ${r.t[k].toFixed(2)} h` })]); return { series: d.series, points: d.points, ylim: d.ylim }; })()));
    side.append(metric("Net power", S.Wnet[k].toFixed(0) + " W"), metric("Thermal efficiency / Carnot", `${(c.eta_th * 100).toFixed(2)} % / ${(c.carnot() * 100).toFixed(1)} %`),
      metric("Second-law efficiency", (L.second_law_efficiency(c, Tsrc, S.Ta[k]) * 100).toFixed(0) + " %"), h("div", { class: "cap" }, "Entropy generation rate by device [W/K]"),
      barRows(["pump", "evaporator", "turbine", "condenser"].map((n) => [n, g[n] * m * 1000]), "W/K"));
  }
  let cycChart = null; const dispose2 = () => { if (cycChart) { cycChart.destroy(); cycChart = null; } };
  app.disposers.push(dispose2);
  wrap.append(sl, body); draw();
  return wrap;
}
function energyTab(r) {
  const k = r.kpi, b = r.balance, kwh = (v) => v / 1000, box = h("div", { class: "wf" });
  const items = [{ lab: "Beam on aperture", kind: "abs", v: kwh(k.E_incident_Wh) }, { lab: "Collector losses", kind: "rel", v: -kwh(k.E_incident_Wh - k.E_collector_Wh) },
    { lab: "Collector heat", kind: "tot" }, { lab: "Tank losses", kind: "rel", v: -kwh(k.E_loss_Wh) }, { lab: "Stored in tank", kind: "rel", v: -kwh(b.dU_tank_Wh) },
    { lab: "Heat to evaporator", kind: "tot" }, { lab: "Pump work", kind: "rel", v: kwh(k.W_pump_Wh) }, { lab: "Heat rejected", kind: "rel", v: -kwh(k.Q_condenser_Wh) },
    { lab: "Turbine work", kind: "tot" }, { lab: "Pump work", kind: "rel", v: -kwh(k.W_pump_Wh) }, { lab: "Net work", kind: "tot" }];
  const wrap = h("div", null, box, h("div", { class: "cap" }, "Energy over the day [kWh]. Blue bars are running totals, orange adds energy, grey removes it."),
    table(["Check", "Value"], [["Tank: dU - (Q_col - Q_evap - Q_loss) [Wh]", exp1(b.resid_tank_Wh)], ["Cycle: Q_evap - Q_cond - W_net [Wh]", exp1(b.resid_cycle_Wh)],
      ["Collector heat: solver vs trapezoid [Wh]", (b.trap_E_col_Wh - k.E_collector_Wh).toFixed(2)]], "num"));
  const draw = () => waterfall(box, items, "Energy over the day [kWh]"); draw();
  const ro = new ResizeObserver(() => draw()); ro.observe(box); app.disposers.push(() => ro.disconnect());
  return wrap;
}
function dataTab(r) {
  const S = r.series, keys = Object.keys(S), rows = [];
  for (let i = 0; i < r.t.length; i += 6) rows.push([r.t[i].toFixed(2)].concat(keys.map((q) => (Number.isFinite(S[q][i]) ? +S[q][i].toFixed(3) : "") + "")));
  const csv = () => { let s = "t_h," + keys.join(",") + "\n"; for (let i = 0; i < r.t.length; i++) s += r.t[i].toFixed(4) + "," + keys.map((q) => S[q][i]).join(",") + "\n";
    const a = h("a", { href: URL.createObjectURL(new Blob([s], { type: "text/csv" })), download: "solar_rankine_day.csv" }); document.body.append(a); a.click(); a.remove(); };
  return h("div", null, h("button", { class: "btn", onclick: csv }, "Download full data (CSV)"), h("div", { class: "cap" }, "Every 30 minutes shown; the CSV has every 5 minutes."), table(["hour"].concat(keys), rows, "num small"));
}

// ---------------------------------------------------------------- steady-state calculator
function steadyPage() {
  const d = L.DEFAULT_STEADY, root = h("div"), out = h("div");
  const fields = [["hours_sun", "Hours of direct sun [h]", 0.5, 24, 0.5], ["sun_elevation", "Sun elevation [deg]", 0, 90, 1], ["tilt", "Collector tilt [deg]", 0, 90, 1], ["area", "Collector area [m^2]", 0.5, 100, 0.5],
    ["eta_t", "Turbine efficiency", 0.3, 1, 0.01], ["dni", "Beam irradiance [W/m^2]", 0, 1100, 10], ["T_amb", "Ambient temperature [C]", -20, 50, 1], ["Te", "Evaporator temperature [C]", 20, 95, 0.5],
    ["superheat", "Superheat [K]", 0, 20, 0.5], ["eta_p", "Pump efficiency", 0.2, 1, 0.01], ["Tc_day", "Condenser, day [C]", 0, 60, 0.5], ["Tc_night", "Condenser, night [C]", 0, 60, 0.5],
    ["pump_W", "Pump input power [W]", 1, 1000, 1], ["eta_store", "Storage efficiency (0 = none)", 0, 1, 0.05]];
  const inputs = {};
  const form = h("form", { class: "nform", onsubmit: (e) => { e.preventDefault(); calc(); } },
    fields.map(([n, lab, lo, hi, st]) => { const i = h("input", { type: "number", min: lo, max: hi, step: st, value: app.steadyIn[n], required: "" }); inputs[n] = i; return h("label", { class: "nf" }, h("span", null, lab), i); }),
    h("div", { class: "nfbtn" }, h("button", { class: "btn primary", type: "submit" }, "Calculate"), h("button", { class: "btn ghost", type: "button", onclick: () => { for (const n in inputs) inputs[n].value = d[n]; calc(); } }, "Reset")));
  function calc() {
    const v = {}; for (const [n, , lo, hi] of fields) { let q = parseFloat(inputs[n].value); if (!Number.isFinite(q)) q = d[n]; q = Math.max(lo, Math.min(hi, q)); inputs[n].value = q; v[n] = q; }
    app.steadyIn = Object.assign({}, d, v); out.replaceChildren(); dispose();
    let o; try { o = L.steady_day_night(app.steadyIn); } catch (e) { out.append(callout("error", e.message)); return; }
    const cs = [o.day], ls = ["Daytime"]; if (o.night) { cs.push(o.night); ls.push("Night"); }
    const cbox = h("div"), side = h("div", { class: "side" });
    out.append(h("div", { class: "kpis five" }, metric("W_out (net, daytime)", o.W_out.toFixed(1) + " W"), metric("Thermal efficiency", (o.day.eta_th * 100).toFixed(2) + " %"), metric("Collector heat", o.Q_sol.toFixed(0) + " W"),
      metric("Energy per day", o.E_total.toFixed(0) + " Wh"), metric("Night run", o.t_night.toFixed(1) + " h")),
      o.flow_limited_by === "pump" ? callout("info", `Flow set by pump power; the sun has ${o.surplus.toFixed(0)} W to spare, which charges the store.`) : callout("warning", "Flow limited by sunlight: the pump could move more fluid than the sun can boil."),
      h("div", { class: "two" }, cbox, side), h("h3", null, "State points (daytime cycle)"), statesTable(o.day));
    tsChart(cbox, cs, ls, 400);
    side.append(metric("Turbine work", o.day.wt.toFixed(2) + " kJ/kg"), metric("Pump work", o.day.wp.toFixed(2) + " kJ/kg"), metric("Heat in", o.day.qin.toFixed(1) + " kJ/kg"),
      metric("Carnot limit", (o.carnot * 100).toFixed(1) + " %", `cycle reaches ${(o.day.eta_th / o.carnot * 100).toFixed(0)} % of it`));
  }
  root.append(h("h1", null, "Steady-State Calculator"), h("p", null, "Quick design point: state the sun exposure and sun angle, get the net work output ", h("b", null, "W_out"),
    ". The pump input power sets the mass flow; if the sun cannot boil that flow, the flow drops to what the sun supplies."), form, out);
  calc();
  return root;
}

// ---------------------------------------------------------------- missions
function missionsPage() {
  const root = h("div"), left = h("div", { class: "mleft" }), right = h("div", { class: "mright" });
  const sel = h("select", { onchange: () => { app.missionKey = sel.value; navigate("Missions"); } }, Object.entries(L.MISSIONS).map(([k, m]) => h("option", { value: k, selected: k === app.missionKey ? "" : null }, m.title)));
  const key = app.missionKey, m = L.MISSIONS[key], st = app.mission[key] = app.mission[key] || { choice: {}, res: null };
  for (const [n, v] of Object.entries(m.knobs)) if (st.choice[n] === undefined) st.choice[n] = v[3];
  const sliders = {};
  const run = () => { dispose(); right.replaceChildren(); try { st.res = L.missionRun(key, st.choice); st.err = null; } catch (e) { st.res = null; st.err = e.message; } renderResult(); };
  left.append(h("label", { class: "sel" }, h("span", null, "Mission"), sel), h("h2", null, m.title), h("p", null, m.brief), h("p", null, h("b", null, "Objective. "), m.objective));
  for (const [n, [lab, lo, hi, def, step]] of Object.entries(m.knobs)) { sliders[n] = sliderEl(lab, lo, hi, step, st.choice[n], (v) => { st.choice[n] = v; }); left.append(sliders[n]); }
  left.append(h("button", { class: "btn primary", onclick: run }, "Run mission"),
    h("details", { class: "hint" }, h("summary", null, "Hint and worked solution"), h("p", null, m.hint),
      h("button", { class: "btn", onclick: () => { for (const [n, v] of Object.entries(m.knobs)) { st.choice[n] = m.solution[n] !== undefined ? m.solution[n] : v[3]; sliders[n].setValue(st.choice[n]); } run(); } }, "Load a worked solution")));
  function renderResult() {
    right.replaceChildren();
    if (st.err) { right.append(callout("error", st.err + " Choose a lower evaporator temperature.")); return; }
    if (!st.res) { right.append(callout("info", "Set your operating conditions and press Run mission.")); return; }
    const res = st.res, cr = m.evaluate(res), done = cr.every((c) => c[3]);
    if (done) { app.completed.add(key); right.append(callout("success", "Mission complete: every criterion is met.")); }
    else { app.completed.delete(key); right.append(callout("error", `Not yet: ${cr.filter((c) => !c[3]).length} of ${cr.length} criteria failed.`)); }
    updateCompleted();
    right.append(table(["Criterion", "Result", "Requirement", "Status"], cr.map((c) => [c[0], c[1], c[2], h("span", { class: c[3] ? "ok" : "bad" }, c[3] ? "met" : "not met")]), "crit"));
    const rating = L.engineering_rating(res, m.kind);
    right.append(h("div", { class: "kpis auto" }, Object.entries(rating).map(([k, v]) => metric(k, fmtNum(v)))));
    if (m.kind === "steady") { const box = h("div"); right.append(box); tsChart(box, [res.day], ["Your cycle"], 380); }
    else { right.append(feedbackBox(L.feedback(res)));
      right.append(tabs(["Day plots", "Plant animation"], "missionTab", (n) => (n === "Day plots" ? dayPlots(res, 150) : plantView(res)))); }
  }
  root.append(h("h1", null, "Missions"), h("div", { class: "mgrid" }, left, right));
  if (st.res || st.err) renderResult(); else right.append(callout("info", "Set your operating conditions and press Run mission."));
  return root;
}

// ---------------------------------------------------------------- comparison
const PRESETS = { "Baseline": {}, "Large collector, small tank": { area: 14, tank_L: 200 },
  "Large tank (all-night operation)": { area: 14, tank_L: 900, pump_W: 22, T_cut: 60, T_full: 78 }, "High-efficiency (hot tank)": { T_cut: 82, T_full: 92, area: 12, eta_t: 0.85 },
  "Winter day": { day: 355 }, "Cloudy day": { clearness: 0.5 } };
function comparePage() {
  const root = h("div"), out = h("div"); let pending = false;
  const only = ["area", "tilt", "tank_L", "pump_W", "T_cut", "T_full", "superheat", "eta_t", "day", "clearness"];
  const cases = {};
  const update = () => { if (pending) return; pending = true; requestAnimationFrame(() => { pending = false; render(); }); };
  const col = (id) => { const c = h("div", { class: "ccol" }); cases[id] = c;
    const fill = () => { if (!app.cmp[id]) app.cmp[id] = Object.assign({}, L.DEFAULT_PLANT, PRESETS[app.cmp["preset" + id]]);
      const sel = h("select", { onchange: () => { app.cmp["preset" + id] = sel.value; app.cmp[id] = Object.assign({}, L.DEFAULT_PLANT, PRESETS[sel.value]); fill(); update(); } },
        Object.keys(PRESETS).map((n) => h("option", { value: n, selected: n === app.cmp["preset" + id] ? "" : null }, n)));
      c.replaceChildren(h("h3", null, "Case " + id), h("label", { class: "sel" }, h("span", null, "Preset"), sel), paramPanel(app.cmp[id], { only, switches: false, onChange: update })); };
    fill(); return c; };
  const render = () => {
    dispose(); out.replaceChildren(); let a, b;
    try { a = L.simulate(prep(app.cmp.A)[0]); b = L.simulate(prep(app.cmp.B)[0]); } catch (e) { out.append(callout("error", e.message)); return; }
    const keys = [["W_net_Wh", "Net work [Wh]", 0], ["eta_cycle", "Cycle efficiency", 4], ["eta_daily", "Solar to work", 4], ["eta_II", "Second-law efficiency", 3], ["E_collector_Wh", "Collector heat [Wh]", 0],
      ["E_evaporator_Wh", "Heat to evaporator [Wh]", 0], ["Q_condenser_Wh", "Heat rejected [Wh]", 0], ["mass_circulated_kg", "Mass circulated [kg]", 0], ["peak_W_net", "Peak net power [W]", 0],
      ["Ts_max", "Peak tank temperature [C]", 1], ["Pe_max", "Peak evaporator pressure [kPa]", 0], ["run_hours", "Run time [h]", 1], ["night_run_hours", "Run time after sunset [h]", 1]];
    const f = (v, d) => (Number.isFinite(v) ? v.toFixed(d) : "-");
    out.append(table(["Quantity", "Case A", "Case B", "B - A"], keys.map(([k, lab, d]) => [lab, f(a.kpi[k], d), f(b.kpi[k], d), f(b.kpi[k] - a.kpi[k], d)]), "num"));
    const grid = h("div", { class: "cmpgrid" }); out.append(grid);
    const grp = "cmp" + Math.random().toString(36).slice(2), cfg = (title, ya, yb, ex) => { const el = h("div"); grid.append(el);
      chart(el, Object.assign({ title, xlim: [0, 24], xticks: [0, 4, 8, 12, 16, 20, 24], height: 220, series: ya.concat(yb), xfmt: (v) => v.toFixed(2) + " h", xlabel: "Solar time [h]" }, ex)); };
    const A = (q, s = 1) => Array.from(q, (v) => v * s);
    const ser = (r, name, col, key, scale, dash) => ({ name, x: Array.from(r.t), y: A(r.series[key], scale), color: col, dash });
    cfg("Tank temperature [C]", [ser(a, "Case A", BLUE, "Ts", 1)], [ser(b, "Case B", ORANGE, "Ts", 1)], { tipfmt: (v) => v.toFixed(1), group: grp });
    cfg("Evaporator (solid) and condenser (dashed) pressure [kPa]", [ser(a, "Case A", BLUE, "Pe", 1), ser(a, "Case A condenser", BLUE, "Pc", 1, "5 4")], [ser(b, "Case B", ORANGE, "Pe", 1), ser(b, "Case B condenser", ORANGE, "Pc", 1, "5 4")], { tipfmt: (v) => v.toFixed(0), group: grp, legend: false });
    cfg("Working-fluid mass flow [g/s]", [ser(a, "Case A", BLUE, "mdot", 1e3)], [ser(b, "Case B", ORANGE, "mdot", 1e3)], { includeZero: true, tipfmt: (v) => v.toFixed(2), group: grp, legend: false });
    cfg("Net power [W]", [ser(a, "Case A", BLUE, "Wnet", 1)], [ser(b, "Case B", ORANGE, "Wnet", 1)], { includeZero: true, tipfmt: (v) => v.toFixed(0), group: grp, legend: false });
    for (const [nm, r] of [["A", a], ["B", b]]) out.append(h("details", { class: "fbd" }, h("summary", null, "Performance feedback: Case " + nm), feedbackBox(L.feedback(r))));
  };
  root.append(h("h1", null, "Comparison Mode"), h("p", null, "Run two operating cases on the same day and compare pressure, temperature, mass flow, energy transfer, work and efficiency."),
    h("div", { class: "cgrid" }, col("A"), col("B")), out);
  render();
  return root;
}

// ---------------------------------------------------------------- validation
function validationPage() {
  const root = h("div"), body = h("div", null, callout("info", "Running the checks..."));
  root.append(h("h1", null, "Validation"), h("p", null, "Each check below is executed now, in your browser. Tolerances are stated next to the measured value. Checks against CoolProp compare with reference values that the Python version of the lab computed offline with the CoolProp equation of state."), body);
  setTimeout(() => {
    const cs = LabValidation.runAll(), n = cs.filter((c) => c.passed).length, ts = LabValidation.toleranceStudy();
    body.replaceChildren(h("div", { class: "kpis three" }, metric("Checks passed", `${n} / ${cs.length}`)),
      table(["Category", "Check", "Value", "Tolerance", "Result"], cs.map((c) => [c.category, c.name, c.value.toExponential(2), c.tolerance.toExponential(1), h("span", { class: c.passed ? "ok" : "bad" }, c.passed ? "pass" : "FAIL")]), "num val"),
      h("div", { class: "cap" }, "The tank energy residual (about 1e-15) is partly closed by construction, because the energy terms are integrated by the same solver step as the tank temperature. The independent tests are the analytic cool-down, the trapezoid comparisons, the periodic-day check, the property and cycle checks against CoolProp, and the entropy-generation checks."),
      h("h3", null, "Solver tolerance study"), table(["rtol", "Daily net work [Wh]", "RHS evaluations"], ts.map((t) => [t.rtol.toExponential(0), t.W_net_Wh.toFixed(4), String(t.nfev)]), "num"));
  }, 30);
  return root;
}

// ---------------------------------------------------------------- assumptions
const ASSUMPTIONS = window.__ASSUMPTIONS__ || "";
function md(s) { return s.split(/\n\s*\n/).filter(Boolean).map((p) => h("p", { html: esc(p.trim()).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`(.+?)`/g, "<code>$1</code>") })); }
function assumptionsPage() { return h("div", { class: "prose" }, h("h1", null, "Assumptions and governing equations"), md(ASSUMPTIONS)); }

// ---------------------------------------------------------------- menu
function menuPage() {
  const cards = [["Free Play", "Change any parameter, flip the pump, close the turbine valve, and watch a full day unfold with an animated plant."],
    ["Steady-State Calculator", "Type in sun hours and sun angle, get net work output W_out for a design point."],
    ["Missions", "Five engineering challenges: efficiency, power, night operation, tank heating and an integrated design."],
    ["Comparison", "Put two operating cases side by side: pressure, temperature, mass flow, work and efficiency."],
    ["Validation", "Mass, energy and second-law checks, plus solver-tolerance tests, run live."],
    ["Assumptions", "Every modelling assumption and governing equation in one place."]];
  return h("div", null, h("h1", null, "Solar Rankine Lab"),
    h("p", { class: "lead", html: "A virtual laboratory for a <b>solar-driven R-134a (Freon) Rankine power plant</b>. Sunlight heats a collector, a storage tank carries the heat past sunset, and a pump, evaporator, turbine and condenser turn it into work. You operate the plant, the thermodynamics decides what happens." }),
    h("div", { class: "cards" }, cards.map(([n, t]) => h("div", { class: "card" }, h("h3", null, n), h("p", null, t), h("button", { class: "btn", onclick: () => navigate(n) }, "Open " + n)))),
    h("hr"), h("p", { html: "<b>How the lab works.</b> The thermodynamic engine is separate from this interface. Missions are scored by engineering quantities such as efficiency, temperature limits and conservation residuals, never by arbitrary points. Warnings appear when equipment limits are exceeded. This is the standalone browser edition: it runs entirely on your computer with no installation, using R-134a property tables generated from the CoolProp equation of state." }));
}

// ---------------------------------------------------------------- shell
const main = document.getElementById("main"), nav = document.getElementById("nav"), done = document.getElementById("done");
function updateCompleted() { if (WEB) { done.style.display = "none"; return; } const names = Object.keys(L.MISSIONS).filter((k) => app.completed.has(k)).map((k) => L.MISSIONS[k].title.split(":")[0]); done.textContent = "Missions completed: " + (names.length ? names.join(", ") : "none yet"); }
function navigate(page) {
  dispose(); app.page = page;
  for (const b of nav.children) b.classList.toggle("on", b.dataset.page === page);
  const fn = { "Main Menu": menuPage, "Free Play": freePlayPage, "Steady-State Calculator": steadyPage, "Missions": missionsPage, "Comparison": comparePage, "Validation": validationPage, "Assumptions": assumptionsPage }[page];
  main.replaceChildren(fn()); main.scrollTop = 0; window.scrollTo(0, 0); updateCompleted();
  try { history.replaceState(null, "", "#" + encodeURIComponent(page)); } catch (e) {}
}
PAGES.forEach((p) => nav.append(h("button", { class: "navb", "data-page": p, onclick: () => navigate(p) }, p)));
let start = WEB ? "Free Play" : "Main Menu"; try { const q = decodeURIComponent(location.hash.slice(1)); if (PAGES.includes(q)) start = q; } catch (e) {}
window.__lab = { app, navigate };
navigate(start);
})();
