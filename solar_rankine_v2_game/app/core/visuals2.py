"""
Plotly figures for the v2 Streamlit app: animated plant, T-s diagram with
isentropic references, storage, energy balance by device and day plots.
"""
from __future__ import annotations

import math
from typing import List, Optional

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import properties as fp
from .plant import PlantResult, cycle_at, M_COL, CP_W

BLUE, ORANGE, AQUA, GREY, RED, PURPLE = "#257de0", "#f47230", "#00b894", "#8a8a8a", "#c8332f", "#8e5cd9"
PH = {"liquid": BLUE, "two-phase": PURPLE, "vapor": ORANGE, "superheated": RED, "off": "#c9ced6"}


def phase_of(s) -> str:
    if s.phase == "vapor":
        return "superheated" if s.x is None else "vapor"
    if s.phase == "two-phase":
        return "two-phase"
    return "vapor" if s.x == 1 else s.phase


def phase_text(s) -> str:
    if s.phase == "two-phase":
        return f"two-phase, x = {s.x:.3f}"
    if s.phase == "liquid":
        return "saturated liquid (x = 0)" if s.x == 0 else "compressed liquid"
    return "saturated vapor (x = 1)" if s.x == 1 else "superheated vapor"


def temp_colour(T: float, lo: float = 15.0, hi: float = 98.0) -> str:
    f = max(0.0, min(1.0, (T - lo) / (hi - lo)))
    a, m, b = (56, 132, 214), (246, 196, 70), (214, 48, 49)
    if f < 0.5:
        c = [round(a[i] + 2 * f * (m[i] - a[i])) for i in range(3)]
    else:
        c = [round(m[i] + (2 * f - 1) * (b[i] - m[i])) for i in range(3)]
    return f"rgb({c[0]},{c[1]},{c[2]})"


def clock_str(h: float) -> str:
    h = h % 24.0
    hh, mm = int(h), int(round((h - int(h)) * 60))
    if mm == 60:
        hh, mm = hh + 1, 0
    return f"{hh % 24:02d}:{mm:02d}"


def cycle_at_sample(r: PlantResult, i: int):
    if r.series["frac"][i] <= 0.01:
        return None
    return cycle_at(r.config, float(r.series["Tc"][i]))


def _time_axis(r: PlantResult, H: float):
    step = 6 if H > 24 else 3
    ticks = list(np.arange(0, H + 1e-9, step))
    return dict(tickvals=ticks, ticktext=[clock_str(r.scenario.sunrise + t) for t in ticks], range=[0, H])


def _night_shapes(r: PlantResult, H: float, rows: int):
    t, alt = r.t, r.series["alt"]
    out, a = [], None
    for i in range(len(t)):
        if t[i] > H + 1e-9:
            break
        n = alt[i] <= 0
        if n and a is None:
            a = t[i]
        if (not n or t[i] >= H - 1e-9) and a is not None:
            out.append((a, t[i]))
            a = None
    shapes = []
    for k in range(1, rows + 1):
        for a, b in out:
            shapes.append(dict(type="rect", xref=f"x{'' if k == 1 else k}", yref=f"y{'' if k == 1 else k} domain",
                               x0=a, x1=b, y0=0, y1=1, fillcolor="rgba(60,70,110,0.10)", line_width=0, layer="below"))
    return shapes


# --------------------------------------------------------------------------
# animated plant
# --------------------------------------------------------------------------
def _along(pts, f):
    """Point at fraction f (0..1) along a polyline."""
    seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    L = sum(seg)
    d = (f % 1.0) * L
    for i, s in enumerate(seg):
        if d <= s or i == len(seg) - 1:
            u = d / s if s > 0 else 0
            return pts[i][0] + u * (pts[i + 1][0] - pts[i][0]), pts[i][1] + u * (pts[i + 1][1] - pts[i][1])
        d -= s
    return pts[-1]


