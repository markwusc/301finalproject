/* Numerical and physical validation checks (JavaScript port of core/validation.py, plus checks against
 * reference values that were computed offline with CoolProp by the Python version of the lab). */
const LabValidation = (function () {
"use strict";
const L = Lab, K = L.K, T = L.TABLES;
const chk = (cat, name, value, tol, note = "", upper = true) =>
  ({ category: cat, name, value, tolerance: tol, passed: upper ? Math.abs(value) <= tol : value >= tol, note });
const rel = (a, b) => Math.abs(a - b) / Math.max(Math.abs(b), 1e-12);

function checkProperties() {
  const out = [];
  out.push(chk("Properties", "Critical temperature vs 101.06 C [K error]", L.T_CRIT_C - 101.06, 0.05, "value stored with the tables"));
  out.push(chk("Properties", "Saturation pressure at -26.07 C vs 101.325 kPa [rel. error]", (L.p_sat(-26.07) - 101.325) / 101.325, 0.003, "normal boiling point"));
  let worst = 0;
  for (const t of [0, 20, 40, 60, 80]) {
    const dT = 0.05, dpdt = (L.p_sat(t + dT) - L.p_sat(t - dT)) / (2 * dT);
    const f = L.sat_state(t, 0), g = L.sat_state(t, 1);
    const rhs = (g.h - f.h) / ((t + K) * (g.v - f.v));
    worst = Math.max(worst, Math.abs(dpdt - rhs) / rhs);
  }
  out.push(chk("Properties", "Clapeyron relation, worst of 5 temperatures [rel. error]", worst, 2e-3, "dP/dT = h_fg/(T v_fg), independent of the stored data"));
  let wP = 0, wh = 0, ws = 0;
  for (const r of T.refs) { const g = L.sat_state(r.T, 1), f = L.sat_state(r.T, 0);
    wP = Math.max(wP, rel(L.p_sat(r.T), r.P)); wh = Math.max(wh, rel(g.h, r.hg), rel(f.h + 1000, r.hf + 1000)); ws = Math.max(ws, Math.abs(g.s - r.sg), Math.abs(f.s - r.sf)); }
  out.push(chk("Properties", "Saturation table vs CoolProp at 6 off-grid temperatures, worst of P and h [rel.]", Math.max(wP, wh), 1e-5, "reference computed offline with CoolProp"));
  out.push(chk("Properties", "Saturation entropy vs CoolProp at the same points [kJ/kg-K]", ws, 1e-5));
  let wH = 0, wS = 0;
  for (const r of T.refs_sh) { const h = L.satProp("hg", r.Tsat) + L.shDh(r.Tsat, r.d), s = L.satProp("sg", r.Tsat) + L.shDs(r.Tsat, r.d);
    wH = Math.max(wH, Math.abs(h - r.h)); wS = Math.max(wS, Math.abs(s - r.s)); }
  out.push(chk("Properties", "Superheated-vapor table vs CoolProp at 6 off-grid states, h [kJ/kg]", wH, 0.02));
  out.push(chk("Properties", "Superheated-vapor table vs CoolProp at the same states, s [kJ/kg-K]", wS, 5e-5));
  return out;
}

function checkCycle() {
  const out = [], grid = [];
  for (const Te of [50, 70, 90]) for (const Tc of [15, 30, 45]) for (const sh of [0, 10]) for (const et of [0.6, 0.85]) if (Te - Tc >= 10) grid.push([Te, Tc, sh, et]);
  let r1 = 0, r2 = 0, sgenMin = 1.0, carnotOk = true;
  for (const [Te, Tc, sh, et] of grid) {
    const c = L.solve_cycle(Te, Tc, sh, et, 0.7);
    r1 = Math.max(r1, Math.abs(L.first_law_residual(c)) / c.qin);
    const g = L.entropy_generation(c, Te + sh, Tc);
    sgenMin = Math.min(sgenMin, g.pump, g.evaporator, g.turbine, g.condenser, g.total);
    carnotOk = carnotOk && c.eta_th < c.carnot();
    r2 = Math.max(r2, Math.abs(g.total - (c.qout / (Tc + K) - c.qin / (Te + sh + K))));
  }
  out.push(chk("Cycle", `First law q_in - q_out - w_net over ${grid.length} cases [rel.]`, r1, 1e-6));
  out.push(chk("Cycle", "Second law: eta_th below Carnot in every case", carnotOk ? 0 : 1, 0));
  out.push(chk("Cycle", "Entropy generation sum equals q_out/Tc - q_in/T_source [kJ/kg-K]", r2, 1e-9));
  out.push(chk("Cycle", "Entropy generation of every device >= 0 [min over all cases, kJ/kg-K]", sgenMin, -1e-8, "pump, evaporator, turbine, condenser; tolerance = table-interpolation consistency of T s_fg vs h_fg", false));
  const c = L.solve_cycle(80, 30, 0, 0.8, 0.7), m = 30.0 / 1000.0 / c.wp;
  out.push(chk("Cycle", "Pump power recovered from m_dot * w_p [W error]", m * c.wp * 1000 - 30.0, 1e-9));
  let w = 0;
  for (const r of T.refs_cycle) { const q = L.solve_cycle(r.Te, r.Tc, r.sh, r.et, r.ep, r.valve === false ? false : true);
    w = Math.max(w, Math.abs(q.wnet - (r.wt - r.wp)) / Math.abs(r.wt - r.wp || 1), Math.abs(q.qin - r.qin) / r.qin); }
  out.push(chk("Cycle", `Net work and heat input vs CoolProp reference over ${T.refs_cycle.length} cases [rel.]`, w, 1e-3, "includes superheat and a closed turbine valve"));
  return out;
}

function checkGeometry() {
  const out = [];
  let [, alt] = L.sun_position(12.0, 0.0, 80);
  out.push(chk("Solar", "Equatorial solar-noon altitude at equinox vs 90 deg", alt - (90 - Math.abs(L.declination_deg(80))), 0.01));
  out.push(chk("Solar", "Equatorial day length vs 12 h", L.daylight_hours(0.0, 80) - 12.0, 0.02));
  const lat = 34.05, d = 172;
  [, alt] = L.sun_position(12.0, lat, d);
  out.push(chk("Solar", "Solar-noon altitude = 90 - |lat - decl| [deg error]", alt - (90 - Math.abs(lat - L.declination_deg(d))), 1e-6));
  return out;
}

function checkTransient() {
  const p = Object.assign({}, L.DEFAULT_PLANT), r = L.simulate(p), b = r.balance, S = r.series, out = [];
  out.push(chk("Energy", "Tank energy balance dU = Q_col - Q_evap - Q_loss [rel. to Q_col]", b.resid_tank_rel, 1e-5));
  out.push(chk("Energy", "Cycle energy balance Q_evap - Q_cond - W_net [rel. to Q_evap]", b.resid_cycle_rel, 1e-8));
  out.push(chk("Energy", "Collector heat: solver quadrature vs 5-min trapezoid [rel.]", (b.trap_E_col_Wh - r.kpi.E_collector_Wh) / r.kpi.E_collector_Wh, 5e-3));
  out.push(chk("Mass", "Circulated mass: solver quadrature vs trapezoid [rel.]", (b.mass_from_pump_kg - r.kpi.mass_circulated_kg) / Math.max(r.kpi.mass_circulated_kg, 1e-9), 5e-3));
  const idx = []; for (let i = 0; i < S.frac.length; i++) if (S.frac[i] > 0.2) idx.push(i);
  const stride = Math.max(1, Math.floor(idx.length / 25)), pick = idx.filter((_, j) => j % stride === 0);
  let worst = 0;
  for (const i of pick) { const c = L.solve_cycle(S.Te[i], S.Tc[i], p.superheat, p.eta_t, p.eta_p, p.valve_open), m = S.mdot[i];
    for (const f of [S.Wp[i] / (c.wp * 1000), S.Wt[i] / (c.wt * 1000), S.Qev[i] / (c.qin * 1000), S.Qc[i] / (c.qout * 1000)]) worst = Math.max(worst, Math.abs(f - m) / m); }
  out.push(chk("Mass", `Flow recovered from pump, turbine, evaporator and condenser rates vs m_dot (${pick.length} instants) [rel.]`, worst, 1e-9));
  const q = Object.assign({}, p, { collector_on: false, pump_on: false, T_swing: 0.0, warmup_days: 0, T_tank0: 90.0 });
  const rq = L.simulate(q);
  let e = 0; for (let i = 0; i < rq.t.length; i++) e = Math.max(e, Math.abs(rq.series.Ts[i] - L.tankCooldown(q.tank_L, q.UA, 90.0, q.T_mean, rq.t[i] * 3600.0)));
  out.push(chk("Transient", "Cool-down vs analytic exponential, max error [K]", e, 1e-4));
  const lo = L.simulate(p, 1e-4).kpi.W_net_Wh, hi = L.simulate(p, 1e-9).kpi.W_net_Wh;
  out.push(chk("Numerics", "Daily net work, rtol 1e-4 vs 1e-9 [rel. change]", (lo - hi) / hi, 1e-3));
  out.push(chk("Numerics", "Tank energy change over the reported day (periodic state) [Wh]", b.dU_tank_Wh, 1.0, "three warm-up days"));
  return out;
}

function checkSteadyVsTransient() {
  const inst = L.steady_day_night({ Te: 80.0, Tc_day: 30.0 });
  const p = Object.assign({}, L.DEFAULT_PLANT, { T_cut: 79.0, T_full: 79.1, pump_W: 30.0, approach_cond: 0.0, T_swing: 0.0, T_mean: 30.0, pinch: 0.0 });
  const d = L.instant(p, 12 * 3600.0, 80.0);
  return [chk("Consistency", "Steady vs transient plant: net power at Te=80 C, Tc=30 C [rel.]", (d.Wnet - inst.W_out) / inst.W_out, 1e-6, "same cycle, same pump power")];
}

function checkReference() {
  const out = [];
  for (const [name, sc] of Object.entries(T.refs_scen)) {
    const k = L.simulate(sc.params).kpi;
    out.push(chk("CoolProp reference", `Daily net work vs Python/CoolProp version (${name}) [rel., or Wh if zero]`,
      sc.W_net_Wh === 0 ? k.W_net_Wh : (k.W_net_Wh - sc.W_net_Wh) / Math.abs(sc.W_net_Wh), sc.W_net_Wh === 0 ? 0.01 : 5e-4));
    out.push(chk("CoolProp reference", `Run time vs Python/CoolProp version (${name}) [h]`, k.run_hours - sc.run_hours, 0.1, "one 5 min output step"));
  }
  const st = L.steady_day_night({}), rs = T.refs_steady;
  out.push(chk("CoolProp reference", "Steady calculator W_out vs Python/CoolProp version [rel.]", (st.W_out - rs.W_out) / rs.W_out, 5e-4));
  return out;
}

function runAll() {
  return [].concat(checkProperties(), checkCycle(), checkGeometry(), checkTransient(), checkSteadyVsTransient(), checkReference());
}
function toleranceStudy() {
  return [1e-3, 1e-4, 1e-6, 1e-9].map((t) => { const r = L.simulate(L.DEFAULT_PLANT, t); return { rtol: t, W_net_Wh: r.kpi.W_net_Wh, nfev: r.nfev }; });
}
return { runAll, toleranceStudy };
})();
if (typeof module !== "undefined") module.exports = LabValidation;
