// ===================================================================== stage 3: animations and analysis windows
const PH = { liquid: "#257de0", "two-phase": "#8e5cd9", vapor: "#f47230", superheated: "#c8332f", off: "#c9ced6", water: "#3aa0c8" };
const phaseOf = (s) => (s.phase === "vapor" ? (s.x === null || s.x === undefined ? "superheated" : "vapor") : s.phase === "two-phase" ? "two-phase" : s.x === 1 ? "vapor" : s.phase);
function phaseText(s) {
  if (s.phase === "two-phase") return `two-phase, x = ${s.x.toFixed(3)}`;
  if (s.phase === "liquid") return s.x === 0 ? "saturated liquid (x = 0)" : "compressed liquid";
  return s.x === 1 ? "saturated vapor (x = 1)" : "superheated vapor";
}
const tempColour = (T, lo = 15, hi = 98) => { const f = Math.max(0, Math.min(1, (T - lo) / (hi - lo))), a = [56, 132, 214], b = [214, 48, 49], m = [246, 196, 70];
  const mix = (p, q, u) => p.map((v, i) => Math.round(v + u * (q[i] - v)));
  const c = f < 0.5 ? mix(a, m, f * 2) : mix(m, b, (f - 0.5) * 2); return `rgb(${c.join(",")})`; };