def plant_animation(r: PlantResult, hours: float = 24.0, every_min: float = 30.0) -> go.Figure:
    c, sc, S, n = r.config, r.scenario, r.series, r.layers.shape[0]
    W, Hh = 11.0, 6.3
    tH = 1.2 + 0.0008 * c.tank_L
    tW = 0.7 + 0.0003 * c.tank_L
    tX, tY = 3.3 - tW / 2, 0.75
    colL = 0.6 + 0.07 * c.area
    colX, colY = 1.0, 4.45
    eX, eY, eW, eH = 4.7, 2.1, 1.2, 0.9
    tbX, tbY, pX, pY, cX, cY, cW, cH = 8.2, 3.3, 6.6, 1.05, 8.4, 0.8, 1.4, 0.8
    pipes = {
        "col_in": [(tX, tY + 0.15), (colX - 0.1, tY + 0.15), (colX - 0.1, colY - 0.3)],
        "col_out": [(colX + colL * 0.9, colY + 0.3), (colX + colL * 0.9, 5.4), (tX + tW / 2, 5.4), (tX + tW / 2, tY + tH)],
        "ev_in": [(tX + tW, tY + tH - 0.2), (eX, tY + tH - 0.2), (eX, eY + eH - 0.2)],
        "ev_out": [(eX, eY + 0.15), (tX + tW + 0.2, eY + 0.15), (tX + tW + 0.2, tY + 0.15), (tX + tW, tY + 0.15)],
        "r2": [(pX, pY + 0.26), (pX, eY + 0.2), (eX + eW, eY + 0.2)],
        "r3": [(eX + eW, eY + eH - 0.25), (tbX - 0.5, eY + eH - 0.25), (tbX - 0.5, tbY - 0.1)],
        "r4": [(tbX + 0.5, tbY - 0.4), (cX + 0.4, tbY - 0.4), (cX + 0.4, cY + cH)],
        "r1": [(cX, pY), (pX + 0.26, pY)],
    }
    N = len(r.t)
    idx = [i for i in range(N) if r.t[i] <= hours + 1e-9 and abs((r.t[i] * 60) % every_min) < 1e-6]
    names = ["Pump inlet", "Evaporator inlet", "Turbine inlet", "Turbine exit"]
    tag_xy = [(pX + 0.45, 0.25), (pX + 0.2, eY + 0.75), (eX + 0.9, 4.75), (tbX + 0.75, tbY + 0.75)]
    angle = 0.0

    def frame(i, k):
        nonlocal angle
        cyc = cycle_at_sample(r, i)
        run = cyc is not None
        alt, clock = S["alt"][i], S["clock"][i]
        shapes, ann, data = [], [], []
        day = max(0.0, min(1.0, (alt + 6) / 20))
        shapes.append(dict(type="rect", x0=0, x1=W, y0=4.0, y1=Hh, line_width=0, layer="below",
                           fillcolor=f"rgb({int(30 + 190 * day)},{int(40 + 196 * day)},{int(80 + 175 * day)})"))
        # collector: tracking faces the sun, fixed shows the tilt
        frac = (clock - sc.sunrise) / (24 - 2 * sc.sunrise)
        sx, sy = 1.2 + max(-0.1, min(1.1, frac)) * 8.6, 4.2 + max(-2, alt) * 0.022
        tilt = (90 - alt) if (c.tracking and alt > 0) else (c.tilt if not c.tracking else 0.0)
        facing = 1 if (not c.tracking or sx >= colX + colL / 2) else -1
        a = math.radians(tilt)
        cx, cy, hl = colX + colL / 2, colY, colL / 2
        x0, y0 = cx - facing * hl * math.cos(a), cy + hl * math.sin(a)
        x1, y1 = cx + facing * hl * math.cos(a), cy - hl * math.sin(a)
        e = max(0.0, min(1.0, S["Qcol"][i] / max(1.0, 600 * c.area)))
        data.append(go.Scatter(x=[x0, x1], y=[y0, y1], mode="lines", line=dict(color=f"rgba(244,114,48,{0.25 + 0.75 * e:.2f})" if S["G"][i] > 1 else "#9aa3b2", width=12), hoverinfo="skip"))
        data.append(go.Scatter(x=[sx], y=[sy], mode="markers", marker=dict(size=26 if alt > 0 else 10, color="#f2b705" if alt > 0 else "#888"), hoverinfo="skip"))
        # tank layers
        for j in range(n):
            T = r.layers[j, i]
            shapes.append(dict(type="rect", x0=tX, x1=tX + tW, y0=tY + tH * (1 - (j + 1) / n), y1=tY + tH * (1 - j / n), line_width=0, fillcolor=temp_colour(T)))
        shapes.append(dict(type="rect", x0=tX, x1=tX + tW, y0=tY, y1=tY + tH, line=dict(color="#191919", width=1.5)))
        # devices
        shapes += [dict(type="rect", x0=eX, x1=eX + eW, y0=eY, y1=eY + eH, fillcolor="#fff3ea", line=dict(color="#191919", width=1.5)),
                   dict(type="path", path=f"M {tbX-0.5},{tbY+0.25} L {tbX+0.5},{tbY+0.55} L {tbX+0.5},{tbY-0.55} L {tbX-0.5},{tbY-0.25} Z", fillcolor="#eef4fc", line=dict(color="#191919", width=1.5)),
                   dict(type="rect", x0=cX, x1=cX + cW, y0=cY, y1=cY + cH, fillcolor="#e6f7f1", line=dict(color="#191919", width=1.5)),
                   dict(type="circle", x0=pX - 0.26, x1=pX + 0.26, y0=pY - 0.26, y1=pY + 0.26, fillcolor="white", line=dict(color="#191919", width=1.5))]
        # spinning turbine rotor: the angle advances with the turbine power
        angle += (S["Wt"][i] / 40.0) * 37.0 if run else 0.0
        for b in range(6):
            q = math.radians(angle + 60 * b)
            shapes.append(dict(type="line", x0=tbX, y0=tbY, x1=tbX + 0.32 * math.cos(q), y1=tbY + 0.32 * math.sin(q) * 0.95, line=dict(color=BLUE, width=4)))
        for b in range(4):
            q = math.radians(angle * 1.7 + 90 * b)
            shapes.append(dict(type="line", x0=pX, y0=pY, x1=pX + 0.2 * math.cos(q), y1=pY + 0.2 * math.sin(q), line=dict(color=BLUE, width=3)))
        # pipes: water by temperature, refrigerant by phase; width follows mass flow
        mf = S["mdot"][i] * 1000
        wref = 3 + min(9, mf / 2.2)
        col = {"col_in": temp_colour(r.layers[-1, i]) if S["Qcol"][i] > 1 else PH["off"],
               "col_out": temp_colour(min(99, r.layers[-1, i] + S["Qcol"][i] / (M_COL * c.area * CP_W))) if S["Qcol"][i] > 1 else PH["off"],
               "ev_in": temp_colour(r.layers[0, i]) if run else PH["off"], "ev_out": temp_colour(c.Te + 5) if run else PH["off"]}
        if run:
            col.update(r2=PH[phase_of(cyc.s2)], r3=PH[phase_of(cyc.s3)], r4=PH[phase_of(cyc.s4)], r1=PH[phase_of(cyc.s1)])
        else:
            col.update(r2=PH["off"], r3=PH["off"], r4=PH["off"], r1=PH["off"])
        for name, pts in pipes.items():
            refr = name.startswith("r")
            data.append(go.Scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], mode="lines",
                                   line=dict(color=col[name], width=wref if refr else 5), hoverinfo="skip"))
        # moving flow dots
        for name, pts in pipes.items():
            moving = (S["Qcol"][i] > 1) if name.startswith("col") else run
            xs, ys = [], []
            if moving:
                sp = 0.13 if not name.startswith("r") else 0.05 + mf / 120
                for q in range(5):
                    x, y = _along(pts, q / 5 + k * sp)
                    xs.append(x); ys.append(y)
            data.append(go.Scatter(x=xs or [None], y=ys or [None], mode="markers", marker=dict(size=7, color="white", line=dict(color="#333", width=1)), hoverinfo="skip"))
        # labels
        ann.append(dict(x=tX + tW / 2, y=tY - 0.25, text=f"Tank {c.tank_L:.0f} L ({'stratified' if n > 1 else 'uniform'}): {S['E_tank_kWh'][i]:+.2f} kWh stored", showarrow=False, font=dict(size=11)))
        ann.append(dict(x=tX + tW / 2, y=tY + tH - 0.15, text=f"<b>{r.layers[0, i]:.1f} C</b>", showarrow=False, font=dict(color="white", size=12)))
        if n > 1:
            ann.append(dict(x=tX + tW / 2, y=tY + 0.15, text=f"<b>{r.layers[-1, i]:.1f} C</b>", showarrow=False, font=dict(color="white", size=12)))
        ann.append(dict(x=0.1, y=6.1, xanchor="left", text=f"Collector {c.area:g} m^2: {S['Qcol'][i]/1000:.2f} kW" + (" (tracking)" if c.tracking else f", tilt {c.tilt:.0f} deg"), showarrow=False, bgcolor="rgba(255,255,255,0.85)", font=dict(size=12)))
        ann.append(dict(x=W - 0.1, y=6.1, xanchor="right", text=f"{clock_str(clock)} solar time ({r.t[i]:.1f} h after sunrise)", showarrow=False, bgcolor="rgba(16,35,63,0.8)", font=dict(color="white", size=12)))
        ann += [dict(x=eX + eW / 2, y=eY + eH + 0.15, text="<b>Evaporator</b>", showarrow=False),
                dict(x=tbX, y=tbY + 0.75, text="<b>Turbine</b>", showarrow=False),
                dict(x=cX + cW / 2, y=cY + cH + 0.15, text="<b>Condenser</b>", showarrow=False),
                dict(x=pX, y=pY - 0.45, text=f"<b>Pump</b> {S['Wp'][i]:.0f} W, {mf:.1f} g/s" if run else "<b>Pump</b> off", showarrow=False, font=dict(size=11)),
                dict(x=tbX, y=tbY - 0.8, text=f"<b>W_net {S['Wnet'][i]:.0f} W</b>" if run else "", showarrow=False, font=dict(color="#0b8f6e", size=14)),
                dict(x=cX + cW / 2, y=cY + cH / 2, text=(f"{S['Qc'][i]/1000:.2f} kW to air<br>air {S['Ta'][i]:.1f} C" if run else f"air {S['Ta'][i]:.1f} C"), showarrow=False, font=dict(size=10))]
        states = [cyc.s1, cyc.s2, cyc.s3, cyc.s4] if run else [None] * 4
        for j, s in enumerate(states):
            x, y = tag_xy[j]
            txt = (f"<b>{j+1} {names[j]}</b><br>T {s.T:.1f} C  P {s.P:.0f} kPa<br>h {s.h:.1f} kJ/kg  s {s.s:.4f}<br>{phase_text(s)}"
                   if s else f"<b>{j+1} {names[j]}</b><br>idle")
            ann.append(dict(x=x, y=y, text=txt, showarrow=False, align="left", xanchor="left", font=dict(size=10), bgcolor="rgba(255,255,255,0.92)", bordercolor="#cfd6de"))
        if not run:
            ann.append(dict(x=7.4, y=2.3, text=("Idle: tank below the start temperature" if c.pump_on else "Pump off"), showarrow=False, font=dict(color=RED, size=13)))
        return data, shapes, ann

    frames = []
    for k, i in enumerate(idx):
        d, s_, a_ = frame(i, k)
        frames.append(go.Frame(data=d, layout=dict(shapes=s_, annotations=a_), name=f"{r.t[i]:.2f}"))
    k0 = max(range(len(idx)), key=lambda q: S["Wnet"][idx[q]])
    angle = 0.0
    d0, s0, a0 = frame(idx[k0], k0)
    fig = go.Figure(data=d0, frames=frames)
    steps = [dict(method="animate", label=clock_str(sc.sunrise + r.t[i]), args=[[f"{r.t[i]:.2f}"], dict(mode="immediate", frame=dict(duration=0, redraw=True), transition=dict(duration=0))]) for i in idx]
    fig.update_layout(
        shapes=s0, annotations=a0, height=560, showlegend=False, margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(range=[0, W], visible=False, fixedrange=True), yaxis=dict(range=[-0.2, Hh], visible=False, scaleanchor="x", fixedrange=True),
        plot_bgcolor="#f7f8fa", paper_bgcolor="white",
        updatemenus=[dict(type="buttons", x=0.0, y=-0.02, xanchor="left", yanchor="top", direction="left",
                          buttons=[dict(label="Play", method="animate", args=[None, dict(frame=dict(duration=180, redraw=True), fromcurrent=True, transition=dict(duration=0))]),
                                   dict(label="Pause", method="animate", args=[[None], dict(mode="immediate", frame=dict(duration=0, redraw=False))])])],
        sliders=[dict(active=k0, steps=steps, x=0.12, len=0.88, y=-0.02, yanchor="top", currentvalue=dict(prefix="Solar time "))])
    return fig


