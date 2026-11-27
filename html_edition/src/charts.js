/* Tiny dependency-free SVG chart toolkit: line charts with hover tooltips, T-s diagrams, waterfall, bars.
 * Colour follows the lab's fixed categorical order (blue, orange, aqua, yellow); one y-axis per chart. */
const BLUE = "#257de0", ORANGE = "#f47230", AQUA = "#00b894", YELLOW = "#f2a600", GREY = "#8a8a8a";
const INK = "#191919", INK2 = "#666666", GRIDC = "#e6e6e6", NIGHTC = "rgba(60,70,110,0.10)";

function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const c of kids.flat(Infinity)) { if (c == null || c === false) continue; e.append(c.nodeType ? c : document.createTextNode(String(c))); }
  return e;
}
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function niceTicks(lo, hi, n = 5) {
  if (!(hi > lo)) { hi = lo + 1; }
  const raw = (hi - lo) / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / mag;
  const step = (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * mag;
  const ticks = [];
  for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + step * 1e-9; v += step) ticks.push(+v.toPrecision(12));
  return { ticks, step };
}
function tickLabel(v, step) {
  const d = step >= 1 ? 0 : Math.min(4, Math.ceil(-Math.log10(step) - 1e-9));
  const s = Math.abs(v) >= 10000 ? v.toLocaleString("en-US", { maximumFractionDigits: 0 }) : v.toFixed(d);
  return s === "-0" ? "0" : s;
}
const groups = {};

