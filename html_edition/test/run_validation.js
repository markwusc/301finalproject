globalThis.window = globalThis;
globalThis.__TABLES__ = JSON.parse(require("fs").readFileSync(__dirname + "/../src/tables.json"));
globalThis.Lab = require("../src/core.js");
const V = require("../src/validation.js");
const t0 = Date.now();
const cs = V.runAll();
for (const c of cs) console.log((c.passed ? "PASS " : "FAIL ") + `[${c.category}] ${c.name}: ${c.value.toExponential(2)} (tol ${c.tolerance.toExponential(1)})`);
console.log(cs.filter(c => c.passed).length + "/" + cs.length, (Date.now() - t0) + " ms");
const t1 = Date.now(); console.log(V.toleranceStudy(), Date.now() - t1, "ms");
// missions: worked solutions must pass
for (const [k, m] of Object.entries(Lab.MISSIONS)) {
  const sol = Object.assign({}, m.solution); const res = Lab.missionRun(k, sol); const cr = m.evaluate(res);
  const defRes = Lab.missionRun(k, {}); const dcr = m.evaluate(defRes);
  console.log(k.padEnd(10), "solution:", cr.every(c => c[3]) ? "ALL MET" : "FAILED " + JSON.stringify(cr.filter(c => !c[3])), "| default fails:", dcr.filter(c => !c[3]).length);
}
