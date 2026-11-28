// ===================================================================== stage 4: pop-ups and change summaries
const LABELS = Object.fromEntries(G.CONTROLS.map((c) => [c[0], c[1]]).concat([["pump_on", "Pump running"], ["valve_open", "Turbine valve open"], ["collector_on", "Collector exposed"]]));
const showVal = (v) => (typeof v === "boolean" ? (v ? "on" : "off") : typeof v === "number" ? String(+v.toFixed(3)) : String(v));

/* Pop-up for physically unrealistic settings or outcomes, with Undo. */
function problemPopup(problems, title, onUndo) {
  const body = h("div", { class: "probs" }, problems.map((p) => h("div", { class: "prob" },
    h("h3", null, p.title), h("p", null, h("b", null, "What was violated. "), p.what), h("p", null, h("b", null, "Impact on the plant. "), p.impact))));
  const buttons = onUndo ? [["Undo change", "primary", onUndo], ["Keep and edit", "", null]] : [["Back to the settings", "primary", null]];
  modal(title, body, buttons);
}

/* Side panel: what changed between the last two runs, device by device, and why. */
function summaryPanel() {
  const box = h("div", { class: "sumpanel" }, h("h3", null, "Change summary"));
  if (!app.run || !app.prev) {
    box.append(h("p", { class: "cap" }, "Change some settings and press Run: this panel compares the new run with the previous one, device by device, and explains each change."));
    return box;
  }
  const ch = G.changedSettings(app.prev.config, app.run.config).filter(([k]) => k !== "difficulty");
  const scen = JSON.stringify(app.prev.scenario) !== JSON.stringify(app.run.scenario);
  box.append(h("div", { class: "chg" }, h("b", null, "You changed: "),
    ch.length ? ch.map(([k, a, b]) => h("div", null, `${LABELS[k] || k}: ${showVal(a)} -> ${showVal(b)}`)) : h("span", null, scen ? "the scenario" : "nothing (same settings)")));
  const rows = G.summary(app.prev, app.run);
  let dev = null;
  for (const r of rows) {
    if (r.device !== dev) { dev = r.device; box.append(h("div", { class: "sdev" }, dev)); }
    const d = r.delta, small = !Number.isFinite(d) || Math.abs(d) < Math.max(1e-3, 0.002 * Math.max(Math.abs(r.before || 0), Math.abs(r.after || 0)));
    const dig = r.unit === "-" ? 3 : r.unit === "%" ? 2 : r.unit === "C" || r.unit === "h" ? 1 : 0;
    const arrow = small ? "=" : d > 0 ? "▲" : "▼";
    box.append(h("div", { class: "srow" + (small ? " same" : d > 0 ? " up" : " down") },
      h("span", { class: "slab2" }, r.label), h("span", { class: "sval" }, `${fmt(r.before, dig)} -> ${fmt(r.after, dig)} ${r.unit === "-" ? "" : r.unit}`),
      h("span", { class: "sarr" }, arrow), small ? null : h("div", { class: "swhy" }, r.why)));
  }
  return box;
}