# --------------------------------------------------------------------------
# T-s diagram with isentropic references
# --------------------------------------------------------------------------
def _dome(tmin=0.0):
    T, sf, sg = fp.saturation_dome(tmin, fp.T_CRIT_C - 0.3, 60)
    return list(sf) + list(sg[::-1]), list(T) + list(T[::-1])


def cycle_path(c, n=14):
    S, T = [c.s1.s, c.s2.s], [c.s1.T, c.s2.T]
    for i in range(n + 1):
        t = c.s2.T + (c.Te - 0.02 - c.s2.T) * i / n
        S.append(fp.sat_state(t, 0).s + (c.s2.s - fp.sat_state(c.s2.T, 0).s) * (1 - i / n)); T.append(t)
    S += [fp.sat_state(c.Te, 0).s, fp.sat_state(c.Te, 1).s]; T += [c.Te, c.Te]
    if c.superheat > 0:
        for i in range(1, 7):
            d = c.superheat * i / 6
            S.append(fp.state_PT(c.Pe, c.Te + d).s); T.append(c.Te + d)
    S += [c.s3.s, c.s4.s]; T += [c.s3.T, c.s4.T]
    if c.s4.x is None:
        for i in range(1, 7):
            d = (c.s4.T - c.Tc) * (1 - i / 6)
            S.append(fp.state_PT(c.Pc, c.Tc + d + 1e-3).s if d > 0.01 else fp.sat_state(c.Tc, 1).s); T.append(c.Tc + d)
    S.append(c.s1.s); T.append(c.Tc)
    return S, T