/* One plant SVG built once; update(i) moves it to output sample i without rebuilding (animations keep running). */
function plantScene(r) {
  const c = r.config, si = r.info, n = r.balance.layers;
  const W = 1100, H = 630, NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.append(e); return e; };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "plantsvg2", role: "img", "aria-label": "Animated plant" });
  const sky = el("rect", { x: 0, y: 0, width: W, height: 250, fill: "#dcecff" }, svg);
  el("rect", { x: 0, y: 250, width: W, height: H - 250, fill: "#f7f8fa" }, svg);
  el("line", { x1: 0, x2: W, y1: 250, y2: 250, stroke: "#cfd6de" }, svg);
  // ---- sun
  const sunG = el("g", {}, svg), sun = el("circle", { r: 20, fill: "#f2b705" }, sunG);
  for (let i = 0; i < 8; i++) el("line", { x1: 0, y1: -28, x2: 0, y2: -36, stroke: "#f2b705", "stroke-width": 3, transform: `rotate(${i * 45})`, class: "ray" }, sunG);
  // ---- collector: size follows the area, angle follows tracking or tilt
  const colW = 60 + 7 * c.area, colX = 70, colY = 205;
  const colG = el("g", {}, svg);
  const colPanel = el("rect", { x: -colW / 2, y: -7, width: colW, height: 14, rx: 2, fill: "#f47230", stroke: "#191919", "stroke-width": 1.5 }, colG);
  const nPanels = Math.max(1, Math.round(c.area / 2));
  for (let i = 1; i < nPanels; i++) el("line", { x1: -colW / 2 + colW * i / nPanels, x2: -colW / 2 + colW * i / nPanels, y1: -7, y2: 7, stroke: "#7a3412", "stroke-width": 1 }, colG);
  const beam = el("line", { stroke: "#f2b705", "stroke-width": 3, "stroke-dasharray": "6 6", class: "flow", opacity: 0.9 }, svg);
  el("line", { x1: colX + colW / 2, x2: colX + colW / 2, y1: colY, y2: 250, stroke: "#8a8a8a", "stroke-width": 4 }, svg);
  el("rect", { x: 8, y: 8, width: 360, height: 28, rx: 8, fill: "rgba(255,255,255,0.85)" }, svg);
  const colLab = el("text", { x: 18, y: 27, class: "slab" }, svg);
  // ---- tank: height and width follow the volume, layers coloured by temperature
  const tH = 120 + 0.08 * c.tank_L, tW = 70 + 0.03 * c.tank_L, tX = 330 - tW / 2, tY = 555 - tH;
  const insW = Math.min(14, 1 + (G.thicknessOf(c) || 1) * 0.9);
  el("rect", { x: tX - insW, y: tY - insW, width: tW + 2 * insW, height: tH + 2 * insW, rx: 10, fill: "#e8dcc4", stroke: "#a99671" }, svg);
  const layerRects = [];
  for (let j = 0; j < n; j++) layerRects.push(el("rect", { x: tX, y: tY + tH * j / n, width: tW, height: tH / n + 0.5, fill: "#888" }, svg));
  el("rect", { x: tX, y: tY, width: tW, height: tH, rx: 4, fill: "none", stroke: "#191919", "stroke-width": 1.5 }, svg);
  const tankTop = el("text", { x: tX + tW / 2, y: tY + 18, "text-anchor": "middle", class: "tlab" }, svg);
  const tankBot = el("text", { x: tX + tW / 2, y: tY + tH - 8, "text-anchor": "middle", class: "tlab" }, svg);
  const tankLab = el("text", { x: tX + tW / 2, y: 585, "text-anchor": "middle", class: "slab" }, svg);
  const lossTxt = el("text", { x: tX - insW - 6, y: tY + tH / 2, "text-anchor": "end", class: "slab small" }, svg);
  // collector loop (water): tank bottom -> collector, collector -> tank top
  const water = (d) => el("path", { d, fill: "none", "stroke-width": 5, "stroke-linecap": "round", class: "flow" }, svg);
  const cIn = water(`M ${tX} ${tY + tH - 15} H ${colX + 10} V ${colY + 30}`);
  const cOut = water(`M ${colX + colW - 10} ${colY - 8} V 150 H ${tX + tW / 2} V ${tY}`);
  // evaporator water loop: tank top -> evaporator -> tank bottom
  const eX = 470, eY = 330, eW = 120, eH = 90;
  const eIn = water(`M ${tX + tW} ${tY + 20} H ${eX} V ${eY + 20}`);
  const eOut = water(`M ${eX} ${eY + eH - 15} H ${tX + tW + 20} V ${tY + tH - 15} H ${tX + tW}`);
  el("rect", { x: eX, y: eY, width: eW, height: eH, rx: 6, fill: "#fff3ea", stroke: "#191919", "stroke-width": 1.5 }, svg);
  el("path", { d: `M ${eX + 15} ${eY + 25} q 15 -12 30 0 t 30 0 t 30 0 M ${eX + 15} ${eY + 45} q 15 -12 30 0 t 30 0 t 30 0 M ${eX + 15} ${eY + 65} q 15 -12 30 0 t 30 0 t 30 0`, fill: "none", stroke: "#c8332f", "stroke-width": 2, opacity: 0.6 }, svg);
  el("text", { x: eX + eW / 2, y: eY - 8, "text-anchor": "middle", class: "dlab" }, svg).textContent = "Evaporator";
  // ---- refrigerant loop
  const tbX = 820, tbY = 300, pX = 660, pY = 525, cX = 840, cY = 480, cW = 140, cH = 80;
  const ref = (d) => el("path", { d, fill: "none", "stroke-linecap": "round", "stroke-linejoin": "round", class: "flow" }, svg);
  const r23 = ref(`M ${pX} ${pY - 26} V ${eY + eH - 20} H ${eX + eW}`);                                     // pump -> evaporator (liquid)
  const r3 = ref(`M ${eX + eW} ${eY + 25} H ${tbX - 50} V ${tbY - 10}`);                                     // evaporator -> turbine
  const r4 = ref(`M ${tbX + 50} ${tbY + 40} H ${cX + 40} V ${cY}`);                                       // turbine -> condenser
  const r1 = ref(`M ${cX} ${pY} H ${pX + 26}`);                                                      // condenser -> pump
  // turbine (trapezoid) with a spinning rotor
  el("path", { d: `M ${tbX - 50} ${tbY - 25} L ${tbX + 50} ${tbY - 55} L ${tbX + 50} ${tbY + 55} L ${tbX - 50} ${tbY + 25} Z`, fill: "#eef4fc", stroke: "#191919", "stroke-width": 1.5 }, svg);
  const rotor = el("g", { transform: `translate(${tbX} ${tbY})` }, svg), rotorSpin = el("g", { class: "spin" }, rotor);
  for (let i = 0; i < 6; i++) el("path", { d: "M 0 0 L 6 -30 L -6 -30 Z", fill: "#257de0", transform: `rotate(${i * 60})` }, rotorSpin);
  el("circle", { r: 7, fill: "#191919" }, rotor);
  el("text", { x: tbX + 10, y: tbY - 64, "text-anchor": "middle", class: "dlab" }, svg).textContent = "Turbine";
  const gen = el("text", { x: tbX - 10, y: tbY + 80, "text-anchor": "middle", class: "wlab" }, svg);
  // condenser with a fan
  el("rect", { x: cX, y: cY, width: cW, height: cH, rx: 6, fill: "#e6f7f1", stroke: "#191919", "stroke-width": 1.5 }, svg);
  const fan = el("g", { transform: `translate(${cX + cW - 28} ${cY + cH / 2})` }, svg), fanSpin = el("g", { class: "spin" }, fan);
  for (let i = 0; i < 3; i++) el("ellipse", { cx: 0, cy: -11, rx: 5, ry: 11, fill: "#0b9b77", transform: `rotate(${i * 120})` }, fanSpin);
  el("text", { x: cX + cW / 2 - 18, y: cY - 8, "text-anchor": "middle", class: "dlab" }, svg).textContent = "Condenser";
  const heatOut = el("text", { x: cX + 8, y: cY + cH / 2 - 4, class: "slab small" }, svg);
  // pump with a spinning impeller
  el("circle", { cx: pX, cy: pY, r: 26, fill: "#fff", stroke: "#191919", "stroke-width": 1.5 }, svg);
  const imp = el("g", { transform: `translate(${pX} ${pY})` }, svg), impSpin = el("g", { class: "spin" }, imp);
  for (let i = 0; i < 4; i++) el("path", { d: "M 0 0 Q 8 -10 4 -20", fill: "none", stroke: "#257de0", "stroke-width": 3, transform: `rotate(${i * 90})` }, impSpin);
  el("text", { x: pX, y: pY + 44, "text-anchor": "middle", class: "dlab" }, svg).textContent = "Pump";
  const pumpLab = el("text", { x: pX, y: pY + 60, "text-anchor": "middle", class: "slab small" }, svg);
  // state tags 1-4
  const tag = (x, y, anchor) => { const g = el("g", {}, svg); const bg = el("rect", { rx: 6, fill: "rgba(255,255,255,0.92)", stroke: "#cfd6de" }, g); const t = el("text", { x, y, class: "stag", "text-anchor": anchor }, g); return { g, bg, t, x, y, anchor }; };
  const tags = [tag(pX + 60, pY + 48, "start"), tag(pX + 20, eY + eH - 10, "start"), tag(eX + 90, eY - 125, "start"), tag(tbX + 75, tbY - 40, "start")];
  const dots = [[pX + 34, pY], [pX, pY - 35], [tbX - 50, tbY - 18], [tbX + 55, tbY + 40]].map(([x, y], i) => { const g = el("g", {}, svg); el("circle", { cx: x, cy: y, r: 10, fill: "#191919" }, g);
    el("text", { x, y: y + 4, "text-anchor": "middle", class: "snum" }, g).textContent = String(i + 1); return g; });
  el("rect", { x: W - 330, y: 8, width: 322, height: 28, rx: 8, fill: "rgba(16,35,63,0.78)" }, svg);
  const clockTxt = el("text", { x: W - 18, y: 27, "text-anchor": "end", class: "clock" }, svg);
  const idle = el("text", { x: 760, y: 455, "text-anchor": "middle", class: "idle" }, svg);

  function setTag(T, s, i, title) {
    const lines = s ? [`${i}  ${title}`, `T ${s.T.toFixed(1)} C   P ${s.P.toFixed(0)} kPa`, `h ${s.h.toFixed(1)} kJ/kg   s ${s.s.toFixed(4)} kJ/kg-K`, phaseText(s)] : [`${i}  ${title}`, "idle"];
    T.t.replaceChildren(...lines.map((l, j) => { const ts = document.createElementNS(NS, "tspan"); ts.setAttribute("x", T.x); ts.setAttribute("dy", j ? 15 : 0); if (!j) ts.setAttribute("font-weight", "700"); ts.textContent = l; return ts; }));
    const bb = T.t.getBBox ? (() => { try { return T.t.getBBox(); } catch (e) { return null; } })() : null;
    if (bb && bb.width) { T.bg.setAttribute("x", bb.x - 6); T.bg.setAttribute("y", bb.y - 4); T.bg.setAttribute("width", bb.width + 12); T.bg.setAttribute("height", bb.height + 8); }
  }
  function stroke(p, colour, width, speed) {
    p.setAttribute("stroke", colour); p.setAttribute("stroke-width", width);
    p.setAttribute("stroke-dasharray", speed > 0 ? "10 8" : "none");
    p.style.animationDuration = speed > 0 ? `${Math.max(0.25, 2.2 / speed).toFixed(2)}s` : "0s";
    p.style.animationPlayState = speed > 0 ? "running" : "paused";
  }
  function spin(g, rate) { g.style.animationDuration = rate > 0 ? `${Math.max(0.15, 1.8 / rate).toFixed(2)}s` : "0s"; g.style.animationPlayState = rate > 0 ? "running" : "paused"; }

  function update(i) {
    const S = r.series, alt = S.alt[i], clock = S.clock[i], cyc = G.cycleAtSample(r, i), run = !!cyc;
    // sky and sun
    const day = Math.max(0, Math.min(1, (alt + 6) / 20));
    sky.setAttribute("fill", `rgb(${Math.round(30 + 190 * day)},${Math.round(40 + 196 * day)},${Math.round(80 + 175 * day)})`);
    const frac = (clock - si.sunrise) / (si.sunset - si.sunrise);
    const sx = 120 + Math.max(-0.1, Math.min(1.1, frac)) * (W - 240), sy = 240 - Math.max(-2, alt) * 2.6;
    sunG.setAttribute("transform", `translate(${sx.toFixed(1)} ${sy.toFixed(1)})`); sunG.style.opacity = alt > 0 ? 1 : 0.15;
    // collector angle: tracking faces the sun; fixed shows the tilt
    const ang = c.tracking ? (alt > 0 ? -(90 - alt) * (sx < colX + colW / 2 ? -1 : 1) : 0) : -c.tilt;
    colG.setAttribute("transform", `translate(${colX + colW / 2} ${colY}) rotate(${ang.toFixed(1)})`);
    const e = Math.max(0, Math.min(1, S.Qcol[i] / Math.max(1, 600 * c.area)));
    colPanel.setAttribute("fill", S.G[i] > 1 ? `rgba(244,114,48,${(0.25 + 0.75 * e).toFixed(2)})` : "#9aa3b2");
    if (alt > 0 && S.G[i] > 1) { beam.setAttribute("x1", sx); beam.setAttribute("y1", sy); beam.setAttribute("x2", colX + colW / 2); beam.setAttribute("y2", colY); beam.style.display = ""; } else beam.style.display = "none";
    const inc = G.incidenceDeg(S.cos_i[i]);
    colLab.textContent = `Collector ${c.area} m^2: ${(S.Qcol[i] / 1000).toFixed(2)} kW` + (alt > 0 ? (c.tracking ? " (tracking)" : `, incidence ${Number.isFinite(inc) ? inc.toFixed(0) : "-"} deg`) : "");
    // tank layers
    for (let j = 0; j < n; j++) layerRects[j].setAttribute("fill", tempColour(r.layers[j][i]));
    tankTop.textContent = n > 1 ? `top ${r.layers[0][i].toFixed(1)} C` : `${r.layers[0][i].toFixed(1)} C`;
    tankBot.textContent = n > 1 ? `bottom ${r.layers[n - 1][i].toFixed(1)} C` : "";
    tankLab.textContent = `Tank ${c.tank_L} L, ${n > 1 ? "stratified" : "uniform"}: ${S.E_tank_kWh[i] >= 0 ? "+" : ""}${S.E_tank_kWh[i].toFixed(2)} kWh stored`;
    lossTxt.textContent = `loss ${S.Qloss[i].toFixed(0)} W`;
    const mc = S.Qcol[i] > 1 ? 1 : 0;
    stroke(cIn, mc ? tempColour(r.layers[n - 1][i]) : PH.off, 5, mc ? 1 : 0);
    stroke(cOut, mc ? tempColour(Math.min(99, r.layers[n - 1][i] + S.Qcol[i] / (0.015 * c.area * 4186))) : PH.off, 5, mc ? 1 : 0);
    const ev = S.Qev[i] > 1 ? Math.min(2.5, S.Qev[i] / 1500) : 0;
    stroke(eIn, ev ? tempColour(r.layers[0][i]) : PH.off, 5, ev);
    stroke(eOut, ev ? tempColour(c.Te + 5) : PH.off, 5, ev);
    // refrigerant: colour by phase, width by mass flow, dash speed by mass flow
    const mf = S.mdot[i] * 1000, w = 3 + Math.min(9, mf / 2.2), sp = run ? Math.max(0.3, mf / 6) : 0;
    if (run) {
      stroke(r23, PH[phaseOf(cyc.s2)], w, sp); stroke(r3, PH[phaseOf(cyc.s3)], w, sp); stroke(r4, PH[phaseOf(cyc.s4)], w, sp); stroke(r1, PH[phaseOf(cyc.s1)], w, sp);
    } else for (const p of [r23, r3, r4, r1]) stroke(p, PH.off, 4, 0);
    spin(rotorSpin, run && c.valve_open ? S.Wt[i] / 60 : 0); spin(impSpin, run ? S.Wp[i] / 10 : 0); spin(fanSpin, run ? S.Qc[i] / 800 : 0);
    gen.textContent = run ? `W_net ${S.Wnet[i].toFixed(0)} W` : "";
    heatOut.replaceChildren(...[run ? `${(S.Qc[i] / 1000).toFixed(2)} kW out` : "idle", `air ${S.Ta[i].toFixed(1)} C`].map((l, j) => { const ts = document.createElementNS(NS, "tspan"); ts.setAttribute("x", cX + 8); ts.setAttribute("dy", j ? 15 : 0); ts.textContent = l; return ts; }));
    pumpLab.textContent = run ? `${S.Wp[i].toFixed(0)} W, ${mf.toFixed(1)} g/s` : "off";
    const names = ["Pump inlet", "Evaporator inlet", "Turbine inlet", "Turbine exit"];
    [cyc && cyc.s1, cyc && cyc.s2, cyc && cyc.s3, cyc && cyc.s4].forEach((s, j) => setTag(tags[j], s, j + 1, names[j]));
    dots.forEach((d) => (d.style.opacity = run ? 1 : 0.35));
    clockTxt.textContent = `${clockStr(clock)} solar time  (${r.t[i].toFixed(1)} h after sunrise)`;
    idle.textContent = run ? "" : (r.config.pump_on ? (r.layers[0][i] < r.config.T_start ? `Idle: tank top ${r.layers[0][i].toFixed(1)} C is below the ${r.config.T_start} C start` : "Idle: lift too small") : "Pump off");
  }
  return { svg, update };
}

