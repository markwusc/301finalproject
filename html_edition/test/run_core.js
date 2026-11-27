globalThis.window = globalThis;
globalThis.__TABLES__ = JSON.parse(require("fs").readFileSync(__dirname + "/../src/tables.json"));
const Lab = require("../src/core.js");
const ref = JSON.parse(require("fs").readFileSync(__dirname + "/py_reference.json"));
const T = __TABLES__;
let worst = {};
const upd = (k, v) => { worst[k] = Math.max(worst[k] || 0, Math.abs(v)); };
// saturation + superheat references
for (const r of T.refs) { const s = Lab.sat_state(r.T, 1), f = Lab.sat_state(r.T, 0);
  upd("P rel", (Lab.p_sat(r.T) - r.P) / r.P); upd("hg", s.h - r.hg); upd("hf", f.h - r.hf); upd("sg", s.s - r.sg); upd("sf", f.s - r.sf); upd("vg rel", (s.v - r.vg) / r.vg); }
console.log("saturation table vs CoolProp:", worst);
// cycles
const cw = {};
for (const c of ref.cyc) {
  const r = Lab.solve_cycle(c.Te, c.Tc, c.sh, c.et, c.ep, c.valve === false ? false : true);
  const d = (k, a, b) => { cw[k] = Math.max(cw[k] || 0, Math.abs(a - b)); };
  d("wp", r.wp, c.wp); d("wt", r.wt, c.wt); d("qin", r.qin, c.qin); d("qout", r.qout, c.qout); d("T2", r.s2.T, c.T2); d("s2", r.s2.s, c.s2); d("s4", r.s4.s, c.s4); d("h4", r.s4.h, c.h4);
  if (c.x4 !== null) d("x4", r.x4, c.x4); else if (r.x4 !== null) console.log("x4 mismatch (py superheated)", c, r.x4);
  cw["wnet rel"] = Math.max(cw["wnet rel"] || 0, Math.abs((r.wnet - (c.wt - c.wp)) / (c.wt - c.wp)));
}
console.log("cycle vs Python:", cw);
// steady
const st = Lab.steady_day_night({});
console.log("steady W_out", st.W_out, "py", ref.steady.W_out, "eta", st.day.eta_th, ref.steady.eta, "E_total", st.E_total, ref.steady.E_total, "tn", st.t_night, ref.steady.t_night);
// scenarios
for (const [name, sc] of Object.entries(ref.cases)) {
  const t0 = Date.now(); const r = Lab.simulate(sc.params); const dt = Date.now() - t0;
  const k = r.kpi;
  const rel = (a, b) => (b === 0 ? Math.abs(a - b) : Math.abs(a - b) / Math.abs(b));
  console.log(name.padEnd(14), `W_net ${k.W_net_Wh.toFixed(2)} (py ${sc.W_net_Wh.toFixed(2)}, rel ${rel(k.W_net_Wh, sc.W_net_Wh).toExponential(1)})`,
    `E_ev rel ${rel(k.E_evaporator_Wh, sc.E_evaporator_Wh).toExponential(1)}`, `run ${k.run_hours.toFixed(2)}/${sc.run_hours.toFixed(2)}`, `night ${k.night_run_hours.toFixed(2)}/${sc.night_run_hours.toFixed(2)}`,
    `Tmax ${k.Ts_max.toFixed(2)}/${sc.Ts_max.toFixed(2)}`, `etaII ${k.eta_II.toFixed(4)}/${sc.eta_II.toFixed(4)}`, `nfev ${r.nfev}`, `${dt} ms`, `tankres ${r.balance.resid_tank_rel.toExponential(1)}`);
}