def ts_figure(cycles: List, labels: List[str], height: int = 430, compact: bool = False) -> go.Figure:
    tmin = min([0.0] + [c.Tc - 3 for c in cycles])
    fig = go.Figure()
    x, y = _dome(tmin)
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="Saturation dome", line=dict(color=GREY, width=1.5)))
    cols = [BLUE, ORANGE, AQUA, PURPLE]
    for k, (c, lab) in enumerate(zip(cycles, labels)):
        col = cols[k % 4]
        S, T = cycle_path(c)
        fig.add_trace(go.Scatter(x=S, y=T, mode="lines", name=lab, line=dict(color=col, width=2.5)))
        fig.add_trace(go.Scatter(x=[c.s3.s, c.s3.s], y=[c.s3.T, c.Tc], mode="lines", name="Isentropic (ideal)" if k == 0 else None,
                                 showlegend=k == 0, line=dict(color=col, width=1.2, dash="dash")))
        fig.add_trace(go.Scatter(x=[c.s1.s, c.s1.s], y=[c.s1.T, c.s1.T + 0.6 * (c.s2.T - c.s1.T)], mode="lines", showlegend=False, line=dict(color=col, width=1.2, dash="dash")))
        pts = [c.s1, c.s2, c.s3, c.s4]
        fig.add_trace(go.Scatter(x=[p.s for p in pts], y=[p.T for p in pts], mode="markers+text", text=["1", "2", "3", "4"], textposition="top right",
                                 marker=dict(size=9, color=col), showlegend=False,
                                 hovertext=[f"State {j+1}: T {p.T:.1f} C, P {p.P:.0f} kPa, h {p.h:.1f}, s {p.s:.4f}, {phase_text(p)}" for j, p in enumerate(pts)], hoverinfo="text"))
        if not compact:
            fig.add_annotation(x=c.s3.s, y=c.Tc, text="4s", showarrow=False, xshift=-14, yshift=-10)
    fig.update_layout(height=height, xaxis_title="Entropy s [kJ/kg-K]", yaxis_title="Temperature [C]", margin=dict(l=50, r=10, t=10, b=40),
                      xaxis=dict(range=[0.15, 1.0]), yaxis=dict(range=[min(0, math.floor((tmin - 4) / 20) * 20), 108]), legend=dict(orientation="h", y=1.08))
    return fig