let playTimer = null;
function stopPlay() { if (playTimer) { clearInterval(playTimer); playTimer = null; } }
function timeControl(r, onIdx) {
  const H = span(r), last = Math.max(0, r.t.findIndex((v) => v > H + 1e-9) - 1) || r.t.length - 1;
  let i = Math.min(defaultIdx(r), last);
  const lab = h("span", { class: "hl" }), sl = h("input", { type: "range", min: 0, max: last, step: 1, value: i, "aria-label": "Time of day" });
  const play = h("button", { class: "btn" }, "Play");
  const set = (k) => { i = k; app.hourIdx = k; sl.value = k; lab.textContent = `${clockStr(r.info.sunrise + r.t[k])} solar time`; onIdx(k); };
  play.onclick = () => { if (playTimer) { stopPlay(); play.textContent = "Play"; return; } play.textContent = "Pause"; playTimer = setInterval(() => set((i + 1) % (last + 1)), 110); };
  sl.addEventListener("input", () => set(parseInt(sl.value, 10)));
  app.disposers.push(() => { stopPlay(); });
  const box = h("div", { class: "pctl" }, play, sl, lab);
  box.start = () => set(i);
  return box;
}

function plantTab(r) {
  const sc = plantScene(r), wrap = h("div", { class: "plantwrap" }), tsBox = h("div", { class: "tsmini" });
  let tsc = null;
  const legend = h("div", { class: "phaselegend" }, [["liquid", "liquid"], ["two-phase", "two-phase (wet)"], ["vapor", "saturated vapor"], ["superheated", "superheated vapor"], ["water", "water loops (colour = temperature)"]]
    .map(([k, t]) => h("span", null, h("i", { style: `background:${PH[k] || "linear-gradient(90deg,#3884d6,#f6c446,#d63031)"}` }), t)));
  const tc = timeControl(r, (k) => { sc.update(k); const cyc = G.cycleAtSample(r, k); const cfg = tsConfig(cyc ? [cyc] : [], ["Now"], 300, true); if (!tsc) tsc = chart(tsBox, cfg); else tsc.update(cfg); });
  wrap.append(h("div", { class: "cap" }, "Press Play to run the day. Pipe colour shows the phase, pipe width and dash speed show the mass flow, the turbine, pump and condenser fan spin with their power, the collector grows with its area and the tank with its volume."),
    h("div", { class: "pgrid" }, h("div", { class: "scene" }, sc.svg), h("div", null, tsBox, h("div", { class: "cap" }, "Live T-s diagram at the selected time; dashed lines are the ideal (isentropic) pump and turbine."))),
    tc, legend);
  setTimeout(() => tc.start(), 0);
  return wrap;
}

