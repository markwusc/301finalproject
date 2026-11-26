"""
Plotly figures for the interface: animated plant diagram with T-s panel,
24 h time series, T-s diagram, energy waterfall and case-comparison plots.

No thermodynamics lives here: every number comes from core.simulation,
core.cycle or core.properties.

Colour: categorical slots follow a fixed order (blue, orange, aqua, yellow),
one axis per plot (small multiples rather than dual axes), thin marks.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import cycle as cy
from . import properties as fp
from .simulation import SimResult, instant

# fixed categorical order
BLUE, ORANGE, AQUA, YELLOW = "#257de0", "#f47230", "#00b894", "#f2a600"
INK, INK2, GRID = "#191919", "#666666", "#e6e6e6"
NIGHT = "rgba(60,70,110,0.10)"
FONT = dict(family="Inter, Segoe UI, Arial", size=12, color=INK)


def _layout(fig, height=420, title=None):
    fig.update_layout(template="plotly_white", font=FONT, height=height, title=title,
                      margin=dict(l=55, r=20, t=50 if title else 25, b=45),
                      legend=dict(orientation="h", y=1.08, x=0))
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


# ---------------------------------------------------------------------------
# T-s diagram
# ---------------------------------------------------------------------------
def cycle_path(c: cy.CycleResult, n: int = 14):
    """(s, T) polyline tracing the cycle on T-s axes, plus the four state markers."""
    S, T = [c.s1.s], [c.s1.T]
    S.append(c.s2.s); T.append(c.s2.T)                              # 1-2 pump
    for t in np.linspace(c.s2.T, c.Te - 0.02, n):                   # 2-sat liquid along the isobar
        st = fp.state_PT(c.Pe, float(t)); S.append(st.s); T.append(st.T)
    S.append(fp.sat_state(c.Te, 0).s); T.append(c.Te)
    S.append(fp.sat_state(c.Te, 1).s); T.append(c.Te)               # boiling
    if c.superheat > 0:                                             # superheating
        for t in np.linspace(c.Te + 0.02, c.s3.T, 6):
            st = fp.state_PT(c.Pe, float(t)); S.append(st.s); T.append(st.T)
    S.append(c.s3.s); T.append(c.s3.T)
    S.append(c.s4.s); T.append(c.s4.T)                              # 3-4 turbine
    if c.s4.x is None:                                              # de-superheat along the isobar
        for t in np.linspace(c.s4.T, c.Tc + 0.02, 6):
            st = fp.state_PT(c.Pc, float(t)); S.append(st.s); T.append(st.T)
        S.append(fp.sat_state(c.Tc, 1).s); T.append(c.Tc)
    S.append(c.s1.s); T.append(c.Tc)                                # condensation to state 1
    marks = ([c.s1.s, c.s2.s, c.s3.s, c.s4.s], [c.s1.T, c.s2.T, c.s3.T, c.s4.T])
    return S, T, marks


def ts_figure(cycles: Sequence[cy.CycleResult], labels: Sequence[str], height=430) -> go.Figure:
    T, sf, sg = fp.saturation_dome(0, fp.T_CRIT_C - 0.3, 60)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=np.r_[sf, sg[::-1]], y=np.r_[T, T[::-1]], mode="lines",
                             line=dict(color="#8a8a8a", width=1.5), name="Saturation dome",
                             hoverinfo="skip"))
    for c, lab, col in zip(cycles, labels, (BLUE, ORANGE, AQUA)):
        S, Tt, (ms, mt) = cycle_path(c)
        fig.add_trace(go.Scatter(x=S, y=Tt, mode="lines", line=dict(color=col, width=2.5), name=lab,
                                 hovertemplate="s=%{x:.3f} kJ/kg-K<br>T=%{y:.1f} C<extra></extra>"))
        fig.add_trace(go.Scatter(x=ms, y=mt, mode="markers+text", text=["1", "2", "3", "4"],
                                 textposition=["bottom left", "bottom right", "top right", "bottom right"],
                                 marker=dict(color=col, size=9, line=dict(color="white", width=2)),
                                 showlegend=False, textfont=dict(color=INK, size=13),
                                 hovertemplate="state %{text}<br>s=%{x:.3f}<br>T=%{y:.1f} C<extra></extra>"))
    fig.update_xaxes(title="Entropy s [kJ/kg-K]", range=[0.15, 1.0])
    fig.update_yaxes(title="Temperature [C]", range=[0, 108])
    return _layout(fig, height)


# ---------------------------------------------------------------------------
# 24 h time series (small multiples, one axis each)
# ---------------------------------------------------------------------------
def timeseries_figure(r: SimResult, height=860) -> go.Figure:
    S, t = r.series, r.t
    fig = make_subplots(rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.045,
                        subplot_titles=("Beam irradiance on the collector [W/m^2]",
                                        "Temperatures [C]", "Heat rates [kW]",
                                        "Power [W]", "Working-fluid mass flow [g/s]"))
    line = lambda y, name, col, row, dash=None, show=True: fig.add_trace(
        go.Scatter(x=t, y=y, mode="lines", name=name, line=dict(color=col, width=2, dash=dash),
                   showlegend=show, legend="legend" if row == 1 else f"legend{row}",
                   hovertemplate=name + ": %{y:.2f}<extra></extra>"), row=row, col=1)
    line(S["g_eff"], "Beam on aperture", BLUE, 1, show=False)
    line(S["Ts"], "Tank", BLUE, 2); line(S["Te"], "Evaporator", ORANGE, 2)
    line(S["Tc"], "Condenser", AQUA, 2); line(S["Ta"], "Ambient", "#8a8a8a", 2, dash="dot")
    line(S["Qcol"] / 1e3, "Collector", BLUE, 3); line(S["Qev"] / 1e3, "To evaporator", ORANGE, 3)
    line(S["Qloss"] / 1e3, "Tank loss", AQUA, 3)
    line(S["Wt"], "Turbine", BLUE, 4); line(S["Wp"], "Pump", ORANGE, 4); line(S["Wnet"], "Net", AQUA, 4)
    line(S["mdot"] * 1e3, "Mass flow", BLUE, 5, show=False)
    # night shading
    night = S["alt"] <= 0
    edges = np.flatnonzero(np.diff(night.astype(int)) != 0) + 1
    segs = np.split(np.arange(t.size), edges)
    for seg in segs:
        if night[seg[0]]:
            for row in range(1, 6):
                fig.add_vrect(x0=t[seg[0]], x1=t[seg[-1]], fillcolor=NIGHT, line_width=0, row=row, col=1)
    fig.update_xaxes(title_text="Solar time [h]", row=5, col=1, range=[0, 24], dtick=3)
    fig.update_xaxes(range=[0, 24], dtick=3)
    fig.update_annotations(font=dict(size=12, color=INK2), x=0, xanchor="left")
    _layout(fig, height)
    # one legend per panel so identical colours in different panels are never ambiguous
    for row in (2, 3, 4):
        ax = fig.layout["yaxis" if row == 1 else f"yaxis{row}"]
        fig.update_layout(**{f"legend{row}": dict(orientation="h", x=1.0, xanchor="right",
                                                  y=ax.domain[1] + 0.005, yanchor="bottom",
                                                  bgcolor="rgba(255,255,255,0)")})
    return fig


# ---------------------------------------------------------------------------
# energy balance waterfall
# ---------------------------------------------------------------------------
def energy_waterfall(r: SimResult, height=420) -> go.Figure:
    k, b = r.kpi, r.balance
    kwh = lambda v: v / 1000.0
    labels = ["Beam on aperture", "Collector losses", "Collector heat", "Tank losses",
              "Stored in tank", "Heat to evaporator", "Pump work", "Heat rejected", "Turbine work",
              "Pump work", "Net work"]
    measure = ["absolute", "relative", "total", "relative", "relative", "total",
               "relative", "relative", "total", "relative", "total"]
    y = [kwh(k["E_incident_Wh"]), -kwh(k["E_incident_Wh"] - k["E_collector_Wh"]), 0,
         -kwh(k["E_loss_Wh"]), -kwh(b["dU_tank_Wh"]), 0,
         kwh(k["W_pump_Wh"]), -kwh(k["Q_condenser_Wh"]), 0, -kwh(k["W_pump_Wh"]), 0]
    fig = go.Figure(go.Waterfall(x=labels, y=y, measure=measure,
                                 increasing=dict(marker=dict(color=ORANGE)),
                                 decreasing=dict(marker=dict(color="#9aa3b2")),
                                 totals=dict(marker=dict(color=BLUE)),
                                 connector=dict(line=dict(color="#bbbbbb", width=1)),
                                 hovertemplate="%{x}: %{y:.2f} kWh<extra></extra>"))
    fig.update_yaxes(title="Energy over the day [kWh]")
    fig.update_xaxes(tickangle=-30)
    return _layout(fig, height)


# ---------------------------------------------------------------------------
# comparison of two simulations
# ---------------------------------------------------------------------------
def comparison_figure(a: SimResult, b: SimResult, la="Case A", lb="Case B", height=620) -> go.Figure:
    fig = make_subplots(rows=2, cols=2, shared_xaxes=True, vertical_spacing=0.13, horizontal_spacing=0.09,
                        subplot_titles=("Tank temperature [C]", "Evaporator (solid) and condenser (dashed) pressure [kPa]",
                                        "Working-fluid mass flow [g/s]", "Net power [W]"))
    for res, name, col in ((a, la, BLUE), (b, lb, ORANGE)):
        S, t = res.series, res.t
        add = lambda y, r_, c_, dash=None, show=False: fig.add_trace(
            go.Scatter(x=t, y=y, mode="lines", name=name, line=dict(color=col, width=2, dash=dash),
                       showlegend=show, legendgroup=name), row=r_, col=c_)
        add(S["Ts"], 1, 1, show=True)
        add(S["Pe"], 1, 2); add(S["Pc"], 1, 2, dash="dash")
        add(S["mdot"] * 1e3, 2, 1); add(S["Wnet"], 2, 2)
    fig.update_xaxes(range=[0, 24], dtick=4)
    fig.update_xaxes(title_text="Solar time [h]", row=2)
    fig.update_annotations(font=dict(size=12, color=INK2))
    return _layout(fig, height)


# ---------------------------------------------------------------------------
# animated plant diagram + live T-s panel
# ---------------------------------------------------------------------------
def _heat_colour(T: float, lo=20.0, hi=98.0) -> str:
    """Tank colour: blue at lo, red at hi (a physical temperature scale, not identity)."""
    f = max(0.0, min(1.0, (T - lo) / (hi - lo)))
    a, b = (37, 125, 224), (220, 60, 61)
    return "rgb(%d,%d,%d)" % tuple(round(a[i] + f * (b[i] - a[i])) for i in range(3))


def _box(x0, x1, y0, y1):
    return [x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0]


def _frame_traces(r: SimResult, k: int, qmax: float):
    """Dynamic traces for time index k. Order must match the figure's dynamic trace list."""
    p, S = r.params, r.series
    Ts, Qcol, frac = S["Ts"][k], S["Qcol"][k], S["frac"][k]
    hour = r.t[k]
    alt = S["alt"][k]
    off = "#c9c9c9"
    run = frac > 0.01
    liq = BLUE if run else off
    vap = ORANGE if run else off
    w = 2 + 9 * frac
    # sun
    sx = 0.5 + 4.3 * (hour - 5.0) / 14.0
    sy = 7.0 + 0.6 * math.sin(math.radians(max(alt, 0.0)))
    sun = go.Scatter(x=[sx], y=[sy], mode="markers", marker=dict(size=26 if alt > 0 else 12,
                     color=YELLOW if alt > 0 else "#8a8a8a", line=dict(color="white", width=2)),
                     hoverinfo="skip", showlegend=False)
    # collector colour by useful heat
    e = max(0.0, min(1.0, Qcol / qmax)) if qmax > 0 else 0.0
    col_fill = "rgba(244,114,48,%.2f)" % (0.10 + 0.8 * e)
    cx, cyy = [0.4, 2.8, 2.8, 0.4, 0.4], [4.9, 6.1, 6.6, 5.4, 4.9]
    coll = go.Scatter(x=cx, y=cyy, mode="lines", fill="toself", fillcolor=col_fill,
                      line=dict(color=INK, width=1.5), hoverinfo="skip", showlegend=False)
    tx, ty = _box(3.4, 5.0, 2.2, 5.2)
    tank = go.Scatter(x=tx, y=ty, mode="lines", fill="toself", fillcolor=_heat_colour(Ts),
                      line=dict(color=INK, width=1.5), hoverinfo="skip", showlegend=False)
    pipes = [
        go.Scatter(x=[2.8, 4.2, 4.2], y=[5.7, 5.7, 5.2], mode="lines",
                   line=dict(color=ORANGE if Qcol > 1 else off, width=2 + 7 * min(1.0, Qcol / qmax if qmax else 0)),
                   hoverinfo="skip", showlegend=False),
        go.Scatter(x=[5.0, 6.0], y=[3.7, 3.7], mode="lines", line=dict(color=ORANGE if run else off, width=w),
                   hoverinfo="skip", showlegend=False),
        go.Scatter(x=[6.7, 6.7, 9.4, 9.4], y=[4.4, 6.0, 6.0, 5.1], mode="lines", line=dict(color=vap, width=w),
                   hoverinfo="skip", showlegend=False),
        go.Scatter(x=[9.4, 9.4], y=[2.9, 1.8], mode="lines", line=dict(color=vap, width=w),
                   hoverinfo="skip", showlegend=False),
        go.Scatter(x=[8.6, 7.0], y=[1.2, 1.2], mode="lines", line=dict(color=liq, width=w),
                   hoverinfo="skip", showlegend=False),
        go.Scatter(x=[6.4, 6.7, 6.7], y=[1.2, 1.2, 3.0], mode="lines", line=dict(color=liq, width=w),
                   hoverinfo="skip", showlegend=False),
    ]
    txt_x = [4.2, 6.7, 7.7, 9.4, 2.3, 6.7, 6.2, 9.0, 9.7, 6.7]
    txt_y = [1.75, 2.45, 6.45, 0.1, 8.2, 0.55, 3.15, 5.5, 6.95, 1.8]
    Wnet, Qev, Qc = S["Wnet"][k], S["Qev"][k], S["Qc"][k]
    txt = [f"<b>Tank {Ts:.1f} C</b>",
           f"Evaporator {S['Te'][k]:.1f} C<br>{Qev/1e3:.2f} kW in" if run else "Evaporator idle",
           "" if not run else f"{S['Pe'][k]:.0f} kPa", f"Condenser {S['Tc'][k]:.1f} C<br>{Qc/1e3:.2f} kW out" if run else "Condenser idle",
           f"Sun {alt:.0f} deg, beam {S['g_eff'][k]:.0f} W/m^2<br>collector {Qcol/1e3:.2f} kW",
           f"Pump {S['Wp'][k]:.0f} W" if run else "Pump off",
           "", "", f"<b>W_net {Wnet:.0f} W</b>" if run else "Plant idle", ""]
    labels = go.Scatter(x=txt_x, y=txt_y, mode="text", text=txt, textfont=dict(size=12, color=INK),
                        hoverinfo="skip", showlegend=False)
    # T-s panel
    if run:
        c = cy.solve_cycle(S["Te"][k], S["Tc"][k], p.superheat, p.eta_t, p.eta_p, p.valve_open)
        Sx, Ty, (ms, mt) = cycle_path(c, n=8)
    else:
        Sx, Ty, ms, mt = [], [], [], []
    ts_line = go.Scatter(x=Sx, y=Ty, mode="lines", line=dict(color=BLUE, width=2.5), showlegend=False,
                         hoverinfo="skip")
    ts_pts = go.Scatter(x=ms, y=mt, mode="markers+text", text=["1", "2", "3", "4"] if run else [],
                        textposition="top right", marker=dict(color=BLUE, size=8, line=dict(color="white", width=2)),
                        textfont=dict(size=12), showlegend=False, hoverinfo="skip")
    return [sun, coll, tank, *pipes, labels, ts_line, ts_pts]


