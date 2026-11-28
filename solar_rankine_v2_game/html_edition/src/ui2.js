/* Solar Rankine Lab v2 - website interface (thermodynamics lives in core.js and game.js). */
(function () {
"use strict";
const L = Lab, G = Game, K = L.K;
const STORE = "srl_scores_v2";

// ===================================================================== state
const app = {
  view: "home", difficulty: "basic", mode: null,          // mode null = sandbox
  scenario: null, config: null,                           // current (edited) settings
  run: null, prev: null,                                  // last result, and the one before it
  history: [], tab: "Plant", hourIdx: null, disposers: [], playing: false,
};
const dispose = () => { while (app.disposers.length) { try { app.disposers.pop()(); } catch (e) { /* ignore */ } } };
const chart = (el, cfg) => { const c = new Chart(el, cfg); app.disposers.push(() => c.destroy()); return c; };
const MAIN = () => document.getElementById("main");

// ===================================================================== scores (browser only)
function loadScores() { try { return JSON.parse(localStorage.getItem(STORE) || "{}"); } catch (e) { return {}; } }
function saveScores(s) { try { localStorage.setItem(STORE, JSON.stringify(s)); } catch (e) { /* storage unavailable */ } }
function recordScore(mode, difficulty, sc, cfg, r, res) {
  if (!res.passed) return false;
  const all = loadScores(), key = `${mode}|${difficulty}`, cur = all[key];
  if (cur && cur.score >= res.score) return false;
  all[key] = { score: res.score, scenario: sc, config: cfg, headline: G.headline(r), date: new Date().toISOString().slice(0, 16).replace("T", " ") };
  saveScores(all); return true;
}

// ===================================================================== small components
const fmt = (v, d = 1) => (Number.isFinite(v) ? v.toFixed(d) : "-");
const pct = (v, d = 1) => (Number.isFinite(v) ? (v * 100).toFixed(d) + " %" : "-");
function metric(label, value, sub, cls) { return h("div", { class: "metric " + (cls || "") }, h("div", { class: "ml" }, label), h("div", { class: "mv" }, value), sub ? h("div", { class: "ms" }, sub) : null); }
function callout(level, text) { const ic = { success: "ok", info: "i", warning: "!", error: "x" }[level]; return h("div", { class: "callout " + level }, h("span", { class: "ci" }, ic), h("span", null, text)); }
function table(headers, rows, cls) {
  return h("div", { class: "tw" }, h("table", { class: cls || "" }, h("thead", null, h("tr", null, headers.map((x) => h("th", null, x)))),
    h("tbody", null, rows.map((r) => h("tr", null, r.map((c) => (c && c.nodeType ? h("td", null, c) : h("td", { html: esc(c == null ? "" : c) }))))))));
}
const decimals = (step) => { const s = String(step); return s.includes(".") ? s.split(".")[1].length : 0; };
function slider(label, min, max, step, value, onInput, onCommit) {
  const d = decimals(step), out = h("span", { class: "sv" }, (+value).toFixed(d));
  const inp = h("input", { type: "range", min, max, step, value, "aria-label": label });
  inp.addEventListener("input", () => { out.textContent = parseFloat(inp.value).toFixed(d); onInput(parseFloat(inp.value)); });
  inp.addEventListener("change", () => onCommit && onCommit(parseFloat(inp.value)));
  const el = h("label", { class: "slider" }, h("span", { class: "sl" }, label, out), inp);
  el.setValue = (v) => { inp.value = v; out.textContent = (+inp.value).toFixed(d); };
  return el;
}
function toggle(label, checked, onChange) {
  const inp = h("input", { type: "checkbox" }); inp.checked = checked; inp.addEventListener("change", () => onChange(inp.checked));
  return h("label", { class: "toggle" }, inp, h("span", { class: "tr" }), h("span", null, label));
}
function segmented(options, value, onPick, cls) {
  const box = h("div", { class: "seg " + (cls || ""), role: "radiogroup" });
  for (const [val, lab] of options) box.append(h("button", { class: "segb" + (val === value ? " on" : ""), role: "radio", "aria-checked": val === value ? "true" : "false",
    onclick: () => { if (val !== value) onPick(val); } }, lab));
  return box;
}
function tabs(names, render) {
  const body = h("div", { class: "tabbody" }), bar = h("div", { class: "tabs", role: "tablist" });
  let local = [];
  const show = (n) => { app.tab = n;
    for (const b of bar.children) b.classList.toggle("on", b.dataset.n === n);
    while (local.length) { try { local.pop()(); } catch (e) { /* ignore */ } }
    const before = app.disposers.length; body.replaceChildren(render(n)); local = app.disposers.splice(before); };
  names.forEach((n) => bar.append(h("button", { class: "tab", role: "tab", "data-n": n, onclick: () => show(n) }, n)));
  const wrap = h("div", null, bar, body);
  wrap.refresh = () => show(names.includes(app.tab) ? app.tab : names[0]);
  app.disposers.push(() => { while (local.length) local.pop()(); });
  wrap.refresh();
  return wrap;
}
const clockStr = (hr) => { hr = ((hr % 24) + 24) % 24; const hh = Math.floor(hr), mm = Math.round((hr - hh) * 60); return `${String(mm === 60 ? hh + 1 : hh).padStart(2, "0")}:${String(mm % 60).padStart(2, "0")}`; };

// ===================================================================== modal
function modal(title, body, buttons) {
  document.querySelectorAll(".modal-back").forEach((m) => m.remove());
  const back = h("div", { class: "modal-back", role: "dialog", "aria-modal": "true", "aria-label": title });
  const close = () => back.remove();
  const box = h("div", { class: "modal" }, h("h2", null, title), body,
    h("div", { class: "mbtns" }, buttons.map(([lab, cls, fn]) => h("button", { class: "btn " + (cls || ""), onclick: () => { close(); fn && fn(); } }, lab))));
  back.append(box); document.body.append(back);
  const first = box.querySelector(".btn.primary") || box.querySelector(".btn"); if (first) first.focus();
  back.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  return close;
}

// ===================================================================== navigation
function render() {
  dispose(); stopPlay();
  const m = MAIN(); m.replaceChildren(app.view === "home" ? homeView() : playView());
  window.scrollTo(0, 0);
}
function goHome() { app.view = "home"; render(); }
function startPlay(mode, scenario, config) {
  app.mode = mode; app.view = "play"; app.run = null; app.prev = null; app.history = [];
  if (!scenario && !mode) scenario = { season: "summer", case: "best", T_tank0: 40, limits: app.difficulty === "engineer" ? G.randomScenario("engineer").limits : [] };
  app.scenario = scenario || G.newScenario(mode, app.difficulty);
  app.config = config ? G.clampConfig(Object.assign({}, config, { difficulty: app.difficulty }), app.scenario) : G.defaultConfig(app.difficulty, app.scenario);
  render();
  if (mode) showBriefing(true); else runNow();
}
function setDifficulty(d) {
  if (d === app.difficulty) return;
  app.difficulty = d;
  if (app.view === "play") {
    // same season, case and starting tank; new device limits for Engineer
    const sc = Object.assign({}, app.scenario, { limits: d === "engineer" ? G.randomScenario("engineer").limits : [] });
    app.scenario = sc;
    const keep = Object.assign({}, app.config, { difficulty: d });
    app.config = G.clampConfig(d === "engineer" ? Object.assign(keep, Object.fromEntries(sc.limits.map(([n, lo, hi]) => [n, +(0.5 * (lo + hi)).toFixed(3)]))) : keep, sc);
    app.run = null; app.prev = null; app.history = [];
    render(); if (app.mode) showBriefing(true); else runNow();
  } else render();
}

// ===================================================================== home
const DIFF_TEXT = {
  basic: "Uniform tank temperature, a collector that always faces the sun, and fixed device efficiencies. You size the collector, tank and insulation and set the operating temperatures.",
  engineer: "Stratified tank (10 layers), sun tracking on or off with a fixed tilt, and device efficiencies you set inside this plant's random limits. Adds superheat, optical efficiency and insulation thickness.",
};
function homeView() {
  const root = h("div", { class: "home" });
  root.append(h("h1", null, "Solar Rankine Lab"),
    h("p", { class: "lead" }, "A solar-driven R-134a Rankine power plant with thermal storage. Sunlight heats a collector, a water tank stores the heat, and a pump, evaporator, turbine and condenser turn it into work. Every day is a real Los Angeles season."),
    h("div", { class: "diffrow" }, h("span", { class: "dl" }, "Difficulty"), segmented([["basic", "Basic"], ["engineer", "Engineer"]], app.difficulty, setDifficulty, "big"),
      h("span", { class: "dt" }, DIFF_TEXT[app.difficulty])));
  const cards = h("div", { class: "cards modes" });
  cards.append(h("div", { class: "card sandbox" }, h("h3", null, "Sandbox"), h("p", null, "Free play: pick any season and case, change everything, flip the pump and valve, and watch the plant run. No score."),
    h("button", { class: "btn primary", onclick: () => startPlay(null) }, "Open sandbox")));
  for (const [k, m] of Object.entries(G.MODES)) cards.append(h("div", { class: "card" }, h("h3", null, m.title), h("p", null, m.goal),
    h("button", { class: "btn primary", onclick: () => startPlay(k) }, "Play")));
  root.append(h("h2", null, "Choose a mode"), cards, h("h2", null, "Scoreboard"), scoreboard());
  return root;
}
function scoreboard(compact) {
  const s = loadScores(), box = h("div", { class: "scoreboard" });
  const rows = [];
  for (const [k, m] of Object.entries(G.MODES)) {
    const cells = [h("b", null, m.title)];
    for (const d of ["basic", "engineer"]) {
      const e = s[`${k}|${d}`];
      cells.push(e ? h("div", { class: "sbc" }, h("div", { class: "sbv" }, m.fmt(e.score)), h("div", { class: "sbs" }, `${G.scenarioInfo(e.scenario).label} · ${e.date}`),
        compact ? null : h("button", { class: "btn small", onclick: () => { app.difficulty = d; startPlay(k, e.scenario, e.config); } }, "Replay scenario")) : h("span", { class: "muted" }, "no score yet"));
    }
    rows.push(cells);
  }
  box.append(table(["Mode", "Basic", "Engineer"], rows, "sb"));
  if (!compact) {
    const det = [], heads = ["Best run", "Peak power", "Total work", "Heat in", "Heat lost", "Net heat", "Run after sunset", "Work after sunset", "Cycle eff.", "Collector eff.", "Solar to work", "Second law"];
    for (const [k, m] of Object.entries(G.MODES)) for (const d of ["basic", "engineer"]) {
      const e = s[`${k}|${d}`]; if (!e) continue; const x = e.headline;
      det.push([`${m.title} (${d === "basic" ? "Basic" : "Engineer"})`, fmt(x.peak_W, 0) + " W", fmt(x.total_kWh, 3) + " kWh", fmt(x.heat_in_kWh, 2) + " kWh", fmt(x.heat_lost_kWh, 2) + " kWh",
        fmt(x.net_heat_kWh, 2) + " kWh", fmt(x.after_sunset_h, 1) + " h", fmt(x.after_sunset_kWh, 3) + " kWh", pct(x.eta_cycle, 2), pct(x.eta_collector), pct(x.eta_daily, 2), pct(x.eta_II)]);
    }
    if (det.length) box.append(h("h3", null, "System parameters of the best runs"), table(heads, det, "num small"));
    box.append(h("div", { class: "sbfoot" }, h("span", { class: "cap" }, "Scores are saved in this browser only."),
      h("button", { class: "btn ghost small", onclick: () => { if (Object.keys(loadScores()).length) modal("Clear all scores?", h("p", null, "This removes every best score saved in this browser."),
        [["Clear scores", "danger", () => { saveScores({}); render(); }], ["Cancel", "", null]]); } }, "Clear scores")));
  }
  return box;
}

// ===================================================================== play view
function playView() {
  const root = h("div", { class: "play" }), m = app.mode ? G.MODES[app.mode] : null;
  const best = app.mode ? loadScores()[`${app.mode}|${app.difficulty}`] : null;
  root.append(h("div", { class: "topbar" },
    h("button", { class: "btn ghost", onclick: goHome }, "< Main page"),
    h("h1", null, m ? m.title : "Sandbox"),
    segmented([["basic", "Basic"], ["engineer", "Engineer"]], app.difficulty, (d) => setDifficulty(d)),
    app.mode ? h("div", { class: "bestchip" }, "Best ", h("b", null, best ? m.fmt(best.score) : "none yet")) : null));
  root.append(briefingCard());
  const grid = h("div", { class: "pgrid3" }), ctl = h("aside", { class: "controls" }), res = h("section", { class: "results" }), side = h("aside", { class: "summary" });
  ctl.append(controlsPanel());
  grid.append(ctl, res, side);
  root.append(grid);
  app.resEl = res; app.sideEl = side;
  drawResults();
  return root;
}
function briefingCard() {
  const box = h("details", { class: "brief", open: app.mode ? "" : null });
  const items = G.briefing(app.scenario);
  box.append(h("summary", null, h("b", null, "Scenario briefing: "), G.scenarioInfo(app.scenario).label));
  const list = h("div", { class: "blist" }, items.map(([a, b]) => h("div", null, h("span", { class: "bk" }, a), h("span", { class: "bv" }, b))));
  box.append(list);
  if (app.mode) box.append(h("p", { class: "goal" }, h("b", null, "Goal. "), G.MODES[app.mode].goal));
  const row = h("div", { class: "brow2" });
  if (app.mode) row.append(h("button", { class: "btn", onclick: () => startPlay(app.mode) }, "New random scenario"));
  else {
    const si = G.scenarioInfo(app.scenario);
    const sSel = h("select", { onchange: () => sandboxScenario({ season: sSel.value }) }, Object.entries(G.SEASONS).map(([k, v]) => h("option", { value: k, selected: k === app.scenario.season ? "" : null }, v.label)));
    const cSel = h("select", { onchange: () => sandboxScenario({ case: cSel.value }) }, G.CASES.map((k) => h("option", { value: k, selected: k === app.scenario.case ? "" : null }, k + " case")));
    row.append(h("label", { class: "sel" }, h("span", null, "Season"), sSel), h("label", { class: "sel" }, h("span", null, "Case"), cSel),
      h("div", { class: "t0" }, slider("Tank temperature at sunrise [C]", 20, 70, 1, app.scenario.T_tank0, () => {}, (v) => sandboxScenario({ T_tank0: v }))),
      h("button", { class: "btn", onclick: () => { const sc = G.randomScenario(app.difficulty); app.scenario = sc; app.config = G.clampConfig(app.config, sc); render(); runNow(); } }, "Random scenario"));
    void si;
  }
  box.append(row);
  return box;
}
function sandboxScenario(ch) { app.scenario = Object.assign({}, app.scenario, ch); app.config = G.clampConfig(app.config, app.scenario); render(); runNow(); }
function showBriefing(start) {
  const items = G.briefing(app.scenario);
  const body = h("div", null, h("p", null, G.MODES[app.mode].goal),
    h("div", { class: "blist" }, items.map(([a, b]) => h("div", null, h("span", { class: "bk" }, a), h("span", { class: "bv" }, b)))),
    h("p", { class: "cap" }, app.difficulty === "basic" ? "Basic: uniform tank, sun tracking, fixed efficiencies (turbine 0.80, pump 0.70, optics 0.75)."
      : "Engineer: stratified tank; efficiencies are adjustable only inside the limits above."),
    h("p", { class: "cap" }, "Change the settings on the left, then press Run. Every run starts at sunrise with the tank temperature above."));
  modal(`Scenario briefing: ${G.MODES[app.mode].title}`, body, [[start ? "Start" : "Close", "primary", start ? () => runNow() : null]]);
}

// ===================================================================== controls
const GROUP_ORDER = ["Collector", "Storage tank", "Power cycle"];
function controlsPanel() {
  const box = h("div", { class: "params" }), list = G.controlsFor(app.difficulty, app.scenario), c = app.config;
  const pending = h("div", { class: "pending" });
  const updPending = () => {
    const ch = app.run ? G.changedSettings(app.run.config, G.basicLock(app.config)).filter(([k]) => k !== "difficulty") : [];
    pending.replaceChildren(ch.length ? callout("info", `${ch.length} setting${ch.length > 1 ? "s" : ""} changed. Press Run to see the effect.`) : "");
    runBtn.classList.toggle("pulse", ch.length > 0);
  };
  const commit = (name, oldVal) => { checkInputs(name, oldVal); updPending(); };
  for (const g of GROUP_ORDER) {
    const det = h("details", { open: "" }, h("summary", null, g));
    for (const [name, label, lo, hi, step] of list.filter((x) => x[5] === g)) {
      if (name === "tracking") {
        const tiltBox = h("div");
        const drawTilt = () => tiltBox.replaceChildren(c.tracking ? h("div", { class: "cap" }, "Tracking: the aperture faces the sun all day (incidence angle 0 deg).")
          : (() => { const old = c.tilt; return slider("Fixed tilt from horizontal [deg]", 0, 80, 1, c.tilt, (v) => { c.tilt = v; }, () => commit("tilt", old)); })());
        det.append(toggle("Sun tracking", c.tracking, (v) => { const old = c.tracking; c.tracking = v; drawTilt(); commit("tracking", old); }), tiltBox);
        drawTilt();
      } else if (name === "tilt") continue;
      else if (name === "insulation") {
        const sel = h("select", { onchange: () => { const old = c.insulation; c.insulation = sel.value; commit("insulation", old); } },
          Object.entries(G.INSULATION_LEVELS).map(([k, cm]) => h("option", { value: k, selected: k === c.insulation ? "" : null }, `${k[0].toUpperCase() + k.slice(1)} (${cm} cm foam, UA ${G.tankUA(c.tank_L, cm).toFixed(2)} W/K at this volume)`)));
        det.append(h("label", { class: "sel" }, h("span", null, label), sel));
      } else {
        let old = c[name];
        const el = slider(label, lo, hi, step, Math.min(hi, Math.max(lo, c[name])), (v) => { c[name] = v; }, () => { commit(name, old); old = c[name]; });
        det.append(el);
        if (lo === hi) el.querySelector("input").disabled = true;
      }
    }
    box.append(det);
  }
  if (!app.mode) box.append(h("details", { open: "" }, h("summary", null, "Equipment operation"),
    toggle("Pump running", c.pump_on, (v) => { const o = c.pump_on; c.pump_on = v; commit("pump_on", o); }),
    toggle("Turbine valve open (off = throttle bypass)", c.valve_open, (v) => { const o = c.valve_open; c.valve_open = v; commit("valve_open", o); }),
    toggle("Collector exposed to the sun", c.collector_on, (v) => { const o = c.collector_on; c.collector_on = v; commit("collector_on", o); })));
  const runBtn = h("button", { class: "btn primary run", onclick: () => runNow() }, "Run");
  const undoBtn = h("button", { class: "btn", onclick: undo, disabled: app.history.length ? null : "" }, "Undo last run");
  const resetBtn = h("button", { class: "btn ghost", onclick: () => { app.config = G.defaultConfig(app.difficulty, app.scenario); rebuildControls(); } }, "Reset settings");
  const wrap = h("div", null, h("div", { class: "chead2" }, h("h3", null, "Settings")), box, pending, h("div", { class: "runrow" }, runBtn, undoBtn, resetBtn));
  app.updPending = updPending;
  setTimeout(updPending, 0);
  return wrap;
}
function rebuildControls() { const ctl = document.querySelector(".controls"); if (ctl) ctl.replaceChildren(controlsPanel()); }

// instant check of a committed control; stage 4 turns problems into pop-ups with Undo
function checkInputs(name, oldVal) {
  const probs = G.inputProblems(G.basicLock(app.config), app.scenario);
  if (!probs.length) return true;
  problemPopup(probs, "This setting is not physically possible", () => { app.config[name] = oldVal; rebuildControls(); }, name);
  return false;
}

// ===================================================================== run
function runNow() {
  const c = G.clampConfig(G.basicLock(app.config), app.scenario);
  const probs = G.inputProblems(c, app.scenario);
  if (probs.length) { problemPopup(probs, "Fix these settings before running", null); return; }
  let r;
  try { r = G.simulate(c, app.scenario); } catch (e) { modal("The simulation failed", h("p", null, e.message), [["Close", "primary", null]]); return; }
  if (app.run) { app.history.push({ config: app.run.config, run: app.run, prev: app.prev }); if (app.history.length > 30) app.history.shift(); }
  app.prev = app.run; app.run = r; app.config = Object.assign({}, c); app.hourIdx = null;
  app.lastScore = app.mode ? G.score(app.mode, r) : null;
  app.newBest = app.mode ? recordScore(app.mode, app.difficulty, app.scenario, c, r, app.lastScore) : false;
  drawResults(); rebuildControls();
  const out = G.outcomeProblems(r);
  if (out.length) problemPopup(out, "The run shows a problem", app.history.length ? () => undo() : null);
}
function undo() {
  const h0 = app.history.pop(); if (!h0) return;
  app.run = h0.run; app.prev = h0.prev; app.config = Object.assign({}, h0.config);
  app.lastScore = app.mode ? G.score(app.mode, app.run) : null; app.newBest = false;
  drawResults(); rebuildControls();
}

// ===================================================================== results
function drawResults() {
  const res = app.resEl, side = app.sideEl; if (!res) return;
  stopPlay();
  // dispose charts that belong to results (keep nothing else alive)
  dispose();
  res.replaceChildren(); side.replaceChildren();
  const r = app.run;
  if (!r) { res.append(callout("info", app.mode ? "Read the briefing, adjust the settings and press Run." : "Press Run to simulate the day.")); side.append(summaryPanel()); return; }
  if (app.mode) {
    const s = app.lastScore, m = G.MODES[app.mode];
    res.append(h("div", { class: "scorebar " + (s.passed ? "pass" : "fail") }, h("div", { class: "sbig" }, s.passed ? m.fmt(s.score) : "No score"),
      h("div", null, h("div", { class: "smsg" }, s.message), app.newBest ? h("div", { class: "newbest" }, "New best score for this mode and difficulty!") : null)));
  }
  const k = r.kpi, x = G.headline(r);
  res.append(h("div", { class: "kpis" },
    metric("Total net work", fmt(x.total_kWh, 2) + " kWh", "sunrise to next sunrise"), metric("Peak net power", fmt(x.peak_W, 0) + " W"),
    metric("Heat collected", `${fmt(x.heat_in_kWh, 1)} kWh`, `lost ${fmt(x.heat_lost_kWh, 2)} kWh, net ${fmt(x.net_heat_kWh, 1)} kWh`),
    metric("After sunset", `${fmt(x.after_sunset_h, 1)} h`, `${fmt(x.after_sunset_kWh, 2)} kWh`),
    metric("Cycle efficiency", pct(x.eta_cycle, 2), `solar to work ${pct(x.eta_daily, 2)}`),
    metric("Collector / 2nd law", `${pct(x.eta_collector, 0)} / ${pct(x.eta_II, 0)}`)));
  res.append(h("div", { class: "fb" }, G.outcomeWarnings(r).map(([l, t]) => callout(l, t))));
  const t = tabs(["Plant", "Devices", "T-s diagram", "Energy balance", "Storage", "Day plots", "Data"], renderTab);
  res.append(t);
  side.append(summaryPanel());
  if (app.mode) side.append(h("h3", { class: "sbh" }, "Scoreboard"), scoreboard(true));
}
function renderTab(n) {
  const r = app.run;
  switch (n) {
    case "Plant": return plantTab(r);
    case "Devices": return devicesTab(r);
    case "T-s diagram": return tsTab(r);
    case "Energy balance": return energyTab(r);
    case "Storage": return storageTab(r);
    case "Day plots": return dayPlots(r);
    default: return dataTab(r);
  }
}

// ---------------------------------------------------------------- time helpers
const span = (r) => (app.mode === "survive" ? 48 : 24);
function shadeNights(r, H) { const S = r.series, t = r.t, out = []; let a = null;
  for (let i = 0; i < t.length && t[i] <= H + 1e-9; i++) { const n = S.alt[i] <= 0; if (n && a === null) a = t[i]; if ((!n || t[i] >= H - 1e-9) && a !== null) { out.push([a, t[i]]); a = null; } }
  return out; }
function timeAxis(r, H) {
  const sr = r.info.sunrise, ticks = []; for (let v = 0; v <= H + 1e-9; v += H > 24 ? 6 : 3) ticks.push(v);
  return { xlim: [0, H], xticks: ticks, xtickfmt: (v) => clockStr(sr + v), xfmt: (v) => `${clockStr(sr + v)} (${v.toFixed(2)} h after sunrise)`, shade: shadeNights(r, H) };
}
const idxAt = (r, hr) => { let k = 0, b = 1e9; for (let i = 0; i < r.t.length; i++) { const d = Math.abs(r.t[i] - hr); if (d < b) { b = d; k = i; } } return k; };
function defaultIdx(r) { if (app.hourIdx != null) return app.hourIdx; let k = 0, b = -Infinity; const S = r.series;
  for (let i = 0; i < r.t.length && r.t[i] <= 24; i++) if (S.Wnet[i] > b) { b = S.Wnet[i]; k = i; } if (b <= 0) k = idxAt(r, 6); return k; }

// ---------------------------------------------------------------- day plots
function dayPlots(r) {
  const S = r.series, H = span(r), N = r.t.findIndex((v) => v > H + 1e-9), n = N < 0 ? r.t.length : N, t = Array.from(r.t).slice(0, n);
  const box = h("div", { class: "stack" }), ax = timeAxis(r, H), grp = "day" + Math.random().toString(36).slice(2);
  const k = r.kpi;
  box.append(h("p", { class: "explain" }, `The sun sets how much heat the collector delivers; the tank warms until its top reaches the ${r.config.T_start} C start temperature, then the pump starts and the turbine produces power. `
    + `The plant ran ${k.run_hours.toFixed(1)} h on the scored day, ${k.night_run_hours.toFixed(1)} h of it after sunset on stored heat. Net power = turbine - pump; it stays roughly constant while the pump runs at full flow because the boiler and condenser are held at their set points`
    + (k.float_hours > 0.1 ? `, except when warm air forces the condenser above its set point (${k.float_hours.toFixed(1)} h).` : ".")));
  const A = (a, f = 1) => Array.from(a).slice(0, n).map((v) => v * f);
  const mk = (title, series, extra) => { const el = h("div"); box.append(el); chart(el, Object.assign({ group: grp, height: 160, title, series: series.map((s) => Object.assign({ x: t }, s)) }, ax, extra)); };
  mk("Beam irradiance on the aperture [W/m^2]", [{ name: "Beam on aperture", y: A(S.G), color: BLUE }], { includeZero: true, tipfmt: (v) => v.toFixed(0) });
  const tl = [{ name: "Tank top", y: A(S.T_top), color: "#c8332f" }, { name: "Tank bottom", y: A(S.T_bot), color: BLUE }, { name: "Condenser", y: A(S.Tc), color: AQUA }, { name: "Ambient", y: A(S.Ta), color: GREY, dash: "2 4" }];
  if (r.balance.layers === 1) tl.splice(0, 2, { name: "Tank", y: A(S.T_top), color: "#c8332f" });
  mk("Temperatures [C]", tl, { tipfmt: (v) => v.toFixed(1), vlines: [{ x: 0, color: "#bbb" }] });
  mk("Heat rates [kW]", [{ name: "Collector", y: A(S.Qcol, 1e-3), color: ORANGE }, { name: "To evaporator", y: A(S.Qev, 1e-3), color: BLUE }, { name: "Tank loss", y: A(S.Qloss, 1e-3), color: GREY }], { includeZero: true, tipfmt: (v) => v.toFixed(2) });
  mk("Power [W]", [{ name: "Turbine", y: A(S.Wt), color: BLUE }, { name: "Pump", y: A(S.Wp), color: ORANGE }, { name: "Net", y: A(S.Wnet), color: AQUA }], { includeZero: true, tipfmt: (v) => v.toFixed(0) });
  mk("Refrigerant mass flow [g/s]", [{ name: "Mass flow", y: A(S.mdot, 1e3), color: BLUE }], { includeZero: true, xlabel: "Solar time", tipfmt: (v) => v.toFixed(2), height: 182 });
  box.append(h("div", { class: "cap" }, "Shaded bands: night. The run starts at sunrise" + (H > 24 ? "; the survival mode shows 48 h." : ".")));
  return box;
}

// ---------------------------------------------------------------- data
function dataTab(r) {
  const S = r.series, keys = Object.keys(S), rows = [];
  for (let i = 0; i < r.t.length; i += 6) rows.push([r.t[i].toFixed(2), clockStr(r.info.sunrise + r.t[i])].concat(keys.filter((q) => q !== "clock").map((q) => (Number.isFinite(S[q][i]) ? +S[q][i].toFixed(3) : "") + "")));
  const csv = () => { let s = "t_h_after_sunrise," + keys.join(",") + (r.layers.length > 1 ? "," + r.layers.map((_, j) => "T_layer" + (j + 1)).join(",") : "") + "\n";
    for (let i = 0; i < r.t.length; i++) s += r.t[i].toFixed(4) + "," + keys.map((q) => S[q][i]).join(",") + (r.layers.length > 1 ? "," + r.layers.map((a) => a[i].toFixed(4)).join(",") : "") + "\n";
    const a = h("a", { href: URL.createObjectURL(new Blob([s], { type: "text/csv" })), download: "solar_rankine_run.csv" }); document.body.append(a); a.click(); a.remove(); };
  return h("div", null, h("button", { class: "btn", onclick: csv }, "Download full data (CSV)"), h("div", { class: "cap" }, "Every 30 minutes shown; the CSV has every 5 minutes for 48 h, with each tank layer."),
    table(["h after sunrise", "solar time"].concat(keys.filter((q) => q !== "clock")), rows, "num small"));
}

// stage 3 and 4 views are defined below (plantTab, devicesTab, tsTab, energyTab, storageTab, summaryPanel, problemPopup)
/*__STAGE3__*/
/*__STAGE4__*/

// ===================================================================== boot
document.getElementById("main").replaceChildren();
render();
})();