// ---------------------------------------------------------------- T-s diagram with isentropic references
function tsConfig(cycles, labels, height, compact) {
  let tmin = 0; for (const c of cycles) tmin = Math.min(tmin, c.Tc - 3);
  const dome = L.saturation_dome(tmin, L.T_CRIT_C - 0.3, 60);
  const series = [{ name: "Saturation dome", x: dome.sf.concat(dome.sg.slice().reverse()), y: dome.T.concat(dome.T.slice().reverse()), color: GREY, width: 1.5 }];
  const points = [], cols = [BLUE, ORANGE, AQUA, "#8e5cd9"];
  cycles.forEach((c, i) => {
    const path = L.cycle_path(c), col = cols[i % cols.length];
    series.push({ name: labels[i] || "Cycle", x: path.S, y: path.T, color: col, width: 2.5 });
    // isentropic references: 1 -> 2s (vertical) and 3 -> 4s (vertical)
    const h4s = c.s3.h - c.wt / Math.max(c.eta_t, 1e-9);
    series.push({ name: i === 0 ? "Isentropic (ideal)" : "", x: [c.s3.s, c.s3.s], y: [c.s3.T, c.Tc], color: col, width: 1.2, dash: "4 4" });
    series.push({ name: "", x: [c.s1.s, c.s1.s], y: [c.s1.T, c.s1.T + (c.s2.T - c.s1.T) * 0.6], color: col, width: 1.2, dash: "4 4" });
    void h4s;
    const off = [[-14, 16], [8, 16], [8, -8], [8, 16]];
    path.ms.forEach((s, j) => points.push({ x: s, y: path.mt[j], color: col, text: compact && i ? "" : String(j + 1), dx: off[j][0], dy: off[j][1],
      title: `State ${j + 1}: T ${path.mt[j].toFixed(1)} C, s ${s.toFixed(4)} kJ/kg-K` }));
    if (!compact) points.push({ x: c.s3.s, y: c.Tc, color: col, text: "4s", dx: -24, dy: 16, title: "Turbine exit if it were isentropic" });
  });
  return { height, xlim: [0.15, 1.0], ylim: [Math.min(0, Math.floor((tmin - 4) / 20) * 20), 108], xlabel: "Entropy s [kJ/kg-K]", ylabel: "Temperature [C]",
    series, points, hover: false, legend: !compact, xticks: [0.2, 0.4, 0.6, 0.8, 1.0], title: compact ? "Cycle at this time" : null };
}
function tsTab(r) {
  const box = h("div"), cbox = h("div"), info = h("div", { class: "side" }); let cc = null;
  const tc = timeControl(r, (k) => {
    const cyc = G.cycleAtSample(r, k), S = r.series;
    const cfg = tsConfig(cyc ? [cyc] : [], [`Cycle at ${clockStr(r.info.sunrise + r.t[k])}`], 420, false);
    if (!cc) cc = chart(cbox, cfg); else cc.update(cfg);
    if (!cyc) { info.replaceChildren(callout("info", "The plant is idle at this time.")); return; }
    const carnot = cyc.carnot(), h4s = cyc.s3.h - cyc.wt / cyc.eta_t, h2s = cyc.s1.h + cyc.wp * cyc.eta_p;
    info.replaceChildren(
      metric("Thermal efficiency / Carnot", `${(cyc.eta_th * 100).toFixed(2)} % / ${(carnot * 100).toFixed(1)} %`, `${(cyc.eta_th / carnot * 100).toFixed(0)} % of the Carnot limit`),
      metric("Turbine, eta_t = " + cyc.eta_t.toFixed(3), `${cyc.wt.toFixed(2)} kJ/kg`, `ideal ${(cyc.s3.h - h4s).toFixed(2)} kJ/kg (h4s = ${h4s.toFixed(1)})`),
      metric("Pump, eta_p = " + cyc.eta_p.toFixed(3), `${cyc.wp.toFixed(3)} kJ/kg`, `ideal ${(h2s - cyc.s1.h).toFixed(3)} kJ/kg`),
      metric("Pressures", `${cyc.Pe.toFixed(0)} / ${cyc.Pc.toFixed(0)} kPa`, `ratio ${(cyc.Pe / cyc.Pc).toFixed(2)}`),
      h("p", { class: "explain" }, `The turbine expands from state 3 to 4. An ideal turbine would follow the dashed vertical line (constant entropy) to 4s; friction leaves the real exit at a higher enthalpy (drier, or more superheated), and ${(cyc.s4.s - cyc.s3.s).toFixed(4)} kJ/kg-K of entropy is generated per kg in the turbine. `
        + `The area enclosed by the loop is the net work per kg. Raising the evaporating temperature lifts the top of the loop and the efficiency; the condenser at ${cyc.Tc.toFixed(1)} C sets the bottom${S.Tc[k] > r.config.Tc + 0.01 ? " (floating above its set point because the air is warm)" : ""}.`));
  });
  box.append(h("div", { class: "two" }, cbox, info), tc);
  setTimeout(() => tc.start(), 0);
  return box;
}