# --------------------------------------------------------------------------
# day plots, storage, energy balance
# --------------------------------------------------------------------------
def _cut(r, H):
    n = int(np.searchsorted(r.t, H + 1e-9))
    return n


def day_plots(r: PlantResult, H: float = 24.0) -> go.Figure:
    S, n = r.series, _cut(r, H)
    t = r.t[:n]
    fig = make_subplots(rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        subplot_titles=["Beam irradiance on the aperture [W/m^2]", "Temperatures [C]", "Heat rates [kW]", "Power [W]", "Refrigerant mass flow [g/s]"])
    add = lambda y, name, col, row, dash=None: fig.add_trace(go.Scatter(x=t, y=y[:n], name=name, line=dict(color=col, dash=dash), legendgroup=str(row)), row=row, col=1)
    add(S["G"], "Beam on aperture", BLUE, 1)
    if r.layers.shape[0] > 1:
        add(S["T_top"], "Tank top", RED, 2); add(S["T_bot"], "Tank bottom", BLUE, 2)
    else:
        add(S["T_top"], "Tank", RED, 2)
    add(S["Tc"], "Condenser", AQUA, 2); add(S["Ta"], "Ambient", GREY, 2, "dot")
    add(S["Qcol"] / 1e3, "Collector", ORANGE, 3); add(S["Qev"] / 1e3, "To evaporator", BLUE, 3); add(S["Qloss"] / 1e3, "Tank loss", GREY, 3)
    add(S["Wt"], "Turbine", BLUE, 4); add(S["Wp"], "Pump", ORANGE, 4); add(S["Wnet"], "Net", AQUA, 4)
    add(S["mdot"] * 1e3, "Mass flow", BLUE, 5)
    ax = _time_axis(r, H)
    for k in range(1, 6):
        fig.update_xaxes(tickvals=ax["tickvals"], ticktext=ax["ticktext"], range=ax["range"], row=k, col=1)
    fig.update_layout(height=900, margin=dict(l=50, r=10, t=40, b=40), shapes=_night_shapes(r, H, 5), hovermode="x unified")
    return fig


