/* Solar Rankine Lab v2 - plant model, scenarios and game rules (no interface code).
 * JavaScript port of app/core/scenarios.py, plant.py and game.py. Uses Lab (core.js) for
 * R-134a properties, the Rankine cycle and the solar functions.
 */
const Game = (function () {
"use strict";
const L = Lab, K = L.K;

// ===================================================================== scenarios
const LAT = 34.05;
// Downtown Los Angeles 1991-2020 normals averaged by season (see scenarios.py)
const SEASONS = {
  winter: { day: 15, label: "Winter (15 Jan)", t_max: 19.9, t_min: 9.5, sun: 0.71 },
  spring: { day: 105, label: "Spring (15 Apr)", t_max: 22.2, t_min: 12.8, sun: 0.71 },
  summer: { day: 196, label: "Summer (15 Jul)", t_max: 27.3, t_min: 17.7, sun: 0.77 },
  fall: { day: 288, label: "Fall (15 Oct)", t_max: 25.6, t_min: 15.0, sun: 0.73 },
};
const CASES = ["best", "worst"], CASE_DT = { best: -2.0, worst: 2.0 };
const EFF_RANGES = { eta_t: [[0.55, 0.65], [0.78, 0.88]], eta_p: [[0.40, 0.50], [0.65, 0.80]], eta0: [[0.55, 0.65], [0.72, 0.82]] };
const BASIC_EFF = { eta_t: 0.80, eta_p: 0.70, eta0: 0.75 };
const T_TANK0_RANGE = [25.0, 55.0];

function mulberry32(a) { return function () { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const r3 = (x) => Math.round(x * 1000) / 1000, r1 = (x) => Math.round(x * 10) / 10;

function scenarioInfo(sc) {
  const s = SEASONS[sc.season];
  const T_mean = 0.5 * (s.t_max + s.t_min) + CASE_DT[sc.case], T_swing = s.t_max - s.t_min;
  const daylight = L.daylight_hours(LAT, s.day), sunrise = 12.0 - 0.5 * daylight;
  return { day: s.day, lat: LAT, clearness: sc.case === "best" ? 1.0 : s.sun, T_mean, T_swing,
    T_amb_min: T_mean - 0.5 * T_swing, T_amb_max: T_mean + 0.5 * T_swing, daylight, sunrise, sunset: 24 - sunrise,
    label: `${s.label}, ${sc.case} case` };
}
const limitOf = (sc, name) => { for (const [n, lo, hi] of sc.limits || []) if (n === name) return [lo, hi]; return null; };
function randomScenario(difficulty, rnd, season, kase) {
  rnd = rnd || Math.random;
  const seasons = Object.keys(SEASONS);
  const s = season || seasons[Math.floor(rnd() * seasons.length)], c = kase || CASES[Math.floor(rnd() * 2)];
  const T0 = r1(T_TANK0_RANGE[0] + rnd() * (T_TANK0_RANGE[1] - T_TANK0_RANGE[0]));
  const limits = difficulty === "engineer" ? Object.entries(EFF_RANGES).map(([n, [f, cl]]) =>
    [n, r3(f[0] + rnd() * (f[1] - f[0])), r3(cl[0] + rnd() * (cl[1] - cl[0]))]) : [];
  return { season: s, case: c, T_tank0: T0, limits };
}

// ===================================================================== plant model
const CP_W = 4186.0, K_INS = 0.025, H_OUT = 10.0, PINCH = 5.0, COND_APPROACH = 3.0, MIN_LIFT = 6.0, RAMP = 3.0, TE_MAX = 95.0;
const M_COL = 0.015, G_MIX = 2.0, G_INV = 200.0, HOURS = 48.0;
const INSULATION_LEVELS = { poor: 1.0, standard: 5.0, good: 10.0 };
const DEFAULT_CONFIG = { difficulty: "basic", area: 8.0, T_max: 95.0, tracking: true, tilt: 30.0, eta0: 0.75, a1: 1.5, a2: 0.005,
  tank_L: 500.0, insulation: "standard", ins_cm: 5.0, Te: 75.0, Tc: 30.0, superheat: 0.0, T_start: 82.0, pump_W: 30.0,
  eta_t: 0.80, eta_p: 0.70, pump_on: true, valve_open: true, collector_on: true };
const layersOf = (c) => (c.difficulty === "engineer" ? 10 : 1);
const thicknessOf = (c) => (c.difficulty === "engineer" ? c.ins_cm : INSULATION_LEVELS[c.insulation]);
function basicLock(c) { c = Object.assign({}, DEFAULT_CONFIG, c);
  return c.difficulty === "basic" ? Object.assign(c, { tracking: true, superheat: 0.0 }, BASIC_EFF) : c; }

function tankGeometry(V_L) { const V = V_L / 1000, D = Math.pow(2 * V / Math.PI, 1 / 3), H = 2 * D;
  return { D, H, A_side: Math.PI * D * H, A_end: Math.PI * D * D / 4 }; }
const tankU = (cm) => 1.0 / (cm / 100.0 / K_INS + 1.0 / H_OUT);
function tankUA(V_L, cm) { const g = tankGeometry(V_L); return tankU(cm) * (g.A_side + 2 * g.A_end); }
function layerUA(V_L, cm, n) { const g = tankGeometry(V_L), U = tankU(cm), ua = new Array(n).fill(U * g.A_side / n);
  ua[0] += U * g.A_end; ua[n - 1] += U * g.A_end; return ua; }

const clip01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const cycCache = new Map();
function cycleAt(c, Tc) {
  const key = `${c.Te}|${Tc.toFixed(4)}|${c.superheat}|${c.eta_t}|${c.eta_p}|${c.valve_open}`;
  let v = cycCache.get(key);
  if (!v) { v = L.solve_cycle(c.Te, Math.round(Tc * 1e4) / 1e4, c.superheat, c.eta_t, c.eta_p, c.valve_open);
    if (cycCache.size > 5000) cycCache.clear(); cycCache.set(key, v); }
  return v;
}
function weather(si, clock, c) {
  const [sin_alt, alt] = L.sun_position(clock, si.lat, si.day);
  const dni = L.beam_irradiance(sin_alt, si.day, si.clearness);
  const cos_i = c.tracking ? (sin_alt > 0 ? 1.0 : 0.0) : L.cos_incidence(clock, si.lat, si.day, c.tilt);
  const Ta = L.ambient_temperature(clock, si.T_mean, si.T_swing);
  return { alt, dni, cos_i, Ta, sin_alt };
}
/* incidence angle of the beam on the aperture [deg] (0 = normal) */
const incidenceDeg = (cos_i) => (cos_i > 0 ? Math.acos(Math.min(1, cos_i)) * 180 / Math.PI : NaN);

function instant(c, si, t_s, T) {
  const n = T.length, clock = (si.sunrise + t_s / 3600.0) % 24.0;
  const w = weather(si, clock, c), G = w.dni * w.cos_i;
  const T_top = T[0], T_bot = T[n - 1];
  const taper = clip01((c.T_max - T_top) / 3.0);
  const Qcol = c.collector_on ? L.collector_heat(G, T_bot, w.Ta, c.area, c.eta0, c.a1, c.a2) * taper : 0.0;
  const Tc = Math.max(c.Tc, w.Ta + COND_APPROACH);
  let frac = 0.0;
  if (c.pump_on) { frac = clip01((T_top - c.T_start) / RAMP); frac *= clip01(T_top - (c.Te + c.superheat + PINCH)); frac *= clip01((c.Te - Tc - MIN_LIFT) / 2.0); }
  let Tavg = 0; for (const v of T) Tavg += v; Tavg /= n;
  const out = { clock, alt: w.alt, dni: w.dni, cos_i: w.cos_i, G, Ta: w.Ta, T_top, T_bot, T_avg: Tavg, Tc, Qcol, frac,
    mdot: 0, Qev: 0, Qc: 0, Wt: 0, Wp: 0, Wnet: 0, Ex: 0, Pe: NaN, Pc: NaN, x4: NaN, eta_th: 0 };
  if (frac > 0) {
    const cyc = cycleAt(c, Tc), m = frac * c.pump_W / 1000.0 / cyc.wp, Qev = m * cyc.qin * 1000.0;
    Object.assign(out, { mdot: m, Qev, Qc: m * cyc.qout * 1000.0, Wt: m * cyc.wt * 1000.0, Wp: m * cyc.wp * 1000.0,
      Wnet: m * cyc.wnet * 1000.0, Pe: cyc.Pe, Pc: cyc.Pc, x4: cyc.x4 !== null ? cyc.x4 : 1.0, eta_th: cyc.eta_th });
    out.Ex = Qev * (1.0 - (w.Ta + K) / (T_top + K));
  }
  return out;
}
function makeRhs(c, si, n, Mi, ua) {
  const Tret_set = c.Te + PINCH;
  return (t, y) => {
    const T = y.slice(0, n), d = instant(c, si, t, T), Qcol = d.Qcol, Qev = d.Qev, Ta = d.Ta;
    const mc = M_COL * c.area * clip01(Qcol / 20.0), Tco = T[n - 1] + (mc > 0 ? Qcol / (mc * CP_W) : 0);
    const dTev = Math.max(T[0] - Tret_set, 2.0), me = Qev / (CP_W * dTev), Tret = T[0] - dTev, F = mc - me;
    const out = new Array(n + 9); let loss = 0;
    for (let i = 0; i < n; i++) {
      let q = 0;
      if (i === 0) q += mc * CP_W * (Tco - T[0]);
      if (i === n - 1) q += me * CP_W * (Tret - T[n - 1]);
      if (i > 0 && F > 0) q += F * CP_W * (T[i - 1] - T[i]);
      if (i < n - 1 && F < 0) q += -F * CP_W * (T[i + 1] - T[i]);
      if (i > 0) q += (G_MIX + G_INV * Math.max(0, T[i] - T[i - 1])) * (T[i - 1] - T[i]);
      if (i < n - 1) q += (G_MIX + G_INV * Math.max(0, T[i + 1] - T[i])) * (T[i + 1] - T[i]);
      const ql = ua[i] * (T[i] - Ta); loss += ql;
      out[i] = (q - ql) / (Mi * CP_W);
    }
    out[n] = d.G * c.area; out[n + 1] = Qcol; out[n + 2] = Qev; out[n + 3] = loss; out[n + 4] = d.Wt; out[n + 5] = d.Wp;
    out[n + 6] = d.Qc; out[n + 7] = d.Ex; out[n + 8] = d.mdot;
    return out;
  };
}
// Dormand-Prince RK45 (scipy's pair and step controller), landing exactly on a uniform output grid.
const DP_C = [0, 1 / 5, 3 / 10, 4 / 5, 8 / 9, 1, 1];
const DP_A = [[], [1 / 5], [3 / 40, 9 / 40], [44 / 45, -56 / 15, 32 / 9], [19372 / 6561, -25360 / 2187, 64448 / 6561, -212 / 729],
  [9017 / 3168, -355 / 33, 46732 / 5247, 49 / 176, -5103 / 18656], [35 / 384, 0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84]];
const DP_E = [71 / 57600, 0, -71 / 16695, 71 / 1920, -17253 / 339200, 22 / 525, -1 / 40];
function integrate(f, y0, tEnd, grid, rtol, atol, onGrid) {
  const n = y0.length; let t = 0, y = y0.slice(), h = 10.0, gi = 1, k1 = f(t, y), nfev = 1;
  onGrid(0, t, y);
  while (t < tEnd - 1e-9) {
    const tNext = Math.min(gi * grid, tEnd);
    let hUse = Math.min(h, grid, tNext - t), truncated = hUse < Math.min(h, grid) - 1e-12, ynew, k;
    for (;;) {
      k = [k1];
      for (let s = 1; s < 7; s++) {
        const ys = new Array(n);
        for (let i = 0; i < n; i++) { let a = 0; for (let j = 0; j < s; j++) a += DP_A[s][j] * k[j][i]; ys[i] = y[i] + hUse * a; }
        k.push(f(t + DP_C[s] * hUse, ys)); nfev++; if (s === 6) ynew = ys;
      }
      let sum = 0;
      for (let i = 0; i < n; i++) { let e = 0; for (let j = 0; j < 7; j++) e += DP_E[j] * k[j][i]; e *= hUse;
        const sc = atol[i] + Math.max(Math.abs(y[i]), Math.abs(ynew[i])) * rtol; sum += (e / sc) * (e / sc); }
      const norm = Math.sqrt(sum / n);
      if (norm < 1) { const fac = norm === 0 ? 10 : Math.min(10, 0.9 * Math.pow(norm, -0.2)), hn = hUse * fac; h = truncated ? Math.max(hn, h) : hn; break; }
      hUse *= Math.max(0.2, 0.9 * Math.pow(norm, -0.2)); truncated = false; h = hUse;
      if (hUse < 1e-6) throw new Error("step size too small");
    }
    t = Math.abs(t + hUse - tNext) < 1e-6 ? tNext : t + hUse; y = ynew; k1 = k[6];
    if (Math.abs(t - gi * grid) < 1e-6) { onGrid(gi, t, y); gi++; }
  }
  return nfev;
}

const simCache = new Map();
function simulate(cIn, sc, rtol = 1e-6, step_min = 5.0) {
  const c = basicLock(cIn), key = JSON.stringify([c, sc, rtol]);
  if (simCache.has(key)) return simCache.get(key);
  const si = scenarioInfo(sc), n = layersOf(c), Mi = c.tank_L / n, ua = layerUA(c.tank_L, thicknessOf(c), n);
  const tEnd = HOURS * 3600.0, grid = step_min * 60.0;
  const y0 = new Array(n).fill(sc.T_tank0).concat(new Array(9).fill(0));
  const atol = new Array(n).fill(1e-6).concat([1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-9]);
  const times = [], states = [];
  const nfev = integrate(makeRhs(c, si, n, Mi, ua), y0, tEnd, grid, rtol, atol, (gi, t, y) => { times.push(t); states.push(y.slice()); });
  const N = times.length, keys = ["clock", "alt", "dni", "cos_i", "G", "Ta", "T_top", "T_bot", "T_avg", "Tc", "Qcol", "frac", "mdot", "Qev", "Qc", "Wt", "Wp", "Wnet", "Pe", "Pc", "x4", "eta_th"];
  const S = {}; keys.forEach((q) => (S[q] = new Float64Array(N)));
  S.Qloss = new Float64Array(N); S.E_tank_kWh = new Float64Array(N); S.Q_store = new Float64Array(N);
  const th = new Float64Array(N), layers = [];
  for (let j = 0; j < n; j++) layers.push(new Float64Array(N));
  for (let i = 0; i < N; i++) {
    const T = states[i].slice(0, n), d = instant(c, si, times[i], T);
    for (const q of keys) S[q][i] = d[q];
    th[i] = times[i] / 3600.0;
    let ql = 0, e = 0; for (let j = 0; j < n; j++) { layers[j][i] = T[j]; ql += ua[j] * (T[j] - d.Ta); e += Mi * CP_W * (T[j] - sc.T_tank0); }
    S.Qloss[i] = ql; S.E_tank_kWh[i] = e / 3.6e6; S.Q_store[i] = d.Qcol - d.Qev - ql;
  }
  const wh = 1 / 3600, running = Array.from(S.frac, (v) => v > 0.05), night = Array.from(S.alt, (v) => v <= 0);
  const dt = new Float64Array(N);
  for (let i = 0; i < N; i++) dt[i] = i === 0 ? th[1] - th[0] : i === N - 1 ? th[N - 1] - th[N - 2] : 0.5 * (th[i + 1] - th[i - 1]);
  function totals(a, b) {
    let i0 = 0; while (i0 < N && th[i0] < a - 1e-9) i0++;
    let i1 = N - 1; while (i1 > 0 && th[i1] > b + 1e-9) i1--;
    const D = states[i1].slice(n).map((v, q) => (v - states[i0][n + q]) * wh);
    const [E_in, E_col, E_ev, E_loss, Wt, Wp, Qc, Ex, mass] = [D[0], D[1], D[2], D[3], D[4], D[5], D[6], D[7], D[8] / wh];
    const Wn = Wt - Wp;
    let dU = 0; for (let j = 0; j < n; j++) dU += Mi * CP_W * (layers[j][i1] - layers[j][i0]); dU *= wh;
    let run = 0, nrun = 0, eNight = 0, peak = -Infinity, tmax = -Infinity, tmin = Infinity, x4 = NaN, pe = NaN, fl = 0, df = 0;
    for (let i = i0; i <= i1; i++) {
      const w = dt[i] * (i === i0 || i === i1 ? 0.5 : 1), after = night[i] && th[i] > 1.0;
      if (running[i]) { run += w; if (after) nrun += w; if (!(x4 <= S.x4[i])) x4 = S.x4[i]; if (!(pe >= S.Pe[i])) pe = S.Pe[i];
        if (S.Tc[i] > c.Tc + 1e-6) fl += w; }
      if (layers[0][i] > c.T_max - 1.0) df += w;
      if (i < i1) { const a2 = night[i + 1] && th[i + 1] > 1.0; eNight += 0.5 * ((after ? S.Wnet[i] : 0) + (a2 ? S.Wnet[i + 1] : 0)) * (th[i + 1] - th[i]); }
      if (S.Wnet[i] > peak) peak = S.Wnet[i];
      for (let j = 0; j < n; j++) { const v = layers[j][i]; if (v > tmax) tmax = v; if (v < tmin) tmin = v; }
    }
    return { E_incident_Wh: E_in, E_collector_Wh: E_col, E_evaporator_Wh: E_ev, E_loss_Wh: E_loss, W_turbine_Wh: Wt, W_pump_Wh: Wp,
      W_net_Wh: Wn, Q_condenser_Wh: Qc, dU_tank_Wh: dU, eta_collector: E_in > 0 ? E_col / E_in : 0, eta_cycle: E_ev > 0 ? Wn / E_ev : 0,
      eta_daily: E_in > 0 ? Wn / E_in : 0, eta_II: Ex > 0 ? Wn / Ex : 0, run_hours: run, night_run_hours: nrun, W_after_sunset_Wh: eNight,
      peak_W_net: peak, Ts_max: tmax, Ts_min: tmin, x4_min: x4, Pe_max: pe, float_hours: fl, defocus_hours: df, mass_kg: mass,
      resid_tank_Wh: dU - (E_col - E_ev - E_loss), resid_cycle_Wh: E_ev - Qc - Wn };
  }
  const kpi = totals(0, 24);
  let s0 = -1; for (let i = 0; i < N && th[i] <= 24; i++) if (running[i]) { s0 = i; break; }
  let survive;
  if (s0 >= 0) { const ts = th[s0]; let ok = ts + 24 <= HOURS, fail = NaN;
    for (let i = s0; i < N && th[i] <= ts + 24 + 1e-9; i++) if (!(S.Wnet[i] > 0)) { ok = false; fail = th[i]; break; }
    const w = totals(ts, ts + 24); survive = { start_h: ts, passed: ok, fail_h: fail, w_W_net_Wh: w.W_net_Wh, w_peak_W_net: w.peak_W_net, w_eta_cycle: w.eta_cycle };
  } else survive = { start_h: NaN, passed: false, fail_h: NaN, w_W_net_Wh: 0, w_peak_W_net: 0, w_eta_cycle: 0 };
  const balance = { resid_tank_Wh: kpi.resid_tank_Wh, resid_cycle_Wh: kpi.resid_cycle_Wh,
    resid_tank_rel: Math.abs(kpi.resid_tank_Wh) / Math.max(kpi.E_collector_Wh, 1e-9), resid_cycle_rel: Math.abs(kpi.resid_cycle_Wh) / Math.max(kpi.E_evaporator_Wh, 1e-9),
    UA: ua.reduce((a, b) => a + b, 0), layers: n };
  const res = { config: c, scenario: sc, info: si, t: th, series: S, layers, kpi, survive, balance, nfev };
  if (simCache.size > 40) simCache.delete(simCache.keys().next().value);
  simCache.set(key, res);
  return res;
}
/* the cycle state points at output sample i (null when the plant is idle) */
function cycleAtSample(r, i) { return r.series.frac[i] > 0.01 ? cycleAt(r.config, r.series.Tc[i]) : null; }

// ===================================================================== game rules
const W_MIN_EFF = 300.0;
const MODES = {
  efficiency: { title: "Highest Thermal Efficiency", unit: "%", fmt: (v) => v.toFixed(2) + " %",
    goal: `Reach the highest cycle thermal efficiency (net work / heat into the evaporator) while producing at least ${W_MIN_EFF} Wh of net work over the day.` },
  output: { title: "Max Total Output", unit: "kWh", fmt: (v) => v.toFixed(3) + " kWh",
    goal: "Produce as much net work as possible over the day (sunrise to the next sunrise)." },
  survive: { title: "Survive 24 h", unit: "kWh", fmt: (v) => v.toFixed(3) + " kWh",
    goal: "Once the plant starts, keep the net power positive for the next 24 hours, through the night and into the next morning. Among runs that survive, more net work scores higher." },
};
const CONTROLS = [
  ["area", "Collector area [m^2]", 2.0, 20.0, 0.5, "Collector", false],
  ["T_max", "Collector defocus temperature [C]", 80.0, 99.0, 0.5, "Collector", false],
  ["tracking", "Sun tracking", null, null, null, "Collector", true],
  ["tilt", "Fixed tilt from horizontal [deg]", 0.0, 80.0, 1.0, "Collector", true],
  ["eta0", "Optical efficiency [-]", null, null, 0.005, "Collector", true],
  ["tank_L", "Tank volume [L]", 100.0, 2000.0, 50.0, "Storage tank", false],
  ["insulation", "Insulation level", null, null, null, "Storage tank", false],
  ["ins_cm", "Insulation thickness [cm]", 0.5, 20.0, 0.5, "Storage tank", true],
  ["Te", "Evaporating temperature [C]", 40.0, 95.0, 0.5, "Power cycle", false],
  ["Tc", "Condensing temperature [C]", 10.0, 50.0, 0.5, "Power cycle", false],
  ["superheat", "Superheat [K]", 0.0, 15.0, 0.5, "Power cycle", true],
  ["T_start", "Plant start temperature (tank top) [C]", 45.0, 99.0, 0.5, "Power cycle", false],
  ["pump_W", "Pump input power at full flow [W]", 5.0, 100.0, 1.0, "Power cycle", false],
  ["eta_t", "Turbine isentropic efficiency [-]", null, null, 0.005, "Power cycle", true],
  ["eta_p", "Pump isentropic efficiency [-]", null, null, 0.005, "Power cycle", true],
];
function controlsFor(difficulty, sc) {
  const out = [];
  for (let [name, label, lo, hi, step, group, eng] of CONTROLS) {
    if (difficulty === "basic" && (eng || name === "ins_cm")) continue;
    if (difficulty === "engineer" && name === "insulation") continue;
    if (name === "eta0" || name === "eta_t" || name === "eta_p") { const lim = limitOf(sc, name) || [BASIC_EFF[name], BASIC_EFF[name]]; lo = lim[0]; hi = lim[1]; }
    out.push([name, label, lo, hi, step, group]);
  }
  return out;
}
function defaultConfig(difficulty, sc) {
  const c = Object.assign({}, DEFAULT_CONFIG, { difficulty });
  if (difficulty === "engineer") for (const [n, lo, hi] of sc.limits) c[n] = r3(0.5 * (lo + hi));
  const si = scenarioInfo(sc);
  c.Tc = Math.max(c.Tc, Math.ceil(si.T_amb_min + COND_APPROACH + 1.0));
  return basicLock(c);
}
function clampConfig(c, sc) {
  if (c.difficulty === "basic") return basicLock(c);
  c = Object.assign({}, c); for (const [n, lo, hi] of sc.limits) c[n] = Math.min(Math.max(c[n], lo), hi); return c;
}
function score(mode, r) {
  const k = r.kpi, s = r.survive; let ok, val, msg;
  if (mode === "efficiency") { ok = k.W_net_Wh >= W_MIN_EFF; val = ok ? k.eta_cycle * 100 : 0;
    msg = ok ? `Cycle efficiency ${(k.eta_cycle * 100).toFixed(2)} % with ${k.W_net_Wh.toFixed(0)} Wh of net work.`
      : `Only ${k.W_net_Wh.toFixed(0)} Wh of net work: at least ${W_MIN_EFF} Wh is needed for the efficiency to count.`; }
  else if (mode === "output") { ok = k.W_net_Wh > 0; val = ok ? k.W_net_Wh / 1000 : 0; msg = `${(k.W_net_Wh / 1000).toFixed(3)} kWh of net work over the day.`; }
  else { ok = !!s.passed; val = ok ? s.w_W_net_Wh / 1000 : 0;
    msg = ok ? `Survived: positive net power for 24 h from start-up ${s.start_h.toFixed(1)} h after sunrise; ${val.toFixed(3)} kWh.`
      : Number.isNaN(s.start_h) ? "The plant never started, so it could not survive." : `Net power dropped to zero ${(s.fail_h - s.start_h).toFixed(1)} h after start-up.`; }
  return { mode, passed: ok, score: val, unit: MODES[mode].unit, message: msg };
}
function headline(r) { const k = r.kpi;
  return { peak_W: k.peak_W_net, total_kWh: k.W_net_Wh / 1000, heat_in_kWh: k.E_collector_Wh / 1000, heat_lost_kWh: k.E_loss_Wh / 1000,
    net_heat_kWh: (k.E_collector_Wh - k.E_loss_Wh) / 1000, after_sunset_h: k.night_run_hours, after_sunset_kWh: k.W_after_sunset_Wh / 1000,
    eta_cycle: k.eta_cycle, eta_collector: k.eta_collector, eta_daily: k.eta_daily, eta_II: k.eta_II }; }

function references(mode, difficulty, sc) {
  const base = defaultConfig(difficulty, sc), top = {}; for (const [n, lo, hi] of sc.limits) top[n] = hi;
  const ins = difficulty === "basic" ? { insulation: "good" } : { ins_cm: 20.0 };
  const tc = Math.ceil(scenarioInfo(sc).T_amb_min + COND_APPROACH + 1.0);
  if (mode === "survive") return [[55, 8], [50, 6], [60, 10]].map(([te, p]) => Object.assign({}, base, { area: 20, tank_L: 2000, Te: te, Tc: tc, T_start: te + PINCH + 1, pump_W: p, T_max: 97 }, ins, top));
  return [Object.assign({}, base, { area: 20, tank_L: 300, Te: 70, Tc: tc, T_start: 76, pump_W: 40 }, ins, top)];
}
function feasible(mode, difficulty, sc) { for (const c of references(mode, difficulty, sc)) if (score(mode, simulate(c, sc)).passed) return true; return false; }
function newScenario(mode, difficulty, seed, tries = 40) {
  const rnd = mulberry32(seed == null ? (Math.random() * 2 ** 31) | 0 : seed);
  for (let i = 0; i < tries; i++) { const sc = randomScenario(difficulty, rnd); if (!mode || feasible(mode, difficulty, sc)) return sc; }
  throw new Error("No feasible scenario found");
}
function briefing(sc) {
  const si = scenarioInfo(sc), clock = (h) => { const hh = Math.floor(h), mm = Math.round((h - hh) * 60); return `${String(hh).padStart(2, "0")}:${String(mm % 60).padStart(2, "0")}`; };
  const out = [["Scenario", si.label], ["Daylight", `${si.daylight.toFixed(1)} h (sunrise ${clock(si.sunrise)}, sunset ${clock(si.sunset)} solar time)`],
    ["Sky clearness", `${(si.clearness * 100).toFixed(0)} % of clear-sky sunlight`], ["Air temperature", `${si.T_amb_min.toFixed(1)} to ${si.T_amb_max.toFixed(1)} C (warmest at 15:00)`],
    ["Tank at sunrise", `${sc.T_tank0.toFixed(1)} C`]];
  const names = { eta_t: "Turbine efficiency", eta_p: "Pump efficiency", eta0: "Collector optical efficiency" };
  for (const [n, lo, hi] of sc.limits) out.push([names[n], `between ${lo.toFixed(3)} and ${hi.toFixed(3)} (this plant's limits)`]);
  return out;
}

// ===================================================================== checks
function inputProblems(c, sc) {
  const si = scenarioInfo(sc), p = [], need = c.Te + c.superheat + PINCH;
  if (c.Tc < si.T_amb_min + COND_APPROACH) p.push({ field: "Tc", title: "Condenser colder than the air",
    what: `A condensing temperature of ${c.Tc.toFixed(1)} C is below the coldest air of the day plus ${COND_APPROACH} K (${(si.T_amb_min + COND_APPROACH).toFixed(1)} C). Heat cannot flow from the condenser into warmer air.`,
    impact: "The condenser could never reject heat, so the vapour would not condense and the cycle would stop." });
  if (c.Te - c.Tc < MIN_LIFT) p.push({ field: "Te", title: "Temperature lift too small",
    what: `The evaporating temperature (${c.Te.toFixed(1)} C) is only ${(c.Te - c.Tc).toFixed(1)} K above the condensing temperature; the turbine needs at least ${MIN_LIFT} K.`,
    impact: "There is almost no pressure difference across the turbine, so it cannot produce work." });
  if (c.T_start < need) p.push({ field: "T_start", title: "Evaporator hotter than the tank",
    what: `The plant would start with the tank at ${c.T_start.toFixed(1)} C, but boiling at ${c.Te.toFixed(1)} C${c.superheat > 0 ? ` with ${c.superheat.toFixed(1)} K of superheat` : ""} needs water at ${need.toFixed(1)} C or more (5 K pinch).`,
    impact: "Heat cannot flow from colder water into hotter refrigerant: the evaporator would not boil the fluid." });
  if (c.T_start >= c.T_max - 0.5) p.push({ field: "T_start", title: "Start temperature above the collector limit",
    what: `The collector defocuses at ${c.T_max.toFixed(1)} C, so the tank can never reach the ${c.T_start.toFixed(1)} C start temperature.`, impact: "The plant would never start." });
  if (c.Te > TE_MAX) p.push({ field: "Te", title: "Too close to the critical point", what: `R-134a becomes supercritical at 101 C; boiling above ${TE_MAX} C is not allowed.`,
    impact: "The evaporator could not produce a two-phase boiling process." });
  return p;
}
function outcomeProblems(r) {
  const k = r.kpi, c = r.config, p = [];
  if (c.pump_on && k.run_hours < 0.1) p.push({ title: "Tank never got hot enough", what: `The top of the tank peaked at ${k.Ts_max.toFixed(1)} C, below the ${c.T_start.toFixed(1)} C start temperature.`,
    impact: "The plant never started: no flow, no work. Add collector area, use a smaller tank or lower the start and evaporating temperatures." });
  else if (c.pump_on && k.W_net_Wh <= 0) p.push({ title: "Net work is not positive", what: `The pump used ${k.W_pump_Wh.toFixed(0)} Wh and the turbine produced ${k.W_turbine_Wh.toFixed(0)} Wh.`,
    impact: "The plant consumes more work than it makes. Open the turbine valve, raise the evaporating temperature or lower the condensing temperature." });
  return p;
}
function outcomeWarnings(r) {
  const k = r.kpi, c = r.config, b = r.balance, w = [];
  if (!c.valve_open && c.pump_on) w.push(["warning", "Turbine valve closed: the vapour goes through the bypass throttle and no work is produced."]);
  if (!c.pump_on) w.push(["info", "Pump switched off: no refrigerant flow. The tank only exchanges heat with the sun and the air."]);
  if (!c.collector_on) w.push(["info", "Collector shaded: the tank receives no solar heat."]);
  if (k.run_hours >= 0.1 && k.x4_min < 0.88) w.push(["warning", `Turbine exit quality fell to ${k.x4_min.toFixed(3)}. Below about 0.88 droplets erode the blades; superheat dries the exhaust.`]);
  if (k.defocus_hours > 0.1) w.push(["warning", `The tank reached the defocus temperature for ${k.defocus_hours.toFixed(1)} h: sunlight was thrown away.`]);
  if (k.float_hours > 0.1) w.push(["warning", `For ${k.float_hours.toFixed(1)} h the air was too warm for the condenser set point; the condenser floated up to air + 3 K.`]);
  if (k.night_run_hours > 0.2) w.push(["success", `The plant ran ${k.night_run_hours.toFixed(1)} h after sunset on stored heat (${k.W_after_sunset_Wh.toFixed(0)} Wh).`]);
  if (b.resid_tank_rel < 1e-4 && b.resid_cycle_rel < 1e-6) w.push(["success", `Energy is conserved: tank residual ${b.resid_tank_rel.toExponential(1)}, cycle residual ${b.resid_cycle_rel.toExponential(1)}.`]);
  return w;
}

// ===================================================================== before / after summary
const DEVICE_ROWS = [
  ["Collector", [["E_collector_Wh", "Heat collected", "Wh"], ["eta_collector", "Collector efficiency", "%"]]],
  ["Storage tank", [["Ts_max", "Peak tank temperature", "C"], ["E_loss_Wh", "Heat lost to the air", "Wh"]]],
  ["Evaporator", [["E_evaporator_Wh", "Heat into the cycle", "Wh"], ["Pe_max", "Boiler pressure", "kPa"]]],
  ["Turbine", [["W_turbine_Wh", "Turbine work", "Wh"], ["x4_min", "Lowest exit quality", "-"]]],
  ["Condenser", [["Q_condenser_Wh", "Heat rejected", "Wh"], ["float_hours", "Hours floating above set point", "h"]]],
  ["Pump", [["W_pump_Wh", "Pump work", "Wh"], ["mass_kg", "Fluid circulated", "kg"]]],
  ["Whole plant", [["W_net_Wh", "Net work", "Wh"], ["eta_cycle", "Cycle efficiency", "%"], ["run_hours", "Run time", "h"], ["night_run_hours", "Run time after sunset", "h"]]],
];
const changedSettings = (a, b) => Object.keys(DEFAULT_CONFIG).filter((k) => a[k] !== b[k]).map((k) => [k, a[k], b[k]]);
function why(device, d, ch) {
  const has = (...k) => k.some((x) => ch.has(x)), up = d > 0;
  switch (device) {
    case "Collector": if (has("area")) return up ? "More aperture collects more sunlight." : "Less aperture collects less sunlight.";
      if (has("tracking", "tilt")) return "The aperture angle to the sun changed, so the beam on it changed.";
      if (has("eta0")) return "The optical efficiency scales the absorbed sunlight.";
      if (has("tank_L", "T_start", "Te", "pump_W")) return "Collector losses grow with its inlet temperature, which follows the tank.";
      return "Follows the tank temperature.";
    case "Storage tank": if (has("insulation", "ins_cm")) return "Insulation sets UA, the loss per kelvin above ambient.";
      if (has("tank_L")) return "A larger tank warms more slowly and stores more; a smaller one runs hotter.";
      return "The tank temperature is the balance of heat collected, drawn and lost.";
    case "Evaporator": if (has("pump_W")) return "Pump power sets the refrigerant flow, which sets the heat drawn.";
      if (has("Te", "superheat")) return "The boiling temperature sets the boiler pressure and the heat per kg.";
      return "Heat drawn follows how long the plant runs.";
    case "Turbine": if (has("Te", "Tc", "superheat", "eta_t")) return "Work per kg depends on the pressure ratio, the inlet state and the isentropic efficiency.";
      return "Turbine work follows the flow and the run time.";
    case "Condenser": if (has("Tc")) return "A colder condenser lowers the back pressure and rejects heat at a lower temperature.";
      return "Heat rejected = heat in - net work (first law).";
    case "Pump": if (has("pump_W", "eta_p")) return "Pump input power and efficiency set the flow and the pump work.";
      return "Pump work follows the run time.";
    default: return "Net work = turbine work - pump work; efficiency = net work / heat in.";
  }
}
function summary(before, after) {
  const ch = new Set(changedSettings(before.config, after.config).map((x) => x[0])), rows = [];
  for (const [dev, items] of DEVICE_ROWS) for (const [key, label, unit] of items) {
    let a = before.kpi[key], b = after.kpi[key]; if (unit === "%") { a *= 100; b *= 100; }
    const d = Number.isFinite(a) && Number.isFinite(b) ? b - a : NaN;
    rows.push({ device: dev, label, unit, before: a, after: b, delta: d, why: why(dev, Number.isFinite(d) ? d : 0, ch) });
  }
  return rows;
}

return { LAT, SEASONS, CASES, EFF_RANGES, BASIC_EFF, scenarioInfo, randomScenario, limitOf, mulberry32,
  CP_W, PINCH, COND_APPROACH, MIN_LIFT, TE_MAX, INSULATION_LEVELS, DEFAULT_CONFIG, basicLock, layersOf, thicknessOf,
  tankGeometry, tankU, tankUA, layerUA, cycleAt, cycleAtSample, incidenceDeg, instant, simulate,
  W_MIN_EFF, MODES, CONTROLS, controlsFor, defaultConfig, clampConfig, score, headline, references, feasible, newScenario, briefing,
  inputProblems, outcomeProblems, outcomeWarnings, DEVICE_ROWS, changedSettings, summary };
})();
if (typeof module !== "undefined") module.exports = Game;