// ---------------------------------------------------------------- devices: instantaneous states and rates
function devicesTab(r) {
  const box = h("div"), body = h("div");
  const tc = timeControl(r, (k) => {
    const S = r.series, cyc = G.cycleAtSample(r, k), c = r.config;
    const parts = [];
    parts.push(h("div", { class: "kpis five" }, metric("Sun", S.alt[k] > 0 ? `${S.alt[k].toFixed(0)} deg up` : "below horizon", `beam ${S.G[k].toFixed(0)} W/m^2 on aperture`),
      metric("Collector", `${(S.Qcol[k] / 1000).toFixed(2)} kW`, `inlet ${S.T_bot[k].toFixed(1)} C, air ${S.Ta[k].toFixed(1)} C`),
      metric("Tank", r.layers.length > 1 ? `${S.T_top[k].toFixed(1)} / ${S.T_bot[k].toFixed(1)} C` : `${S.T_top[k].toFixed(1)} C`, r.layers.length > 1 ? "top / bottom" : "uniform"),
      metric("Tank losses", `${S.Qloss[k].toFixed(0)} W`, `UA ${r.balance.UA.toFixed(2)} W/K`),
      metric("Stored since sunrise", `${S.E_tank_kWh[k].toFixed(2)} kWh`, S.Q_store[k] >= 0 ? `charging ${S.Q_store[k].toFixed(0)} W` : `discharging ${(-S.Q_store[k]).toFixed(0)} W`)));
    if (!cyc) { parts.push(callout("info", "The power cycle is idle at this time: no refrigerant flow, so the device states are not defined.")); body.replaceChildren(...parts); return; }
    const st = [[1, "Pump inlet (condenser exit)", cyc.s1], [2, "Pump exit (evaporator inlet)", cyc.s2], [3, "Turbine inlet (evaporator exit)", cyc.s3], [4, "Turbine exit (condenser inlet)", cyc.s4]];
    parts.push(h("h3", null, "Refrigerant states (R-134a)"), table(["State", "Location", "T [C]", "P [kPa]", "h [kJ/kg]", "s [kJ/kg-K]", "Phase", "Quality x"],
      st.map(([n, lab, s]) => [String(n), lab, s.T.toFixed(2), s.P.toFixed(1), s.h.toFixed(2), s.s.toFixed(4), h("span", { class: "phchip", style: `background:${PH[phaseOf(s)]}` }, phaseText(s).split(",")[0]),
        s.x === null || s.x === undefined ? "-" : s.x.toFixed(3)]), "num"));
    const m = S.mdot[k], g = L.entropy_generation(cyc, S.T_top[k], S.Ta[k]);
    const dev = [["Pump", `${S.Wp[k].toFixed(1)} W in`, `w_p = (h2s - h1)/eta_p = ${cyc.wp.toFixed(3)} kJ/kg`, g.pump * m * 1000, "Raises the saturated liquid from the condenser pressure to the boiler pressure. Little work is needed because liquid is nearly incompressible."],
      ["Evaporator", `${(S.Qev[k] / 1000).toFixed(2)} kW in`, `q_in = h3 - h2 = ${cyc.qin.toFixed(1)} kJ/kg`, g.evaporator * m * 1000, `Hot tank water boils the refrigerant at ${c.Te} C (${cyc.Pe.toFixed(0)} kPa)${c.superheat > 0 ? ` and superheats it by ${c.superheat} K` : ""}. Most of the entropy is generated here, by the temperature difference between water and refrigerant.`],
      ["Turbine", `${S.Wt[k].toFixed(1)} W out`, `w_t = eta_t (h3 - h4s) = ${cyc.wt.toFixed(2)} kJ/kg`, g.turbine * m * 1000, `Expands the vapour from ${cyc.Pe.toFixed(0)} to ${cyc.Pc.toFixed(0)} kPa. The exit is ${phaseText(cyc.s4)}.`],
      ["Condenser", `${(S.Qc[k] / 1000).toFixed(2)} kW out`, `q_out = h4 - h1 = ${cyc.qout.toFixed(1)} kJ/kg`, g.condenser * m * 1000, `Rejects heat to the air at ${S.Ta[k].toFixed(1)} C and returns saturated liquid at ${cyc.Tc.toFixed(1)} C.`]];
    parts.push(h("h3", null, `Devices (mass flow ${(m * 1000).toFixed(2)} g/s)`), table(["Device", "Rate", "Per kg", "Entropy generated [W/K]", "What happens"], dev.map((d) => [d[0], d[1], d[2], d[3].toFixed(4), d[4]]), "small"));
    parts.push(h("p", { class: "explain" }, `First law check: q_in - q_out - w_net = ${(cyc.qin - cyc.qout - cyc.wnet).toExponential(1)} kJ/kg. Net power ${S.Wnet[k].toFixed(1)} W, thermal efficiency ${(cyc.eta_th * 100).toFixed(2)} %.`));
    body.replaceChildren(...parts);
  });
  box.append(tc, body);
  setTimeout(() => tc.start(), 0);
  return box;
}

