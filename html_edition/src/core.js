/* Solar Rankine Lab - thermodynamic engine (no interface code).
 * JavaScript port of the Python package core/ (properties, solar, cycle, storage, steady,
 * simulation, missions, validation). R-134a properties come from tables generated with
 * CoolProp (ASHRAE reference state: h = s = 0 for saturated liquid at -40 C) and are
 * interpolated here; everything else is the same model as the Python app.
 * Units: T [C], P [kPa], h [kJ/kg], s [kJ/kg-K], v [m^3/kg]; rates in W, energies in Wh unless noted.
 */
const Lab = (function () {
"use strict";
const TABLES = window.__TABLES__ || (typeof globalThis !== "undefined" && globalThis.__TABLES__);
const K = 273.15;
const T_CRIT_C = TABLES.Tcrit, P_CRIT_KPA = TABLES.Pcrit;

// ===================================================================== properties
// Uniform-grid cubic Hermite interpolation with 4th-order finite-difference slopes.
function makeGrid(y, x0, h) {
  const n = y.length, m = new Float64Array(n);
  for (let i = 2; i < n - 2; i++) m[i] = (y[i - 2] - 8 * y[i - 1] + 8 * y[i + 1] - y[i + 2]) / (12 * h);
  m[0] = (-25 * y[0] + 48 * y[1] - 36 * y[2] + 16 * y[3] - 3 * y[4]) / (12 * h);
  m[1] = (-3 * y[0] - 10 * y[1] + 18 * y[2] - 6 * y[3] + y[4]) / (12 * h);
  m[n - 1] = -(-25 * y[n - 1] + 48 * y[n - 2] - 36 * y[n - 3] + 16 * y[n - 4] - 3 * y[n - 5]) / (12 * h);
  m[n - 2] = -(-3 * y[n - 1] - 10 * y[n - 2] + 18 * y[n - 3] - 6 * y[n - 4] + y[n - 5]) / (12 * h);
  return { y: Float64Array.from(y), m, x0, h, n };
}
function evalGrid(g, x) {
  let u = (x - g.x0) / g.h, i = Math.floor(u);
  if (i < 0) i = 0; else if (i > g.n - 2) i = g.n - 2;
  const t = u - i, t2 = t * t, t3 = t2 * t;
  return (2 * t3 - 3 * t2 + 1) * g.y[i] + (t3 - 2 * t2 + t) * g.h * g.m[i]
       + (-2 * t3 + 3 * t2) * g.y[i + 1] + (t3 - t2) * g.h * g.m[i + 1];
}
const SAT = {};
for (const k of ["P", "hf", "hg", "sf", "sg", "vf", "vg"]) SAT[k] = makeGrid(TABLES.sat[k], TABLES.sat.T0, TABLES.sat.dT);
const SAT_TMIN = TABLES.sat.T0, SAT_TMAX = TABLES.sat.T0 + (TABLES.sat.n - 1) * TABLES.sat.dT;
const clampT = (T) => (T < SAT_TMIN ? SAT_TMIN : T > SAT_TMAX ? SAT_TMAX : T);

const SH = TABLES.sh;                       // superheat offsets on a (Tsat, delta) grid
function shCell(Tsat, d) {
  let u = (Tsat - SH.Ts0) / SH.dTs; u = u < 0 ? 0 : u > SH.nTs - 1.000001 ? SH.nTs - 1.000001 : u;
  const i = Math.floor(u), f = u - i;
  let v = d / SH.dD; v = v < 0 ? 0 : v;
  let j = Math.floor(v); if (j > SH.nD - 2) j = SH.nD - 2;
  return [i, f, j, v - j];
}
function shAt(arr, Tsat, d) {               // bilinear (linear extrapolation beyond the superheat range)
  const [i, f, j, g] = shCell(Tsat, d), nD = SH.nD;
  const a = arr[i * nD + j], b = arr[i * nD + j + 1], c = arr[(i + 1) * nD + j], e = arr[(i + 1) * nD + j + 1];
  return (1 - f) * ((1 - g) * a + g * b) + f * ((1 - g) * c + g * e);
}
function shRow(arr, Tsat) {
  let u = (Tsat - SH.Ts0) / SH.dTs; u = u < 0 ? 0 : u > SH.nTs - 1.000001 ? SH.nTs - 1.000001 : u;
  const i = Math.floor(u), f = u - i, nD = SH.nD, row = new Float64Array(nD);
  for (let j = 0; j < nD; j++) row[j] = (1 - f) * arr[i * nD + j] + f * arr[(i + 1) * nD + j];
  return row;
}
function shInverse(arr, Tsat, target) {     // superheat d (K) at which the offset equals target (>= 0)
  const row = shRow(arr, Tsat), nD = SH.nD;
  if (target <= 0) return 0;
  let j = 0;
  while (j < nD - 2 && row[j + 1] < target) j++;
  const slope = row[j + 1] - row[j];
  return (j + (target - row[j]) / slope) * SH.dD;
}
const shDh = (Tsat, d) => shAt(SH.dh, Tsat, d);
const shDs = (Tsat, d) => shAt(SH.ds, Tsat, d);

const PM = TABLES.pump;
function vbar(Tc, Te) {
  let u = (Tc - PM.Tc0) / PM.dTc, v = (Te - PM.Te0) / PM.dTe;
  u = Math.max(0, Math.min(PM.nTc - 1.000001, u)); v = Math.max(0, Math.min(PM.nTe - 1.000001, v));
  const i = Math.floor(u), j = Math.floor(v), f = u - i, g = v - j, n = PM.nTe, a = PM.vbar;
  return (1 - f) * ((1 - g) * a[i * n + j] + g * a[i * n + j + 1]) + f * ((1 - g) * a[(i + 1) * n + j] + g * a[(i + 1) * n + j + 1]);
}

const satProp = (name, T) => evalGrid(SAT[name], clampT(T));
const p_sat = (T) => satProp("P", T);
function sat_state(T, x) {                  // saturated liquid (x = 0) or vapor (x = 1)
  const liq = x <= 0;
  return { T, P: p_sat(T), h: satProp(liq ? "hf" : "hg", T), s: satProp(liq ? "sf" : "sg", T),
           v: satProp(liq ? "vf" : "vg", T), x, phase: liq ? "liquid" : "vapor" };
}
// vapor state at pressure psat(Tsat) with entropy or enthalpy given
function vaporFromH(Tsat, h) {
  const hg = satProp("hg", Tsat), sg = satProp("sg", Tsat), hf = satProp("hf", Tsat), sf = satProp("sf", Tsat);
  const P = p_sat(Tsat);
  if (h < hg) { const x = Math.max(0, (h - hf) / (hg - hf));
    return { T: Tsat, P, h, s: sf + x * (sg - sf), x, phase: "two-phase" }; }
  const d = shInverse(SH.dh, Tsat, h - hg);
  return { T: Tsat + d, P, h, s: sg + shDs(Tsat, d), x: null, phase: "vapor" };
}
function hFromS(Tsat, s) {                  // isentropic exit enthalpy at saturation pressure of Tsat
  const hg = satProp("hg", Tsat), sg = satProp("sg", Tsat), hf = satProp("hf", Tsat), sf = satProp("sf", Tsat);
  if (s <= sg) return hf + (s - sf) / (sg - sf) * (hg - hf);
  const d = shInverse(SH.ds, Tsat, s - sg);
  return hg + shDh(Tsat, d);
}

// ===================================================================== cycle
function pump(s1, Te, Tc, eta_p) {
  const Pe = p_sat(Te), Pc = s1.P;
  const wps = vbar(Tc, Te) * (Pe - Pc);
  const wp = wps / eta_p;
  // compressed-liquid state 2 from the liquid cp and expansivity of the saturated-liquid table
  const cp = (satProp("hf", Tc + 0.25) - satProp("hf", Tc - 0.25)) / 0.5;
  const beta = (satProp("vf", Tc + 0.25) - satProp("vf", Tc - 0.25)) / 0.5 / s1.v;
  const T1K = Tc + K;
  const T2 = Tc + (beta * s1.v * T1K * (Pe - Pc) + (wp - wps)) / cp;
  const s2 = s1.s + cp * Math.log((T2 + K) / T1K) - beta * s1.v * (Pe - Pc);
  return [{ T: T2, P: Pe, h: s1.h + wp, s: s2, v: s1.v, x: null, phase: "liquid" }, wp];
}
function evaporator(s2, Te, superheat) {
  let s3;
  if (superheat > 0) {
    s3 = { T: Te + superheat, P: s2.P, h: satProp("hg", Te) + shDh(Te, superheat),
           s: satProp("sg", Te) + shDs(Te, superheat), x: null, phase: "vapor" };
  } else s3 = sat_state(Te, 1);
  return [s3, s3.h - s2.h];
}
function turbine(s3, Tc, eta_t, valve_open) {
  if (!valve_open) return [vaporFromH(Tc, s3.h), 0.0];
  const h4s = hFromS(Tc, s3.s);
  const wt = eta_t * (s3.h - h4s);
  return [vaporFromH(Tc, s3.h - wt), wt];
}
function solve_cycle(Te, Tc, superheat = 0, eta_t = 0.80, eta_p = 0.70, valve_open = true) {
  if (Te - Tc < 3.0) throw new Error("Evaporator temperature must exceed condenser temperature by 3 K.");
  if (Te > T_CRIT_C - 3.0) throw new Error("Evaporator temperature too close to the critical point.");
  const s1 = sat_state(Tc, 0);
  const [s2, wp] = pump(s1, Te, Tc, eta_p);
  const [s3, qin] = evaporator(s2, Te, superheat);
  const [s4, wt] = turbine(s3, Tc, eta_t, valve_open);
  const qout = s4.h - s1.h;
  const c = { s1, s2, s3, s4, Te, Tc, superheat, eta_t, eta_p, valve_open, wp, wt, qin, qout,
              wnet: wt - wp, eta_th: (wt - wp) / qin, x4: s4.x, Pe: s3.P, Pc: s1.P };
  c.carnot = (Th = Te, Tcold = Tc) => 1.0 - (Tcold + K) / (Th + K);
  return c;
}
function entropy_generation(c, Tsrc, Tsink) {
  const Ts = Tsrc + K, Ta = Tsink + K;
  const g = { pump: c.s2.s - c.s1.s, evaporator: (c.s3.s - c.s2.s) - c.qin / Ts,
              turbine: c.s4.s - c.s3.s, condenser: (c.s1.s - c.s4.s) + c.qout / Ta };
  g.total = g.pump + g.evaporator + g.turbine + g.condenser;
  return g;
}
const second_law_efficiency = (c, Tsrc, T0) => c.wnet / (c.qin * (1.0 - (T0 + K) / (Tsrc + K)));
const first_law_residual = (c) => c.qin - c.qout - c.wnet;

/* Polyline of the cycle on T-s axes (state markers included). */
function cycle_path(c, n = 14) {
  const S = [c.s1.s], T = [c.s1.T];
  S.push(c.s2.s); T.push(c.s2.T);
  const Pe_Tsat = c.Te;
  // 2 -> saturated liquid along the isobar: s ~ sf(T) shifted by the pump entropy offset
  const off = c.s2.s - satProp("sf", c.s2.T);
  for (let i = 0; i <= n; i++) { const t = c.s2.T + (c.Te - 0.02 - c.s2.T) * i / n; S.push(satProp("sf", t) + off * (1 - i / n)); T.push(t); }
  S.push(satProp("sf", c.Te)); T.push(c.Te);
  S.push(satProp("sg", c.Te)); T.push(c.Te);
  if (c.superheat > 0) for (let i = 1; i <= 6; i++) { const d = c.superheat * i / 6;
    S.push(satProp("sg", c.Te) + shDs(c.Te, d)); T.push(c.Te + d); }
  S.push(c.s3.s); T.push(c.s3.T);
  S.push(c.s4.s); T.push(c.s4.T);
  if (c.s4.x === null) {
    const d4 = c.s4.T - c.Tc;
    for (let i = 1; i <= 6; i++) { const d = d4 * (1 - i / 6);
      S.push(satProp("sg", c.Tc) + shDs(c.Tc, d)); T.push(c.Tc + d); }
  }
  S.push(c.s1.s); T.push(c.Tc);
  return { S, T, ms: [c.s1.s, c.s2.s, c.s3.s, c.s4.s], mt: [c.s1.T, c.s2.T, c.s3.T, c.s4.T] };
}
function saturation_dome(Tmin = 0, Tmax = 100, n = 51) {
  const T = [], sf = [], sg = [];
  for (let i = 0; i < n; i++) { const t = Tmin + (Tmax - Tmin) * i / (n - 1); T.push(t); sf.push(satProp("sf", t)); sg.push(satProp("sg", t)); }
  return { T, sf, sg };
}

// ===================================================================== solar
const SOLAR_CONSTANT = 1353.0;
const rad = (d) => d * Math.PI / 180, deg = (r) => r * 180 / Math.PI;
const declination_deg = (n) => 23.45 * Math.sin(rad(360.0 * (284 + n) / 365.0));
function hemi(lat, dec) { return lat < 0 ? [-lat, -dec] : [lat, dec]; }
function sun_position(hour, lat, n) {
  const [la, de] = hemi(lat, declination_deg(n));
  const w = rad(15.0 * (hour - 12.0));
  let s = Math.sin(rad(la)) * Math.sin(rad(de)) + Math.cos(rad(la)) * Math.cos(rad(de)) * Math.cos(w);
  s = Math.max(-1, Math.min(1, s));
  return [s, deg(Math.asin(s))];
}
function cos_incidence(hour, lat, n, tilt) {
  const [la, de] = hemi(lat, declination_deg(n));
  const w = rad(15.0 * (hour - 12.0)), phi = rad(la - tilt), d = rad(de);
  return Math.max(0, Math.sin(d) * Math.sin(phi) + Math.cos(d) * Math.cos(phi) * Math.cos(w));
}
function daylight_hours(lat, n) {
  const [la, de] = hemi(lat, declination_deg(n));
  let x = -Math.tan(rad(la)) * Math.tan(rad(de));
  x = Math.max(-1, Math.min(1, x));
  return 2.0 * deg(Math.acos(x)) / 15.0;
}
function beam_irradiance(sin_alt, n, clearness = 1.0) {
  if (sin_alt <= 0) return 0.0;
  const am = 1.0 / Math.max(sin_alt, 0.02);
  const e0 = 1.0 + 0.033 * Math.cos(rad(360.0 * n / 365.0));
  const g = SOLAR_CONSTANT * e0 * Math.pow(0.7, Math.pow(am, 0.678));
  const ramp = Math.min(1.0, sin_alt / Math.sin(rad(3.0)));
  return clearness * g * ramp;
}
function collector_heat(G, Tcol, Tamb, area, eta0, a1, a2) {
  const dT = Tcol - Tamb;
  return area * Math.max(0.0, eta0 * G - a1 * dT - a2 * dT * dT);
}
const ambient_temperature = (hour, Tmean, Tswing) => Tmean + 0.5 * Tswing * Math.cos(2.0 * Math.PI * (hour - 15.0) / 24.0);

// ===================================================================== storage tank
const CP_WATER = 4186.0, RHO_WATER = 1.0;
const tankCapacity = (L) => L * RHO_WATER * CP_WATER;               // J/K
const tankCooldown = (L, UA, T0, Tamb, t) => Tamb + (T0 - Tamb) * Math.exp(-UA * t / tankCapacity(L));

// ===================================================================== steady-state calculator
const DEFAULT_STEADY = { hours_sun: 6.0, sun_elevation: 60.0, tilt: 30.0, area: 6.0, dni: 900.0, T_amb: 25.0,
  Te: 80.0, Tc_day: 30.0, Tc_night: 20.0, pump_W: 30.0, eta_t: 0.80, eta_p: 0.70, eta_store: 0.80,
  superheat: 0.0, eta0: 0.75, a1: 1.5, a2: 0.005 };
function steady_day_night(p) {
  p = Object.assign({}, DEFAULT_STEADY, p);
  const cos_th = Math.max(0.0, Math.sin(rad(p.sun_elevation + p.tilt)));
  const g_eff = p.dni * cos_th;
  const q_sol = collector_heat(g_eff, p.Te + p.superheat, p.T_amb, p.area, p.eta0, p.a1, p.a2);
  const day = solve_cycle(p.Te, p.Tc_day, p.superheat, p.eta_t, p.eta_p);
  const m_pump = p.pump_W / 1000.0 / day.wp;
  const m_sun = q_sol / 1000.0 / day.qin;
  const m = Math.min(m_pump, m_sun);
  const q_req = m_pump * day.qin * 1000.0;
  const surplus = Math.max(0.0, q_sol - q_req);
  const o = { cos_theta: cos_th, G_eff: g_eff, Q_sol: q_sol, day, eta_collector: g_eff > 0 ? q_sol / (p.area * g_eff) : 0.0,
    m_pump, m_sun, m, Q_req: q_req, surplus, flow_limited_by: m_pump <= m_sun ? "pump" : "sunlight",
    W_turb: m * day.wt * 1000.0, W_pump: m * day.wp * 1000.0, W_out: m * day.wnet * 1000.0,
    Q_in: m * day.qin * 1000.0, Q_out: m * day.qout * 1000.0, carnot: day.carnot() };
  o.eta_system = g_eff > 0 ? o.W_out / (g_eff * p.area) : 0.0;
  let night = null, t_night = 0, w_night = 0, e_store = 0, m_night = 0;
  if (p.eta_store > 0 && surplus > 0) {
    night = solve_cycle(p.Te, p.Tc_night, p.superheat, p.eta_t, p.eta_p);
    m_night = p.pump_W / 1000.0 / night.wp;
    const q_night = m_night * night.qin * 1000.0;
    e_store = p.eta_store * surplus * p.hours_sun;
    t_night = Math.min(24.0 - p.hours_sun, e_store / q_night);
    w_night = m_night * night.wnet * 1000.0;
  }
  Object.assign(o, { night, t_night, W_night: w_night, E_store: e_store, m_night });
  o.E_day = o.W_out * p.hours_sun;
  o.E_night = w_night * t_night;
  o.E_total = o.E_day + o.E_night;
  const denom = g_eff * p.area * p.hours_sun;
  o.eta_daily = denom > 0 ? o.E_total / denom : 0.0;
  o.inputs = p;
  return o;
}

// ===================================================================== 24 h transient simulation
const TE_MAX = 95.0, MIN_LIFT = 6.0;
const DEFAULT_PLANT = { lat: 34.05, day: 172, clearness: 1.0, T_mean: 22.0, T_swing: 12.0,
  tilt: 30.0, area: 8.0, eta0: 0.75, a1: 1.5, a2: 0.005, tank_L: 500.0, UA: 3.0, T_tank0: 30.0,
  pinch: 5.0, approach_cond: 8.0, superheat: 0.0, eta_t: 0.80, eta_p: 0.70, pump_W: 30.0,
  T_cut: 70.0, T_full: 85.0, T_max: 98.0, pump_on: true, valve_open: true, collector_on: true, warmup_days: 3 };
const clip01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);

function instant(p, t_s, Ts) {
  const hour = (t_s / 3600.0) % 24.0;
  const [sin_alt, alt] = sun_position(hour, p.lat, p.day);
  const dni = beam_irradiance(sin_alt, p.day, p.clearness);
  const cos_i = cos_incidence(hour, p.lat, p.day, p.tilt);
  const g_eff = dni * cos_i;
  const Ta = ambient_temperature(hour, p.T_mean, p.T_swing);
  const taper = clip01((p.T_max - Ts) / 5.0);
  const Qcol = p.collector_on ? collector_heat(g_eff, Ts, Ta, p.area, p.eta0, p.a1, p.a2) * taper : 0.0;
  const Qloss = p.UA * (Ts - Ta);
  const Te = Math.min(Ts - p.pinch - p.superheat, TE_MAX);
  const Tc = Ta + p.approach_cond;
  let frac = p.pump_on ? clip01((Ts - p.T_cut) / Math.max(p.T_full - p.T_cut, 1e-6)) : 0.0;
  frac *= clip01((Te - Tc - MIN_LIFT) / 4.0);
  const out = { hour, alt, sin_alt, dni, cos_i, g_eff, Ta, Ts, Te, Tc, Qcol, Qloss, frac,
    mdot: 0, Qev: 0, Qc: 0, Wt: 0, Wp: 0, Wnet: 0, Ex: 0, Pe: NaN, Pc: NaN, x4: NaN, eta_th: 0 };
  if (frac > 0.0) {
    const c = solve_cycle(Te, Tc, p.superheat, p.eta_t, p.eta_p, p.valve_open);
    const m = frac * p.pump_W / 1000.0 / c.wp;
    Object.assign(out, { mdot: m, Qev: m * c.qin * 1000.0, Qc: m * c.qout * 1000.0, Wt: m * c.wt * 1000.0,
      Wp: m * c.wp * 1000.0, Wnet: m * c.wnet * 1000.0, Pe: c.Pe, Pc: c.Pc,
      x4: c.x4 !== null ? c.x4 : 1.0, eta_th: c.eta_th });
    out.Ex = out.Qev * (1.0 - (Ta + K) / (Ts + K));
  }
  return out;
}

const ATOL = [1e-8, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-9];
function makeRhs(p, C) {
  return (t, y) => { const d = instant(p, t, y[0]);
    return [(d.Qcol - d.Qev - d.Qloss) / C, d.g_eff * p.area, d.Qcol, d.Qev, d.Qloss, d.Wt, d.Wp, d.Qc, d.Ex, d.mdot]; };
}
// Dormand-Prince RK45 (same pair and step controller as scipy's solve_ivp), landing exactly on the output grid.
const DP_C = [0, 1 / 5, 3 / 10, 4 / 5, 8 / 9, 1, 1];
const DP_A = [[], [1 / 5], [3 / 40, 9 / 40], [44 / 45, -56 / 15, 32 / 9],
  [19372 / 6561, -25360 / 2187, 64448 / 6561, -212 / 729],
  [9017 / 3168, -355 / 33, 46732 / 5247, 49 / 176, -5103 / 18656],
  [35 / 384, 0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84]];
const DP_E = [71 / 57600, 0, -71 / 16695, 71 / 1920, -17253 / 339200, 22 / 525, -1 / 40];
function integrate(f, y0, tEnd, grid, rtol, maxStep, onGrid) {
  const n = y0.length;
  let t = 0, y = y0.slice(), h = 10.0, nfev = 0;
  let k1 = f(t, y); nfev++;
  let gi = 1;                                   // next grid index (grid spacing = maxStep)
  const tg = (i) => i * grid;
  onGrid(0, t, y);
  while (t < tEnd - 1e-9) {
    const tNext = Math.min(tg(gi), tEnd);
    let hUse = Math.min(h, maxStep, tNext - t), truncated = hUse < Math.min(h, maxStep) - 1e-12;
    let accepted = false, ynew, k = null;
    while (!accepted) {
      k = [k1];
      for (let s = 1; s < 7; s++) {
        const ys = new Array(n);
        for (let i = 0; i < n; i++) { let a = 0; for (let j = 0; j < s; j++) a += DP_A[s][j] * k[j][i]; ys[i] = y[i] + hUse * a; }
        k.push(f(t + DP_C[s] * hUse, ys)); nfev++;
        if (s === 6) ynew = ys;
      }
      let sum = 0;
      for (let i = 0; i < n; i++) {
        let e = 0; for (let j = 0; j < 7; j++) e += DP_E[j] * k[j][i];
        e *= hUse;
        const sc = ATOL[i] + Math.max(Math.abs(y[i]), Math.abs(ynew[i])) * rtol;
        sum += (e / sc) * (e / sc);
      }
      const norm = Math.sqrt(sum / n);
      if (norm < 1) {
        accepted = true;
        const factor = norm === 0 ? 10 : Math.min(10, 0.9 * Math.pow(norm, -0.2));
        const hn = hUse * factor;
        h = truncated ? Math.max(hn, h) : hn;
      } else {
        const factor = Math.max(0.2, 0.9 * Math.pow(norm, -0.2));
        hUse *= factor; truncated = false; h = hUse;
        if (hUse < 1e-6) throw new Error("step size too small");
      }
    }
    t = (Math.abs(t + hUse - tNext) < 1e-6) ? tNext : t + hUse;
    y = ynew; k1 = k[6];
    if (Math.abs(t - tg(gi)) < 1e-6) { onGrid(gi, t, y); gi++; }
  }
  return nfev;
}

const simCache = new Map();
function simulate(pIn, rtol = 1e-6, step_min = 5.0) {
  const p = Object.assign({}, DEFAULT_PLANT, pIn);
  const key = JSON.stringify([p, rtol]);
  if (simCache.has(key)) return simCache.get(key);
  const C = tankCapacity(p.tank_L);
  const dayS = 86400.0, t0 = p.warmup_days * dayS, tEnd = (p.warmup_days + 1) * dayS;
  const gridS = step_min * 60.0, i0 = Math.round(t0 / gridS), iN = Math.round(tEnd / gridS);
  const times = [], states = [];
  const y0 = [p.T_tank0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
  const nfev = integrate(makeRhs(p, C), y0, tEnd, gridS, rtol, 300.0, (gi, t, y) => {
    if (gi >= i0) { times.push(t); states.push(y.slice()); }
  });
  const keys = ["hour", "alt", "dni", "g_eff", "Ta", "Te", "Tc", "Qcol", "Qloss", "frac", "mdot", "Qev", "Qc", "Wt", "Wp", "Wnet", "Pe", "Pc", "x4", "eta_th"];
  const N = times.length, S = {};
  keys.forEach((kk) => (S[kk] = new Float64Array(N)));
  S.Ts = new Float64Array(N);
  const th = new Float64Array(N);
  for (let i = 0; i < N; i++) {
    const d = instant(p, times[i], states[i][0]);
    for (const kk of keys) S[kk][i] = d[kk];
    S.Ts[i] = states[i][0];
    th[i] = (times[i] - t0) / 3600.0;
  }
  const Y0 = states[0], Y1 = states[N - 1], D = Y1.map((v, i) => v - Y0[i]);
  const wh = 1.0 / 3600.0;
  const running = Array.from(S.frac, (v) => v > 0.05), night = Array.from(S.alt, (v) => v <= 0.0);
  const dt_h = new Float64Array(N);
  for (let i = 0; i < N; i++) {
    const a = i > 0 ? th[i] - th[i - 1] : th[1] - th[0], b = i < N - 1 ? th[i + 1] - th[i] : th[N - 1] - th[N - 2];
    dt_h[i] = i === 0 ? a / 2 : i === N - 1 ? b / 2 : (a + b) / 2;
  }
  let run_hours = 0, night_run = 0;
  for (let i = 0; i < N; i++) if (running[i]) { run_hours += dt_h[i]; if (night[i]) night_run += dt_h[i]; }
  const E_in = D[1] * wh, E_col = D[2] * wh, E_ev = D[3] * wh, E_loss = D[4] * wh;
  const Wt_d = D[5] * wh, Wp_d = D[6] * wh, Qc_d = D[7] * wh, Ex_d = D[8] * wh, W_net = Wt_d - Wp_d;
  let x4min = NaN, pemax = NaN;
  for (let i = 0; i < N; i++) if (running[i]) { if (!(x4min <= S.x4[i])) x4min = S.x4[i]; }
  for (let i = 0; i < N; i++) if (running[i] && !(S.Pe[i] <= pemax)) pemax = S.Pe[i];
  const mx = (a) => a.reduce((m, v) => (v > m ? v : m), -Infinity), mn = (a) => a.reduce((m, v) => (v < m ? v : m), Infinity);
  const kpi = { E_incident_Wh: E_in, E_collector_Wh: E_col, E_evaporator_Wh: E_ev, E_loss_Wh: E_loss,
    W_turbine_Wh: Wt_d, W_pump_Wh: Wp_d, W_net_Wh: W_net, Q_condenser_Wh: Qc_d,
    eta_collector: E_in > 0 ? E_col / E_in : 0, eta_cycle: E_ev > 0 ? W_net / E_ev : 0,
    eta_daily: E_in > 0 ? W_net / E_in : 0, eta_II: Ex_d > 0 ? W_net / Ex_d : 0,
    run_hours, night_run_hours: night_run, peak_W_net: mx(S.Wnet), Ts_max: mx(S.Ts), Ts_min: mn(S.Ts),
    x4_min: running.some(Boolean) ? x4min : NaN, mass_circulated_kg: D[9],
    Pe_max: running.some(Boolean) ? pemax : NaN };
  const dU = C * (Y1[0] - Y0[0]) * wh;
  const resid_tank = dU - (E_col - E_ev - E_loss), resid_cycle = E_ev - Qc_d - W_net;
  const trap = (a, x) => { let s = 0; for (let i = 0; i < N - 1; i++) s += 0.5 * (a[i] + a[i + 1]) * (x[i + 1] - x[i]); return s; };
  const tsec = Array.from(th, (v) => v * 3600), mflow = Array.from(S.mdot, (v, i) => (S.Wp[i] > 0 ? v : 0));
  const balance = { dU_tank_Wh: dU, resid_tank_Wh: resid_tank, resid_tank_rel: Math.abs(resid_tank) / Math.max(E_col, 1e-9),
    resid_cycle_Wh: resid_cycle, resid_cycle_rel: Math.abs(resid_cycle) / Math.max(E_ev, 1e-9),
    trap_E_col_Wh: trap(S.Qcol, th), trap_E_ev_Wh: trap(S.Qev, th), mass_from_pump_kg: trap(mflow, tsec) };
  const res = { params: p, t: th, series: S, kpi, balance, nfev };
  if (simCache.size > 60) simCache.delete(simCache.keys().next().value);
  simCache.set(key, res);
  return res;
}

// ===================================================================== missions
const crit = (label, actual, req, ok) => [label, actual, req, !!ok];
const Q = (c) => (c.x4 === null ? 1.0 : c.x4);
const Qtxt = (c) => (c.x4 === null ? "superheated" : c.x4.toFixed(3));
const MISSIONS = {};
function addMission(m) { MISSIONS[m.key] = m; }
addMission({ key: "rankine", title: "Rankine Challenge: efficiency", kind: "steady",
  brief: "The plant is limited by temperature, not by sunlight. Improve the thermal efficiency of the cycle without letting the turbine ingest too much liquid.",
  objective: "Reach a cycle thermal efficiency of 11 % or more.",
  fixed: { area: 10.0, pump_W: 30.0, hours_sun: 6.0, sun_elevation: 60.0, tilt: 30.0, dni: 900.0, T_amb: 25.0 },
  knobs: { Te: ["Evaporator temperature [C]", 50.0, 100.0, 80.0, 0.5], Tc_day: ["Condenser temperature [C]", 15.0, 45.0, 30.0, 0.5],
           superheat: ["Superheat [K]", 0.0, 30.0, 0.0, 1.0], eta_t: ["Turbine efficiency", 0.60, 0.88, 0.80, 0.01] },
  hint: "Raise Te, keep the condenser as cold as the rules allow, and buy turbine efficiency. Superheat dries the exhaust but lowers the average heat-addition temperature.",
  solution: { Te: 95.0, Tc_day: 25.0, superheat: 0.0, eta_t: 0.86 },
  evaluate(o) { const d = o.day, p = o.inputs, x4 = Q(d);
    return [crit("Thermal efficiency", (d.eta_th * 100).toFixed(2) + " %", ">= 11.0 %", d.eta_th >= 0.11),
      crit("Turbine exit quality", Qtxt(d), ">= 0.88", x4 >= 0.88),
      crit("Condenser temperature", p.Tc_day.toFixed(1) + " C", ">= 25 C (hot-climate air cooling)", p.Tc_day >= 25.0),
      crit("Evaporator temperature", p.Te.toFixed(1) + " C", "<= 95 C (critical point is 101 C)", p.Te <= 95.0)]; } });
addMission({ key: "turbine", title: "Turbine Challenge: power output", kind: "steady",
  brief: "A small off-grid load needs 260 W. Size the pump and collector so that the sun can boil all of the flow the pump delivers.",
  objective: "Deliver 260 W net (within 5 %) with at most 40 W of pump power and 5 m^2 of collector.",
  fixed: { hours_sun: 6.0, sun_elevation: 60.0, tilt: 30.0, dni: 900.0, T_amb: 25.0, Tc_day: 30.0, eta_t: 0.80, eta_p: 0.70 },
  knobs: { area: ["Collector area [m^2]", 2.0, 14.0, 6.0, 0.1], pump_W: ["Pump input power [W]", 5.0, 60.0, 30.0, 0.5],
           Te: ["Evaporator temperature [C]", 50.0, 95.0, 80.0, 0.5] },
  hint: "Net power is roughly pump power times (w_t/w_p - 1): a higher evaporator temperature raises w_t/w_p, but the collector then loses more heat to the air.",
  solution: { area: 5.0, pump_W: 40.0, Te: 85.0 },
  evaluate(o) { const d = o.day, p = o.inputs, x4 = Q(d);
    return [crit("Net power output", o.W_out.toFixed(0) + " W", "260 W +/- 5 %", o.W_out >= 247.0 && o.W_out <= 273.0),
      crit("Pump input power", p.pump_W.toFixed(0) + " W", "<= 40 W", p.pump_W <= 40.0),
      crit("Collector area", p.area.toFixed(1) + " m^2", "<= 5 m^2", p.area <= 5.0),
      crit("Flow supplied by the sun", (o.m / o.m_pump * 100).toFixed(0) + " % of pump flow", ">= 99 %", o.m >= 0.99 * o.m_pump),
      crit("Turbine exit quality", Qtxt(d), ">= 0.88", x4 >= 0.88)]; } });
addMission({ key: "night", title: "Night-Shift Challenge: day/night operation", kind: "day",
  brief: "Make the plant follow the day/night cycle. The tank stores daytime heat; run the cycle for at least six hours after the sun has set, without overheating the tank.",
  objective: "Run 6 h or more after sunset, produce 1800 Wh or more, keep the tank at or below 96 C.",
  fixed: { lat: 34.05, day: 172, clearness: 0.95 },
  knobs: { area: ["Collector area [m^2]", 4.0, 16.0, 8.0, 0.5], tank_L: ["Storage volume [L]", 100.0, 2000.0, 500.0, 50.0],
           pump_W: ["Pump input power [W]", 10.0, 60.0, 30.0, 1.0], T_cut: ["Plant start temperature [C]", 55.0, 90.0, 70.0, 1.0],
           T_full: ["Full-flow temperature [C]", 60.0, 95.0, 85.0, 1.0] },
  hint: "Night hours come from stored heat: more storage and a lower start temperature keep the turbine turning longer, but a lower tank temperature costs cycle efficiency.",
  solution: { area: 14.0, tank_L: 900.0, pump_W: 22.0, T_cut: 60.0, T_full: 78.0 },
  evaluate(r) { const k = r.kpi;
    return [crit("Operating hours after sunset", k.night_run_hours.toFixed(1) + " h", ">= 6 h", k.night_run_hours >= 6.0),
      crit("Daily net work", k.W_net_Wh.toFixed(0) + " Wh", ">= 1800 Wh", k.W_net_Wh >= 1800.0),
      crit("Peak tank temperature", k.Ts_max.toFixed(1) + " C", "<= 96 C", k.Ts_max <= 96.0),
      crit("Minimum turbine exit quality", k.x4_min.toFixed(3), ">= 0.88", k.x4_min >= 0.88)]; } });
addMission({ key: "tank", title: "Transient Challenge: heat the tank", kind: "day",
  brief: "A cold tank (25 C) is heated by the sun alone, with the pump switched off. Reach the target temperature by solar noon without boiling the collector loop.",
  objective: "Tank at 80 C or more by 12:00 with at most 14 m^2 of collector and at least 400 L of water.",
  fixed: { lat: 34.05, day: 80, clearness: 0.95, pump_on: false, warmup_days: 0, T_tank0: 25.0 },
  knobs: { area: ["Collector area [m^2]", 4.0, 20.0, 8.0, 0.5], tilt: ["Collector tilt [deg]", 0.0, 80.0, 30.0, 1.0],
           tank_L: ["Storage volume [L]", 100.0, 1500.0, 500.0, 50.0] },
  hint: "Heating a larger tank takes more energy: the collector must deliver m c dT before noon, so area and an incidence angle near 0 matter more than anything else.",
  solution: { area: 14.0, tilt: 34.0, tank_L: 400.0 },
  evaluate(r) { let i = 0, best = 1e9; r.t.forEach((v, j) => { if (Math.abs(v - 12) < best) { best = Math.abs(v - 12); i = j; } });
    const T12 = r.series.Ts[i], k = r.kpi;
    return [crit("Tank temperature at 12:00 solar time", T12.toFixed(1) + " C", ">= 80 C", T12 >= 80.0),
      crit("Collector area", r.params.area.toFixed(1) + " m^2", "<= 14 m^2 (roof space)", r.params.area <= 14.0),
      crit("Tank volume", r.params.tank_L.toFixed(0) + " L", ">= 400 L (hot-water demand)", r.params.tank_L >= 400.0),
      crit("Peak tank temperature", k.Ts_max.toFixed(1) + " C", "<= 98 C", k.Ts_max <= 98.0)]; } });
addMission({ key: "integrated", title: "Integrated System Challenge", kind: "day",
  brief: "Combine everything: collector, tank, pump and cycle controls. Maximise the daily work while the pump stays economical and every limit is respected.",
  objective: "At least 2400 Wh net, pump work no more than 11 % of turbine work, tank at or below 97 C, exit quality 0.88 or more.",
  fixed: { lat: 34.05, day: 172, clearness: 0.95 },
  knobs: { area: ["Collector area [m^2]", 4.0, 14.0, 8.0, 0.5], tank_L: ["Storage volume [L]", 200.0, 1000.0, 500.0, 50.0],
           pump_W: ["Pump input power [W]", 10.0, 50.0, 30.0, 1.0], superheat: ["Superheat [K]", 0.0, 4.0, 0.0, 0.5],
           T_cut: ["Plant start temperature [C]", 55.0, 90.0, 70.0, 1.0], T_full: ["Full-flow temperature [C]", 60.0, 95.0, 85.0, 1.0] },
  hint: "Every watt of pump power buys mass flow, and mass flow drains the tank. A hot tank raises cycle efficiency; a cold tank stores more heat per degree.",
  solution: { area: 13.5, tank_L: 650.0, pump_W: 26.0, superheat: 3.5, T_cut: 58.0, T_full: 72.0 },
  evaluate(r) { const k = r.kpi, b = r.balance, ratio = k.W_turbine_Wh > 0 ? k.W_pump_Wh / k.W_turbine_Wh : 1.0;
    return [crit("Daily net work", k.W_net_Wh.toFixed(0) + " Wh", ">= 2400 Wh", k.W_net_Wh >= 2400.0),
      crit("Pump work / turbine work", (ratio * 100).toFixed(1) + " %", "<= 11 %", ratio <= 0.11),
      crit("Peak tank temperature", k.Ts_max.toFixed(1) + " C", "<= 97 C", k.Ts_max <= 97.0),
      crit("Minimum turbine exit quality", k.x4_min.toFixed(3), ">= 0.88", k.x4_min >= 0.88),
      crit("Energy-balance closure", b.resid_tank_rel.toExponential(1), "<= 1e-4", b.resid_tank_rel <= 1e-4)]; } });
function missionInputs(m, choice) {
  const vals = {};
  for (const [k, v] of Object.entries(m.knobs)) vals[k] = v[3];
  Object.assign(vals, choice, m.fixed);
  return vals;
}
function missionRun(key, choice) {
  const m = MISSIONS[key], vals = missionInputs(m, choice);
  return m.kind === "steady" ? steady_day_night(vals) : simulate(vals);
}
function engineering_rating(o, kind) {
  if (kind === "steady") return { "Thermal efficiency [%]": o.day.eta_th * 100, "Fraction of Carnot": o.day.eta_th / o.day.carnot(), "Net power [W]": o.W_out };
  return { "Daily net work [Wh]": o.kpi.W_net_Wh, "Cycle efficiency [%]": o.kpi.eta_cycle * 100,
           "Second-law efficiency [%]": o.kpi.eta_II * 100, "Energy-balance residual": o.balance.resid_tank_rel };
}

// ===================================================================== feedback
function feedback(r) {
  const p = r.params, k = r.kpi, b = r.balance, out = [];
  if (!p.pump_on) out.push(["info", "Pump switched off: no mass flow and no power. The tank only exchanges heat with the sun and the air."]);
  else if (k.run_hours < 0.1) out.push(["error", `The plant never started. The tank stayed below the start temperature (${p.T_cut.toFixed(0)} C). Add collector area, lower the start temperature, or reduce the tank volume.`]);
  if (!p.valve_open && p.pump_on) out.push(["warning", "Turbine valve closed: all the heat goes through the bypass throttle to the condenser and no work is produced."]);
  if (k.run_hours >= 0.1 && k.x4_min < 0.88) out.push(["warning", `Turbine exit quality fell to ${k.x4_min.toFixed(2)}. Below about 0.88 liquid droplets erode the blades.`]);
  if (k.Ts_max >= p.T_max - 1.0) out.push(["warning", "The tank reached the collector limit and the collector defocused. Daytime heat was thrown away: add storage, flow or turbine power."]);
  if (k.run_hours >= 0.1 && k.Pe_max > 0.85 * 4059) out.push(["warning", "Evaporator pressure is within 15 % of the critical pressure of R-134a."]);
  if (k.night_run_hours > 0.5) out.push(["success", `The plant ran ${k.night_run_hours.toFixed(1)} h after sunset on stored heat.`]);
  if (b.resid_tank_rel < 1e-4 && b.resid_cycle_rel < 1e-6) out.push(["success", `Conservation: tank energy residual ${b.resid_tank_rel.toExponential(1)}, cycle residual ${b.resid_cycle_rel.toExponential(1)}.`]);
  else out.push(["error", "Energy balance does not close; tighten the solver tolerance."]);
  return out;
}

return { K, T_CRIT_C, P_CRIT_KPA, TABLES, satProp, p_sat, sat_state, solve_cycle, entropy_generation, second_law_efficiency,
  first_law_residual, cycle_path, saturation_dome, shDs, shDh, declination_deg, sun_position, daylight_hours, beam_irradiance,
  cos_incidence, collector_heat, ambient_temperature, tankCapacity, tankCooldown, DEFAULT_STEADY, steady_day_night,
  DEFAULT_PLANT, instant, simulate, MISSIONS, missionInputs, missionRun, engineering_rating, feedback };
})();
if (typeof module !== "undefined") module.exports = Lab;