def storage_figure(r: PlantResult, H: float = 24.0) -> go.Figure:
    S, n = r.series, _cut(r, H)
    t = r.t[:n]
    q = S["Q_store"][:n]
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        subplot_titles=["Charge (+) / discharge (-) rate of the tank [W]", "Energy stored in the tank since sunrise [kWh]",
                                        "Tank layer temperatures [C]" if r.layers.shape[0] > 1 else "Tank temperature [C]"])
    fig.add_trace(go.Scatter(x=t, y=np.maximum(q, 0), name="Charging", fill="tozeroy", line=dict(color=ORANGE)), row=1, col=1)
    fig.add_trace(go.Scatter(x=t, y=np.minimum(q, 0), name="Discharging", fill="tozeroy", line=dict(color=BLUE)), row=1, col=1)
    fig.add_trace(go.Scatter(x=t, y=S["E_tank_kWh"][:n], name="Stored energy", line=dict(color=AQUA)), row=2, col=1)
    nl = r.layers.shape[0]
    for j in range(nl):
        fig.add_trace(go.Scatter(x=t, y=r.layers[j, :n], name=("Top layer" if j == 0 else "Bottom layer" if j == nl - 1 else f"Layer {j+1}") if nl > 1 else "Tank",
                                 line=dict(color=temp_colour(95 - j * 70 / max(1, nl - 1)), width=2.2 if j in (0, nl - 1) else 1),
                                 showlegend=j in (0, nl - 1)), row=3, col=1)
    fig.add_trace(go.Scatter(x=t, y=[r.config.T_start] * n, name="Start temperature", line=dict(color=GREY, dash="dash", width=1)), row=3, col=1)
    ax = _time_axis(r, H)
    for k in range(1, 4):
        fig.update_xaxes(tickvals=ax["tickvals"], ticktext=ax["ticktext"], range=ax["range"], row=k, col=1)
    fig.update_layout(height=700, margin=dict(l=50, r=10, t=40, b=40), shapes=_night_shapes(r, H, 3), hovermode="x unified")
    return fig