// ---------------------------------------------------------------- energy balance by device
function energyTab(r) {
  const k = r.kpi, kwh = (v) => v / 1000, wrap = h("div");
  const rows = [["Collector", kwh(k.E_collector_Wh), 0, "heat from the sun (beam " + kwh(k.E_incident_Wh).toFixed(1) + " kWh on the aperture)"],
    ["Storage tank", 0, kwh(k.E_loss_Wh), "losses to the air; stores " + kwh(k.dU_tank_Wh).toFixed(2) + " kWh"],
    ["Evaporator", kwh(k.E_evaporator_Wh), 0, "heat into the refrigerant"], ["Pump", kwh(k.W_pump_Wh), 0, "work into the refrigerant"],
    ["Turbine", 0, kwh(k.W_turbine_Wh), "work out"], ["Condenser", 0, kwh(k.Q_condenser_Wh), "heat rejected to the air"]];
  const mx = Math.max(...rows.map((x) => Math.max(x[1], x[2])), 1e-6);
  const bars = h("div", { class: "dbars" }, h("div", { class: "dbh" }, h("span", null, "Device"), h("span", { class: "r" }, "Energy in [kWh]"), h("span", null, "Energy out [kWh]"), h("span", null, "")),
    rows.map(([d, ein, eout, note]) => h("div", { class: "dbr" }, h("span", { class: "dn" }, d),
      h("span", { class: "din" }, h("i", { style: `width:${(ein / mx * 100).toFixed(1)}%` }), h("b", null, ein ? ein.toFixed(2) : "")),
      h("span", { class: "dout" }, h("i", { style: `width:${(eout / mx * 100).toFixed(1)}%` }), h("b", null, eout ? eout.toFixed(2) : "")), h("span", { class: "dnote" }, note))));
  const wf = h("div", { class: "wf" });
  const items = [{ lab: "Beam on aperture", kind: "abs", v: kwh(k.E_incident_Wh) }, { lab: "Collector losses", kind: "rel", v: -kwh(k.E_incident_Wh - k.E_collector_Wh) },
    { lab: "Collector heat", kind: "tot" }, { lab: "Tank losses", kind: "rel", v: -kwh(k.E_loss_Wh) }, { lab: "Stored in tank", kind: "rel", v: -kwh(k.dU_tank_Wh) },
    { lab: "Heat to evaporator", kind: "tot" }, { lab: "Pump work", kind: "rel", v: kwh(k.W_pump_Wh) }, { lab: "Heat rejected", kind: "rel", v: -kwh(k.Q_condenser_Wh) },
    { lab: "Turbine work", kind: "tot" }, { lab: "Pump work", kind: "rel", v: -kwh(k.W_pump_Wh) }, { lab: "Net work", kind: "tot" }];
  wrap.append(h("h3", null, "Energy in and out of each device over the day"), bars,
    h("p", { class: "explain" }, `Of ${kwh(k.E_incident_Wh).toFixed(1)} kWh of sunlight on the aperture, the collector delivers ${kwh(k.E_collector_Wh).toFixed(1)} kWh (${(k.eta_collector * 100).toFixed(0)} %); its losses grow with the water temperature. `
      + `The tank loses ${kwh(k.E_loss_Wh).toFixed(2)} kWh through its insulation and ends the day ${k.dU_tank_Wh >= 0 ? "holding" : "short by"} ${Math.abs(kwh(k.dU_tank_Wh)).toFixed(2)} kWh compared with sunrise. `
      + `The cycle turns ${kwh(k.E_evaporator_Wh).toFixed(2)} kWh of heat plus ${kwh(k.W_pump_Wh).toFixed(3)} kWh of pump work into ${kwh(k.W_turbine_Wh).toFixed(3)} kWh of turbine work and rejects the rest, ${kwh(k.Q_condenser_Wh).toFixed(2)} kWh, in the condenser: a Rankine cycle at these temperatures must reject most of its heat (second law).`),
    h("h3", null, "Energy flow over the day"), wf, h("div", { class: "cap" }, "Blue bars are running totals, orange adds energy, grey removes it."),
    table(["Conservation check", "Value"], [["Tank: dU - (Q_col - Q_evap - Q_loss) [Wh]", r.balance.resid_tank_Wh.toExponential(1)], ["Cycle: Q_evap - Q_cond - W_net [Wh]", r.balance.resid_cycle_Wh.toExponential(1)]], "num small"));
  const draw = () => waterfall(wf, items, "Energy over the day [kWh]");
  setTimeout(draw, 0); const ro = new ResizeObserver(() => draw()); ro.observe(wf); app.disposers.push(() => ro.disconnect());
  return wrap;
}