def plant_animation(r: SimResult, step: int = 4, height=520) -> go.Figure:
    """Schematic of the plant with a play/pause slider over the 24 h simulation."""
    S = r.series
    qmax = float(max(S["Qcol"].max(), 1.0))
    idx = list(range(0, r.t.size, step))
    if idx[-1] != r.t.size - 1:
        idx.append(r.t.size - 1)
    k0 = int(np.argmax(S["Wnet"])) if S["Wnet"].max() > 0 else r.t.size // 2

    fig = make_subplots(rows=1, cols=2, column_widths=[0.62, 0.38], horizontal_spacing=0.04,
                        subplot_titles=("Plant (flow width follows mass flow)", "Cycle on T-s axes"))
    # static equipment outlines
    for (x, y, name, fill) in [
        (*_box(6.0, 7.4, 3.0, 4.4), "Evaporator", "rgba(244,114,48,0.12)"),
        ([8.6, 10.2, 10.2, 8.6, 8.6], [3.6, 2.8, 5.2, 4.4, 3.6], "Turbine", "rgba(37,125,224,0.12)"),
        (*_box(8.6, 10.2, 0.6, 1.8), "Condenser", "rgba(0,184,148,0.14)")]:
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines", fill="toself", fillcolor=fill,
                                 line=dict(color=INK, width=1.5), hoverinfo="skip", showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=[6.7], y=[1.2], mode="markers", marker=dict(size=30, color="white",
                             line=dict(color=INK, width=1.5)), hoverinfo="skip", showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=[3.4, 6.7, 9.4, 6.7, 4.2], y=[5.55, 3.7, 4.0, 1.2, 6.15], mode="text",
                             text=["", "", "Turbine", "P", ""], textfont=dict(size=12, color=INK),
                             hoverinfo="skip", showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=[1.6], y=[4.55], mode="text",
                             text=["Collector"], textfont=dict(size=11, color=INK2),
                             hoverinfo="skip", showlegend=False), row=1, col=1)
    n_static = len(fig.data)
    # dome on the T-s panel (static)
    Td, sf, sg = fp.saturation_dome(0, fp.T_CRIT_C - 0.3, 50)
    fig.add_trace(go.Scatter(x=np.r_[sf, sg[::-1]], y=np.r_[Td, Td[::-1]], mode="lines",
                             line=dict(color="#8a8a8a", width=1.3), hoverinfo="skip", showlegend=False), row=1, col=2)
    n_static = len(fig.data)

    dyn_first = _frame_traces(r, k0, qmax)
    # dynamic traces: first 10 live on the schematic axes, last 2 on the T-s axes
    for i, tr in enumerate(dyn_first):
        fig.add_trace(tr, row=1, col=1 if i < len(dyn_first) - 2 else 2)
    dyn_idx = list(range(n_static, n_static + len(dyn_first)))

    frames = []
    for k in idx:
        tr = _frame_traces(r, k, qmax)
        frames.append(go.Frame(data=tr, traces=dyn_idx, name=f"{r.t[k]:.2f}"))
    fig.frames = frames

    steps = [dict(method="animate", label=(f"{r.t[k]:.0f}" if abs(r.t[k] / 3 - round(r.t[k] / 3)) < 0.02 else ""),
                  args=[[f"{r.t[k]:.2f}"], dict(mode="immediate", frame=dict(duration=0, redraw=True),
                                                transition=dict(duration=0))]) for k in idx]
    fig.update_layout(
        updatemenus=[dict(type="buttons", direction="left", x=0.0, y=-0.02, xanchor="left", yanchor="top",
                          buttons=[dict(label="Play", method="animate",
                                        args=[None, dict(frame=dict(duration=140, redraw=True), fromcurrent=True,
                                                         transition=dict(duration=0))]),
                                   dict(label="Pause", method="animate",
                                        args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate",
                                                           transition=dict(duration=0))])])],
        sliders=[dict(active=idx.index(min(idx, key=lambda q: abs(q - k0))), x=0.16, y=-0.02, len=0.84,
                      currentvalue=dict(prefix="Solar time [h]: ", font=dict(size=12)), steps=steps, ticklen=0, minorticklen=0,
                      pad=dict(t=10, b=0))])
    fig.update_xaxes(visible=False, range=[0, 10.8], row=1, col=1)
    fig.update_yaxes(visible=False, range=[-0.5, 8.7], row=1, col=1)
    fig.update_xaxes(title_text="s [kJ/kg-K]", range=[0.15, 1.0], row=1, col=2, gridcolor=GRID)
    fig.update_yaxes(title_text="T [C]", range=[0, 108], row=1, col=2, gridcolor=GRID)
    fig.update_annotations(font=dict(size=12, color=INK2))
    return _layout(fig, height)