def energy_by_device(r: PlantResult) -> go.Figure:
    k = r.kpi
    rows = [("Collector", k["E_collector_Wh"], 0.0), ("Storage tank", 0.0, k["E_loss_Wh"]), ("Evaporator", k["E_evaporator_Wh"], 0.0),
            ("Pump", k["W_pump_Wh"], 0.0), ("Turbine", 0.0, k["W_turbine_Wh"]), ("Condenser", 0.0, k["Q_condenser_Wh"])]
    names = [x[0] for x in rows][::-1]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=names, x=[-x[1] / 1000 for x in rows][::-1], orientation="h", name="Energy in", marker_color=ORANGE,
                         text=[f"{x[1]/1000:.2f}" if x[1] else "" for x in rows][::-1], textposition="outside"))
    fig.add_trace(go.Bar(y=names, x=[x[2] / 1000 for x in rows][::-1], orientation="h", name="Energy out", marker_color=BLUE,
                         text=[f"{x[2]/1000:.2f}" if x[2] else "" for x in rows][::-1], textposition="outside"))
    fig.update_layout(barmode="relative", height=330, margin=dict(l=10, r=10, t=10, b=40), xaxis_title="Energy over the day [kWh]  (in to the left, out to the right)",
                      legend=dict(orientation="h", y=1.1))
    return fig


def waterfall(r: PlantResult) -> go.Figure:
    k = r.kpi
    kwh = lambda v: v / 1000.0
    labels = ["Beam on aperture", "Collector losses", "Collector heat", "Tank losses", "Stored in tank", "Heat to evaporator",
              "Pump work in", "Heat rejected", "Turbine work", "Pump work", "Net work"]
    vals = [kwh(k["E_incident_Wh"]), -kwh(k["E_incident_Wh"] - k["E_collector_Wh"]), 0, -kwh(k["E_loss_Wh"]), -kwh(k["dU_tank_Wh"]), 0,
            kwh(k["W_pump_Wh"]), -kwh(k["Q_condenser_Wh"]), 0, -kwh(k["W_pump_Wh"]), 0]
    meas = ["absolute", "relative", "total", "relative", "relative", "total", "relative", "relative", "total", "relative", "total"]
    fig = go.Figure(go.Waterfall(x=labels, y=vals, measure=meas, textposition="outside", texttemplate="%{y:.2f}",
                                 increasing=dict(marker_color=ORANGE), decreasing=dict(marker_color="#9aa3b2"), totals=dict(marker_color=BLUE)))
    fig.update_layout(height=380, margin=dict(l=40, r=10, t=10, b=90), yaxis_title="Energy over the day [kWh]", showlegend=False)
    return fig