// ---------------------------------------------------------------- storage: instantaneous vs stored
function storageTab(r) {
  const S = r.series, H = span(r), N = r.t.findIndex((v) => v > H + 1e-9), n = N < 0 ? r.t.length : N, t = Array.from(r.t).slice(0, n), ax = timeAxis(r, H);
  const A = (a, f = 1) => Array.from(a).slice(0, n).map((v) => v * f), grp = "st" + Math.random().toString(36).slice(2);
  const a = h("div"), b = h("div"), cbox = h("div"), wrap = h("div");
  const chg = A(S.Q_store), pos = chg.map((v) => Math.max(0, v)), neg = chg.map((v) => Math.min(0, v));
  wrap.append(h("p", { class: "explain" }, "The tank is the plant's battery. The top chart is the instantaneous rate at which energy enters (charging, above zero) or leaves (discharging, below zero) the tank: collector heat minus heat drawn by the evaporator minus losses. The bottom chart is its running total, the energy stored since sunrise."), a, b, cbox);
  chart(a, Object.assign({ group: grp, height: 190, title: "Charge (+) / discharge (-) rate of the tank [W]", includeZero: true, tipfmt: (v) => v.toFixed(0),
    series: [{ name: "Charging", x: t, y: pos, color: ORANGE, fill: "rgba(244,114,48,0.25)" }, { name: "Discharging", x: t, y: neg, color: BLUE, fill: "rgba(37,125,224,0.25)" }] }, ax));
  chart(b, Object.assign({ group: grp, height: 190, title: "Energy stored in the tank since sunrise [kWh]", includeZero: true, tipfmt: (v) => v.toFixed(3),
    series: [{ name: "Stored energy", x: t, y: A(S.E_tank_kWh), color: AQUA }] }, ax));
  const L2 = r.layers.length;
  const lay = r.layers.map((arr, j) => ({ name: L2 > 1 ? (j === 0 ? "Top layer" : j === L2 - 1 ? "Bottom layer" : "") : "Tank", x: t, y: Array.from(arr).slice(0, n), color: tempColour(95 - j * (70 / Math.max(1, L2 - 1))), width: j === 0 || j === L2 - 1 ? 2.2 : 1 }));
  chart(cbox, Object.assign({ group: grp, height: 210, title: L2 > 1 ? "Tank layer temperatures [C] (10 layers, stratified)" : "Tank temperature [C] (uniform)", tipfmt: (v) => v.toFixed(1), xlabel: "Solar time",
    series: lay.concat([{ name: "Start temperature", x: t, y: t.map(() => r.config.T_start), color: GREY, dash: "5 4", width: 1.2 }]) }, ax));
  const k = r.kpi, peak = Math.max(...A(S.E_tank_kWh));
  wrap.append(h("div", { class: "kpis three" }, metric("Peak stored", peak.toFixed(2) + " kWh", "since sunrise"), metric("Losses over the day", (k.E_loss_Wh / 1000).toFixed(2) + " kWh", `UA ${r.balance.UA.toFixed(2)} W/K`),
    metric("Net change over the day", (k.dU_tank_Wh / 1000).toFixed(2) + " kWh", k.dU_tank_Wh >= 0 ? "tank ends warmer than it started" : "tank ends colder than it started")));
  return wrap;
}