class Chart {
  constructor(el, cfg) {
    this.el = el; this.cfg = cfg; el.classList.add("chart");
    this.head = h("div", { class: "chead" }); this.plot = h("div", { class: "cplot" }); this.tip = h("div", { class: "tip" });
    this.plot.append(this.tip); el.append(this.head, this.plot);
    if (cfg.group) (groups[cfg.group] = groups[cfg.group] || []).push(this);
    this.plot.addEventListener("pointermove", (e) => this.onMove(e));
    this.plot.addEventListener("pointerleave", () => this.hide());
    this.lastW = 0;
    this.ro = new ResizeObserver(() => { if (Math.abs(this.el.clientWidth - this.lastW) > 2) this.draw(); });
    this.ro.observe(el);
    this.draw();
  }
  update(cfg) { this.cfg = Object.assign(this.cfg, cfg); this.draw(); }
  draw() {
    const c = this.cfg, W = Math.max(this.el.clientWidth || 600, 260); this.lastW = W;
    const Hh = c.height || 220, m = Object.assign({ l: 56, r: 14, t: 8, b: c.xlabel ? 40 : 24 }, c.margin || {});
    const pw = W - m.l - m.r, ph = Hh - m.t - m.b;
    const [x0, x1] = c.xlim;
    let y0, y1;
    if (c.ylim) [y0, y1] = c.ylim;
    else {
      let lo = Infinity, hi = -Infinity;
      for (const s of c.series) for (const v of s.y) if (Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; }
      if (!Number.isFinite(lo)) { lo = 0; hi = 1; }
      if (c.includeZero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
      if (hi - lo < 1e-9) { hi = lo + 1; }
      const pad = 0.06 * (hi - lo); lo = (c.includeZero && lo >= 0) ? 0 : lo - pad; hi += pad;
      const nt = niceTicks(lo, hi, 4); y0 = nt.ticks[0] > lo ? nt.ticks[0] - nt.step : nt.ticks[0]; y1 = nt.ticks[nt.ticks.length - 1] < hi ? nt.ticks[nt.ticks.length - 1] + nt.step : nt.ticks[nt.ticks.length - 1];
    }
    this.sc = { m, pw, ph, x0, x1, y0, y1, W, Hh };
    const X = (v) => m.l + (v - x0) / (x1 - x0) * pw, Y = (v) => m.t + (1 - (v - y0) / (y1 - y0)) * ph;
    this.X = X; this.Y = Y;
    const yt = niceTicks(y0, y1, c.yticks || 4), xt = c.xticks ? { ticks: c.xticks, step: c.xticks[1] - c.xticks[0] } : niceTicks(x0, x1, 6);
    let g = `<svg width="${W}" height="${Hh}" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="${esc(c.title || c.ylabel || "chart")}"><defs><clipPath id="cp${this.uid = this.uid || Math.random().toString(36).slice(2)}"><rect x="${m.l}" y="${m.t}" width="${pw}" height="${ph}"/></clipPath></defs>`;
    for (const t of yt.ticks) { if (t < y0 - 1e-9 || t > y1 + 1e-9) continue;
      g += `<line x1="${m.l}" x2="${m.l + pw}" y1="${Y(t)}" y2="${Y(t)}" stroke="${GRIDC}"/><text x="${m.l - 7}" y="${Y(t) + 4}" text-anchor="end" class="tk">${tickLabel(t, yt.step)}</text>`; }
    for (const t of xt.ticks) { if (t < x0 - 1e-9 || t > x1 + 1e-9) continue;
      g += `<text x="${X(t)}" y="${m.t + ph + 16}" text-anchor="middle" class="tk">${tickLabel(t, xt.step)}</text>`; }
    g += `<line x1="${m.l}" x2="${m.l + pw}" y1="${m.t + ph}" y2="${m.t + ph}" stroke="#bbb"/>`;
    g += `<g clip-path="url(#cp${this.uid})">`;
    for (const [a, b] of c.shade || []) g += `<rect x="${X(a)}" y="${m.t}" width="${Math.max(0, X(b) - X(a))}" height="${ph}" fill="${NIGHTC}"/>`;
    for (const s of c.series) {
      let d = "", pen = false;
      for (let i = 0; i < s.x.length; i++) {
        const xv = s.x[i], yv = s.y[i];
        if (!Number.isFinite(yv) || !Number.isFinite(xv)) { pen = false; continue; }
        d += (pen ? "L" : "M") + X(xv).toFixed(1) + "," + Y(yv).toFixed(1); pen = true;
      }
      if (s.fill) g += `<path d="${d}Z" fill="${s.fill}" stroke="none"/>`;
      g += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 2}" ${s.dash ? `stroke-dasharray="${s.dash}"` : ""} stroke-linejoin="round" stroke-linecap="round"/>`;
    }
    for (const p of c.points || []) {
      g += `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="5" fill="${p.color}" stroke="#fff" stroke-width="2"><title>${esc(p.title || p.text || "")}</title></circle>`;
      if (p.text) g += `<text x="${X(p.x) + (p.dx || 8)}" y="${Y(p.y) + (p.dy || -8)}" class="pl">${esc(p.text)}</text>`;
    }
    g += `</g>`;
    if (c.xlabel) g += `<text x="${m.l + pw / 2}" y="${Hh - 6}" text-anchor="middle" class="al">${esc(c.xlabel)}</text>`;
    if (c.ylabel) g += `<text transform="translate(13 ${m.t + ph / 2}) rotate(-90)" text-anchor="middle" class="al">${esc(c.ylabel)}</text>`;
    g += `<line class="xh" x1="0" x2="0" y1="${m.t}" y2="${m.t + ph}" stroke="#444" stroke-dasharray="3 3" style="display:none"/><g class="dots"></g></svg>`;
    this.plot.innerHTML = g; this.plot.append(this.tip);
    this.head.innerHTML = "";
    if (c.title) this.head.append(h("span", { class: "ctitle" }, c.title));
    const lg = h("span", { class: "legend" });
    const named = c.series.filter((s) => s.name && c.legend !== false);
    if (named.length >= 2 || c.legend === true) for (const s of named) lg.append(h("span", { class: "li" },
      h("i", { style: `background:${s.dash ? "transparent" : s.color};border-top:${s.dash ? `2px dashed ${s.color}` : "none"}` }), s.name));
    this.head.append(lg);
    this.svg = this.plot.querySelector("svg");
  }
  cursorAt(xv, tip, px) {
    if (!this.sc) return;
    const c = this.cfg, { m, pw, ph, Hh } = this.sc, s0 = c.series[0];
    let bi = 0, bd = Infinity;
    for (let i = 0; i < s0.x.length; i++) { const d = Math.abs(s0.x[i] - xv); if (d < bd) { bd = d; bi = i; } }
    const xs = this.X(s0.x[bi]);
    const xh = this.svg.querySelector(".xh"); xh.setAttribute("x1", xs); xh.setAttribute("x2", xs); xh.style.display = "";
    let dots = "", rows = "";
    for (const s of c.series) { const v = s.y[bi];
      if (!Number.isFinite(v)) continue;
      dots += `<circle cx="${xs}" cy="${this.Y(v)}" r="4" fill="${s.color}" stroke="#fff" stroke-width="2"/>`;
      if (s.name) rows += `<div><i style="background:${s.color}"></i>${esc(s.name)}: <b>${(c.tipfmt || ((q) => q.toPrecision(4)))(v, s)}</b></div>`; }
    this.svg.querySelector(".dots").innerHTML = dots;
    if (tip) {
      this.tip.innerHTML = `<div class="th">${(c.xfmt || ((q) => q.toFixed(2)))(s0.x[bi])}</div>${rows}`;
      this.tip.style.display = "block";
      const tw = this.tip.offsetWidth, left = xs + 12 + tw > this.sc.W ? xs - 12 - tw : xs + 12;
      this.tip.style.left = Math.max(2, left) + "px"; this.tip.style.top = Math.max(2, Math.min(px - 20, Hh - this.tip.offsetHeight - 2)) + "px";
    }
  }
  onMove(e) {
    if (!this.sc || this.cfg.hover === false) return;
    const r = this.svg.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
    const { m, pw, x0, x1 } = this.sc;
    if (px < m.l || px > m.l + pw) return this.hide();
    const xv = x0 + (px - m.l) / pw * (x1 - x0);
    const peers = this.cfg.group ? groups[this.cfg.group].filter((q) => q.el.isConnected) : [this];
    for (const q of peers) q.cursorAt(xv, q === this, py);
  }
  hide() {
    const peers = this.cfg.group ? groups[this.cfg.group] : [this];
    for (const q of peers) { if (!q.svg) continue; q.svg.querySelector(".xh").style.display = "none"; q.svg.querySelector(".dots").innerHTML = ""; q.tip.style.display = "none"; }
  }
  destroy() { this.ro.disconnect(); if (this.cfg.group) groups[this.cfg.group] = groups[this.cfg.group].filter((q) => q !== this); }
}

/* ---- horizontal bars (entropy generation) ---- */
function barRows(rows, unit, color = BLUE) {
  const mx = Math.max(...rows.map((r) => Math.abs(r[1])), 1e-12);
  return h("div", { class: "bars" }, rows.map(([lab, v]) => h("div", { class: "brow" },
    h("span", { class: "blab" }, lab), h("span", { class: "btrack" }, h("span", { class: "bfill", style: `width:${Math.max(0, v) / mx * 100}%;background:${color}` })),
    h("span", { class: "bval" }, v.toPrecision(3) + " " + unit))));
}

/* ---- waterfall (SVG) ---- */
function waterfall(el, items, ylabel) {
  const W = Math.max(el.clientWidth || 700, 420), Hh = 400, m = { l: 58, r: 14, t: 14, b: 112 }, pw = W - m.l - m.r, ph = Hh - m.t - m.b;
  let cum = 0; const bars = [];
  for (const it of items) {
    if (it.kind === "abs") { bars.push({ a: 0, b: it.v, c: BLUE, lab: it.lab, v: it.v }); cum = it.v; }
    else if (it.kind === "rel") { bars.push({ a: cum, b: cum + it.v, c: it.v >= 0 ? ORANGE : "#9aa3b2", lab: it.lab, v: it.v }); cum += it.v; }
    else bars.push({ a: 0, b: cum, c: BLUE, lab: it.lab, v: cum });
  }
  const lo = Math.min(0, ...bars.map((b) => Math.min(b.a, b.b))), hi = Math.max(...bars.map((b) => Math.max(b.a, b.b)));
  const nt = niceTicks(lo, hi * 1.12, 5), y0 = Math.min(0, nt.ticks[0]); let y1 = nt.ticks[nt.ticks.length - 1]; if (y1 < hi * 1.05) y1 += nt.step;
  const Y = (v) => m.t + (1 - (v - y0) / (y1 - y0)) * ph, bw = pw / bars.length;
  let g = `<svg width="${W}" height="${Hh}" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Energy waterfall">`;
  for (const t of nt.ticks) g += `<line x1="${m.l}" x2="${m.l + pw}" y1="${Y(t)}" y2="${Y(t)}" stroke="${GRIDC}"/><text x="${m.l - 7}" y="${Y(t) + 4}" text-anchor="end" class="tk">${tickLabel(t, nt.step)}</text>`;
  bars.forEach((b, i) => {
    const x = m.l + i * bw + bw * 0.14, w = bw * 0.72, ya = Y(Math.max(b.a, b.b)), yb = Y(Math.min(b.a, b.b));
    g += `<rect x="${x}" y="${ya}" width="${w}" height="${Math.max(1, yb - ya)}" rx="3" fill="${b.c}"><title>${esc(b.lab)}: ${b.v.toFixed(2)}</title></rect>`;
    g += `<text x="${x + w / 2}" y="${ya - 5}" text-anchor="middle" class="bl">${(Math.abs(b.v) < 0.005 ? 0 : b.v).toFixed(2)}</text>`;
    g += `<text transform="translate(${x + w / 2} ${Hh - m.b + 14}) rotate(-35)" text-anchor="end" class="tk">${esc(b.lab)}</text>`;
    if (i < bars.length - 1) g += `<line x1="${x + w}" x2="${x + bw * 1.14 - 0}" y1="${Y(i === bars.length ? 0 : (items[i].kind === "tot" ? b.b : b.b))}" y2="${Y(b.b)}" stroke="#bbb"/>`;
  });
  g += `<text transform="translate(13 ${m.t + ph / 2}) rotate(-90)" text-anchor="middle" class="al">${esc(ylabel)}</text></svg>`;
  el.innerHTML = g;
}
