"""
Solar Rankine Lab: an interactive thermodynamics virtual laboratory.

Run with:   streamlit run app_legacy.py   (legacy v1 interface; the v2 app is app.py)

This file contains only the user interface. All thermodynamics lives in the
core/ package (properties, solar, cycle, storage, simulation, validation,
missions, visuals), which can be used and tested without Streamlit.
"""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import fields, replace

import numpy as np
import pandas as pd
import streamlit as st

from core import cycle as cy
from core import validation
from core import visuals as V
from core.missions import MISSIONS, engineering_rating
from core.simulation import PlantParams, instant, simulate
from core.solar import daylight_hours
from core.steady import SteadyInputs, steady_day_night

st.set_page_config(page_title="Solar Rankine Lab", page_icon=None, layout="wide")

PAGES = ["Main Menu", "Free Play", "Steady-State Calculator", "Missions",
         "Comparison", "Validation", "Assumptions"]
DEFAULTS = PlantParams()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def plot(fig, key=None):
    """Plotly chart that works on old and new Streamlit versions."""
    try:
        st.plotly_chart(fig, width="stretch", key=key)
    except TypeError:
        st.plotly_chart(fig, use_container_width=True, key=key)


def fmt_num(v: float) -> str:
    """Readable number: thousands separators for large values, scientific only for tiny ones."""
    a = abs(v)
    if a == 0:
        return "0"
    if a >= 100:
        return f"{v:,.0f}"
    if a >= 0.01:
        return f"{v:.3g}"
    return f"{v:.2e}"


def go_to(page: str):
    st.session_state["page"] = page


# (name, label, min, max, step, format)
GROUPS = {
    "Site and weather": [
        ("lat", "Latitude [deg N]", -60.0, 60.0, 0.5, "%.1f"),
        ("day", "Day of year", 1, 365, 1, "%d"),
        ("clearness", "Sky clearness [-]", 0.2, 1.0, 0.05, "%.2f"),
        ("T_mean", "Mean ambient temperature [C]", -5.0, 40.0, 0.5, "%.1f"),
        ("T_swing", "Daily ambient swing [K]", 0.0, 25.0, 0.5, "%.1f")],
    "Collector": [
        ("area", "Collector area [m^2]", 2.0, 20.0, 0.5, "%.1f"),
        ("tilt", "Tilt from horizontal [deg]", 0.0, 80.0, 1.0, "%.0f"),
        ("eta0", "Optical efficiency [-]", 0.50, 0.85, 0.01, "%.2f"),
        ("a1", "Loss coefficient a1 [W/m^2-K]", 0.5, 5.0, 0.1, "%.1f"),
        ("a2", "Loss coefficient a2 [W/m^2-K^2]", 0.0, 0.02, 0.001, "%.3f")],
    "Storage tank": [
        ("tank_L", "Water volume [L]", 100.0, 2000.0, 50.0, "%.0f"),
        ("UA", "Heat-loss coefficient UA [W/K]", 0.5, 10.0, 0.5, "%.1f"),
        ("T_tank0", "Initial tank temperature [C]", 20.0, 90.0, 1.0, "%.0f")],
    "Power cycle": [
        ("pump_W", "Pump input power at full flow [W]", 5.0, 100.0, 1.0, "%.0f"),
        ("eta_t", "Turbine isentropic efficiency [-]", 0.50, 0.90, 0.01, "%.2f"),
        ("eta_p", "Pump isentropic efficiency [-]", 0.40, 0.90, 0.01, "%.2f"),
        ("pinch", "Tank to turbine-inlet temperature drop [K]", 2.0, 15.0, 0.5, "%.1f"),
        ("approach_cond", "Condenser above ambient [K]", 3.0, 15.0, 0.5, "%.1f"),
        ("superheat", "Superheat [K]", 0.0, 12.0, 0.5, "%.1f")],
    "Controller": [
        ("T_cut", "Plant starts at tank temperature [C]", 40.0, 90.0, 1.0, "%.0f"),
        ("T_full", "Full flow at tank temperature [C]", 50.0, 98.0, 1.0, "%.0f"),
        ("T_max", "Collector defocuses near [C]", 90.0, 99.0, 0.5, "%.1f")],
}
SPEC = {s[0]: s for g in GROUPS.values() for s in g}


def _slider(prefix, name, container=st):
    n, label, lo, hi, step, fmt = SPEC[name]
    key = f"{prefix}_{n}"
    st.session_state.setdefault(key, getattr(DEFAULTS, n))
    kw = dict(min_value=type(lo)(lo), max_value=type(hi)(hi), step=type(step)(step), key=key)
    return container.slider(label, format=fmt, **kw)


def param_panel(prefix: str, groups=None, only=None, switches=True, container=st, base=None) -> PlantParams:
    """Draw the sliders and return the PlantParams they describe."""
    vals = {} if base is None else {f.name: getattr(base, f.name) for f in fields(base)}
    for gname, items in GROUPS.items():
        if groups and gname not in groups:
            continue
        names = [i[0] for i in items if (only is None or i[0] in only)]
        if not names:
            continue
        with container.expander(gname, expanded=(gname in ("Collector", "Power cycle") and only is None)):
            for n in names:
                vals[n] = _slider(prefix, n, st)
            if gname == "Site and weather" and "day" in names:
                d = dt.date(2026, 1, 1) + dt.timedelta(days=int(vals["day"]) - 1)
                st.caption(f"{d:%d %b}: {daylight_hours(vals['lat'], int(vals['day'])):.1f} h of daylight")
    if switches:
        with container.expander("Equipment operation", expanded=True):
            st.session_state.setdefault(f"{prefix}_pump_on", True)
            st.session_state.setdefault(f"{prefix}_valve_open", True)
            st.session_state.setdefault(f"{prefix}_collector_on", True)
            vals["pump_on"] = st.toggle("Pump running", key=f"{prefix}_pump_on")
            vals["valve_open"] = st.toggle("Turbine valve open (off = throttle bypass)", key=f"{prefix}_valve_open")
            vals["collector_on"] = st.toggle("Collector exposed to the sun", key=f"{prefix}_collector_on")
    if "T_full" in vals and "T_cut" in vals and vals["T_full"] <= vals["T_cut"] + 1.0:
        vals["T_full"] = vals["T_cut"] + 1.0
        container.warning("Full-flow temperature was raised to stay above the start temperature.")
    vals["day"] = int(vals.get("day", DEFAULTS.day))
    return replace(DEFAULTS, **vals)


def reset_panel(prefix: str):
    for k in list(st.session_state.keys()):
        if k.startswith(prefix + "_"):
            del st.session_state[k]


def states_table(c: cy.CycleResult) -> pd.DataFrame:
    rows = []
    for i, (s, role) in enumerate([(c.s1, "pump inlet, saturated liquid"), (c.s2, "pump exit, compressed liquid"),
                                   (c.s3, "turbine inlet"), (c.s4, "turbine exit")], start=1):
        rows.append({"State": i, "Description": role, "T [C]": round(s.T, 2), "P [kPa]": round(s.P, 1),
                     "h [kJ/kg]": round(s.h, 2), "s [kJ/kg-K]": round(s.s, 4),
                     "Phase": s.phase if s.x is None else f"two-phase, x = {s.x:.3f}"})
    return pd.DataFrame(rows)


def feedback(r):
    """Engineering warnings and notes for a finished simulation."""
    p, k, b = r.params, r.kpi, r.balance
    out = []
    if not p.pump_on:
        out.append(("info", "Pump switched off: no mass flow and no power. The tank only exchanges heat with the sun and the air."))
    elif k["run_hours"] < 0.1:
        out.append(("error", f"The plant never started. The tank stayed below the start temperature ({p.T_cut:.0f} C). "
                             "Add collector area, lower the start temperature, or reduce the tank volume."))
    if not p.valve_open and p.pump_on:
        out.append(("warning", "Turbine valve closed: all the heat goes through the bypass throttle to the condenser and no work is produced."))
    if k["run_hours"] >= 0.1 and k["x4_min"] < 0.88:
        out.append(("warning", f"Turbine exit quality fell to {k['x4_min']:.2f}. Below about 0.88 liquid droplets erode the blades."))
    if k["Ts_max"] >= p.T_max - 1.0:
        out.append(("warning", "The tank reached the collector limit and the collector defocused. Daytime heat was thrown away: "
                               "add storage, flow or turbine power."))
    if k["run_hours"] >= 0.1 and k["Pe_max"] > 0.85 * 4059:
        out.append(("warning", "Evaporator pressure is within 15 % of the critical pressure of R-134a."))
    if k["night_run_hours"] > 0.5:
        out.append(("success", f"The plant ran {k['night_run_hours']:.1f} h after sunset on stored heat."))
    if b["resid_tank_rel"] < 1e-4 and b["resid_cycle_rel"] < 1e-6:
        out.append(("success", f"Conservation: tank energy residual {b['resid_tank_rel']:.1e}, cycle residual {b['resid_cycle_rel']:.1e}."))
    else:
        out.append(("error", "Energy balance does not close; tighten the solver tolerance."))
    return out


def show_feedback(items):
    icon = {"success": "[ok]", "info": "[i]", "warning": "[!]", "error": "[x]"}
    for lvl, text in items:
        getattr(st, lvl)(f"{icon[lvl]} {text}")


def kpi_row(r):
    k = r.kpi
    c = st.columns(6)
    c[0].metric("Daily net work", f"{k['W_net_Wh']/1000:.2f} kWh")
    c[1].metric("Peak net power", f"{k['peak_W_net']:.0f} W")
    c[2].metric("Cycle efficiency", f"{k['eta_cycle']*100:.1f} %")
    c[3].metric("Solar to work", f"{k['eta_daily']*100:.1f} %")
    c[4].metric("Second-law efficiency", f"{k['eta_II']*100:.0f} %")
    c[5].metric("Run time", f"{k['run_hours']:.1f} h", f"{k['night_run_hours']:.1f} h after sunset", delta_color="off")


def cycle_at(r, k):
    S, p = r.series, r.params
    if S["frac"][k] <= 0.01:
        return None
    return cy.solve_cycle(S["Te"][k], S["Tc"][k], p.superheat, p.eta_t, p.eta_p, p.valve_open)


# ---------------------------------------------------------------------------
# sidebar
# ---------------------------------------------------------------------------
st.session_state.setdefault("page", "Main Menu")
st.session_state.setdefault("completed", set())
st.sidebar.title("Solar Rankine Lab")
st.sidebar.radio("Module", PAGES, key="page", label_visibility="collapsed")
_completed_box = st.sidebar.empty()
page = st.session_state["page"]


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------
def page_menu():
    st.title("Solar Rankine Lab")
    st.markdown("A virtual laboratory for a **solar-driven R-134a (Freon) Rankine power plant**. "
                "Sunlight heats a collector, a storage tank carries the heat past sunset, and a pump, "
                "evaporator, turbine and condenser turn it into work. You operate the plant, "
                "the thermodynamics decides what happens.")
    cards = [("Free Play", "Change any parameter, flip the pump, close the turbine valve, and watch a full day unfold with an animated plant."),
             ("Steady-State Calculator", "Type in sun hours and sun angle, get net work output W_out for a design point."),
             ("Missions", "Five engineering challenges: efficiency, power, night operation, tank heating and an integrated design."),
             ("Comparison", "Put two operating cases side by side: pressure, temperature, mass flow, work and efficiency."),
             ("Validation", "Mass, energy and second-law checks, plus solver-tolerance tests, run live."),
             ("Assumptions", "Every modelling assumption and governing equation in one place.")]
    cols = st.columns(3)
    for i, (name, text) in enumerate(cards):
        with cols[i % 3]:
            with st.container(border=True):
                st.subheader(name)
                st.write(text)
                st.button(f"Open {name}", key=f"menu_{name}", on_click=go_to, args=(name,))
    st.divider()
    st.markdown("**How the lab works.** The thermodynamic engine (`core/`) is separate from this interface. "
                "Missions are scored by engineering quantities such as efficiency, temperature limits and conservation residuals, "
                "never by arbitrary points. Warnings appear when equipment limits are exceeded.")


def page_free_play():
    st.header("Free Play")
    with st.sidebar:
        st.divider()
        st.subheader("Controls")
        st.button("Reset all controls", on_click=reset_panel, args=("fp",))
        p = param_panel("fp")
    r = simulate(p)
    kpi_row(r)
    show_feedback(feedback(r))
    t1, t2, t3, t4, t5 = st.tabs(["Plant (animated)", "Day plots", "Cycle", "Energy balance", "Data"])
    with t1:
        st.caption("Press Play, or drag the slider through the day. Pipe width follows mass flow; the tank colour follows temperature.")
        plot(V.plant_animation(r), key="fp_anim")
    with t2:
        plot(V.timeseries_figure(r), key="fp_ts")
    with t3:
        hour = st.slider("Solar time [h]", 0.0, 24.0, 12.5, 0.25, key="fp_hour")
        k = int(np.argmin(np.abs(r.t - hour)))
        c = cycle_at(r, k)
        if c is None:
            st.info("The plant is idle at this time (tank below the start temperature, pump off, or lift too small).")
        else:
            S = r.series
            a, b = st.columns([3, 2])
            with a:
                plot(V.ts_figure([c], [f"Cycle at {r.t[k]:.2f} h"]), key="fp_cyc")
            with b:
                g = cy.entropy_generation(c, S["Ts"][k] - p.pinch, S["Ta"][k])
                m = S["mdot"][k]
                st.metric("Net power", f"{S['Wnet'][k]:.0f} W")
                st.metric("Thermal efficiency / Carnot", f"{c.eta_th*100:.2f} % / {c.carnot()*100:.1f} %")
                st.metric("Second-law efficiency", f"{cy.second_law_efficiency(c, S['Ts'][k] - p.pinch, S['Ta'][k])*100:.0f} %")
                st.caption("Entropy generation rate by device [W/K]")
                st.bar_chart(pd.Series({kk: vv * m * 1000 for kk, vv in g.items() if kk != "total"}), color="#257de0")
            st.dataframe(states_table(c), hide_index=True)
    with t4:
        plot(V.energy_waterfall(r), key="fp_wf")
        b = r.balance
        st.table(pd.DataFrame({
            "Check": ["Tank: dU - (Q_col - Q_evap - Q_loss) [Wh]", "Cycle: Q_evap - Q_cond - W_net [Wh]",
                      "Collector heat: solver vs trapezoid [Wh]"],
            "Value": [f"{b['resid_tank_Wh']:.2e}", f"{b['resid_cycle_Wh']:.2e}",
                      f"{b['trap_E_col_Wh'] - r.kpi['E_collector_Wh']:.2f}"]}))
    with t5:
        df = pd.DataFrame({"hour": r.t, **{k: v for k, v in r.series.items()}})
        st.dataframe(df.iloc[::6].round(3), hide_index=True)
        st.download_button("Download full data (CSV)", df.to_csv(index=False), "solar_rankine_day.csv", "text/csv")


def page_steady():
    st.header("Steady-State Calculator")
    st.write("Quick design point: state the sun exposure and sun angle, get the net work output **W_out**. "
             "The pump input power sets the mass flow; if the sun cannot boil that flow, the flow drops to what the sun supplies.")
    d = SteadyInputs()
    with st.form("steady"):
        a, b, c = st.columns(3)
        i = SteadyInputs(
            hours_sun=a.number_input("Hours of direct sun [h]", 0.5, 24.0, d.hours_sun, 0.5),
            sun_elevation=a.number_input("Sun elevation [deg]", 0.0, 90.0, d.sun_elevation, 1.0),
            tilt=a.number_input("Collector tilt [deg]", 0.0, 90.0, d.tilt, 1.0),
            area=a.number_input("Collector area [m^2]", 0.5, 100.0, d.area, 0.5),
            dni=b.number_input("Beam irradiance [W/m^2]", 0.0, 1100.0, d.dni, 10.0),
            T_amb=b.number_input("Ambient temperature [C]", -20.0, 50.0, d.T_amb, 1.0),
            Te=b.number_input("Evaporator temperature [C]", 20.0, 95.0, d.Te, 0.5),
            superheat=b.number_input("Superheat [K]", 0.0, 20.0, d.superheat, 0.5),
            Tc_day=c.number_input("Condenser, day [C]", 0.0, 60.0, d.Tc_day, 0.5),
            Tc_night=c.number_input("Condenser, night [C]", 0.0, 60.0, d.Tc_night, 0.5),
            pump_W=c.number_input("Pump input power [W]", 1.0, 1000.0, d.pump_W, 1.0),
            eta_store=c.number_input("Storage efficiency (0 = none)", 0.0, 1.0, d.eta_store, 0.05),
            eta_t=a.number_input("Turbine efficiency", 0.3, 1.0, d.eta_t, 0.01),
            eta_p=b.number_input("Pump efficiency", 0.2, 1.0, d.eta_p, 0.01))
        st.form_submit_button("Calculate")
    try:
        o = steady_day_night(i)
    except ValueError as e:
        st.error(str(e))
        return
    m = st.columns(5)
    m[0].metric("W_out (net, daytime)", f"{o['W_out']:.1f} W")
    m[1].metric("Thermal efficiency", f"{o['day'].eta_th*100:.2f} %")
    m[2].metric("Collector heat", f"{o['Q_sol']:.0f} W")
    m[3].metric("Energy per day", f"{o['E_total']:.0f} Wh")
    m[4].metric("Night run", f"{o['t_night']:.1f} h")
    if o["flow_limited_by"] == "pump":
        st.info(f"Flow set by pump power; the sun has {o['surplus']:.0f} W to spare, which charges the store.")
    else:
        st.warning("Flow limited by sunlight: the pump could move more fluid than the sun can boil.")
    a, b = st.columns([3, 2])
    with a:
        cs, ls = [o["day"]], ["Daytime"]
        if o["night"] is not None:
            cs.append(o["night"]); ls.append("Night")
        plot(V.ts_figure(cs, ls), key="st_ts")
    with b:
        st.dataframe(states_table(o["day"]), hide_index=True)
        st.write(f"Turbine {o['day'].wt:.2f} kJ/kg, pump {o['day'].wp:.2f} kJ/kg, heat in {o['day'].qin:.1f} kJ/kg. "
                 f"Carnot limit {o['carnot']*100:.1f} %.")


def load_solution(key: str):
    """Put a reference solution into the mission sliders and run it (callback, so widget state may change)."""
    m = MISSIONS[key]
    choice = {}
    for name, (label, lo, hi, default, step) in m.knobs.items():
        choice[name] = float(m.solution.get(name, default))
        st.session_state[f"m_{key}_{name}"] = choice[name]
    st.session_state[f"mres_{key}"] = (choice, m.run(choice))



def page_missions():
    st.header("Missions")
    key = st.selectbox("Mission", list(MISSIONS), format_func=lambda k: MISSIONS[k].title, key="mission_key")
    m = MISSIONS[key]
    left, right = st.columns([2, 3])
    with left:
        st.subheader(m.title)
        st.write(m.brief)
        st.markdown(f"**Objective.** {m.objective}")
        choice = {}
        for name, (label, lo, hi, default, step) in m.knobs.items():
            kk = f"m_{key}_{name}"
            st.session_state.setdefault(kk, float(default))
            choice[name] = st.slider(label, float(lo), float(hi), step=float(step), key=kk)
        run = st.button("Run mission", type="primary", key=f"run_{key}")
        with st.expander("Hint and worked solution"):
            st.write(m.hint)
            st.button("Load a worked solution", key=f"sol_{key}", on_click=load_solution, args=(key,))
        if run:
            res = m.run(choice)
            st.session_state[f"mres_{key}"] = (choice, res)
    with right:
        saved = st.session_state.get(f"mres_{key}")
        if saved is None:
            st.info("Set your operating conditions and press Run mission.")
            return
        choice, res = saved
        crit = m.evaluate(res)
        done = all(c[3] for c in crit)
        if done:
            if key not in st.session_state["completed"]:
                st.balloons()
            st.session_state["completed"].add(key)
            st.success("[ok] Mission complete: every criterion is met.")
        else:
            st.session_state["completed"].discard(key)
            st.error(f"[x] Not yet: {sum(1 for c in crit if not c[3])} of {len(crit)} criteria failed.")
        st.table(pd.DataFrame([{"Criterion": c[0], "Result": c[1], "Requirement": c[2],
                                "Status": "[ok] met" if c[3] else "[x] not met"} for c in crit]))
        rating = engineering_rating(res)
        cols = st.columns(len(rating))
        for col, (k_, v) in zip(cols, rating.items()):
            col.metric(k_, fmt_num(v))
        if m.kind == "steady":
            plot(V.ts_figure([res["day"]], ["Your cycle"]), key=f"mt_{key}")
        else:
            show_feedback(feedback(res))
            ta, tb = st.tabs(["Day plots", "Plant animation"])
            with ta:
                plot(V.timeseries_figure(res, height=700), key=f"mp_{key}")
            with tb:
                plot(V.plant_animation(res), key=f"ma_{key}")


PRESETS = {
    "Baseline": {},
    "Large collector, small tank": dict(area=14.0, tank_L=200.0),
    "Large tank (all-night operation)": dict(area=14.0, tank_L=900.0, pump_W=22.0, T_cut=60.0, T_full=78.0),
    "High-efficiency (hot tank)": dict(T_cut=82.0, T_full=92.0, area=12.0, eta_t=0.85),
    "Winter day": dict(day=355),
    "Cloudy day": dict(clearness=0.5),
}


def page_compare():
    st.header("Comparison Mode")
    st.write("Run two operating cases on the same day and compare pressure, temperature, mass flow, energy transfer, work and efficiency.")
    cols = st.columns(2)
    res, names = [], ["Case A", "Case B"]
    for col, nm, default in zip(cols, names, ["Baseline", "Large tank (all-night operation)"]):
        with col:
            st.subheader(nm)
            pre = st.selectbox("Preset", list(PRESETS), index=list(PRESETS).index(default), key=f"cmp_{nm}_preset")
            if st.session_state.get(f"cmp_{nm}_last") != pre:             # preset changed: load its values
                for k, v in PRESETS[pre].items():
                    st.session_state[f"cmp{nm[-1]}_{k}"] = v
                st.session_state[f"cmp_{nm}_last"] = pre
            p = param_panel(f"cmp{nm[-1]}", groups=None,
                            only=["area", "tilt", "tank_L", "pump_W", "T_cut", "T_full", "superheat", "eta_t", "day", "clearness"],
                            switches=False, container=st, base=replace(DEFAULTS, **PRESETS[pre]))
            res.append(simulate(p))
    a, b = res
    keys = [("W_net_Wh", "Net work [Wh]", "%.0f"), ("eta_cycle", "Cycle efficiency", "%.4f"),
            ("eta_daily", "Solar to work", "%.4f"), ("eta_II", "Second-law efficiency", "%.3f"),
            ("E_collector_Wh", "Collector heat [Wh]", "%.0f"), ("E_evaporator_Wh", "Heat to evaporator [Wh]", "%.0f"),
            ("Q_condenser_Wh", "Heat rejected [Wh]", "%.0f"), ("mass_circulated_kg", "Mass circulated [kg]", "%.0f"),
            ("peak_W_net", "Peak net power [W]", "%.0f"), ("Ts_max", "Peak tank temperature [C]", "%.1f"),
            ("Pe_max", "Peak evaporator pressure [kPa]", "%.0f"), ("run_hours", "Run time [h]", "%.1f"),
            ("night_run_hours", "Run time after sunset [h]", "%.1f")]
    df = pd.DataFrame({"Quantity": [k[1] for k in keys],
                       "Case A": [k[2] % a.kpi[k[0]] for k in keys],
                       "Case B": [k[2] % b.kpi[k[0]] for k in keys],
                       "B - A": [k[2] % (b.kpi[k[0]] - a.kpi[k[0]]) for k in keys]})
    st.table(df)
    plot(V.comparison_figure(a, b, "Case A", "Case B"), key="cmp_fig")
    for nm, r in zip(names, res):
        with st.expander(f"Performance feedback: {nm}"):
            show_feedback(feedback(r))


def page_validation():
    st.header("Validation")
    st.write("Each check below is executed now. Tolerances are stated next to the measured value.")
    checks = validation.run_all()
    df = pd.DataFrame([{"Category": c.category, "Check": c.name, "Value": f"{c.value:.2e}",
                        "Tolerance": f"{c.tolerance:.1e}", "Result": "[ok] pass" if c.passed else "[x] FAIL"}
                       for c in checks])
    st.metric("Checks passed", f"{sum(c.passed for c in checks)} / {len(checks)}")
    st.dataframe(df, hide_index=True, height=35 * (len(df) + 1) + 3)
    st.subheader("Solver tolerance study")
    rows = [{"rtol": f"{t:.0e}", "Daily net work [Wh]": simulate(PlantParams(), rtol=t).kpi["W_net_Wh"],
             "RHS evaluations": simulate(PlantParams(), rtol=t).nfev} for t in (1e-3, 1e-4, 1e-6, 1e-9)]
    st.table(pd.DataFrame(rows).round(4))


def page_assumptions():
    st.header("Assumptions and governing equations")
    st.markdown(open(os.path.join(os.path.dirname(__file__), "docs", "assumptions.md")).read())


{"Main Menu": page_menu, "Free Play": page_free_play, "Steady-State Calculator": page_steady,
 "Missions": page_missions, "Comparison": page_compare, "Validation": page_validation,
 "Assumptions": page_assumptions}[page]()

_done = [MISSIONS[k].title.split(":")[0] for k in MISSIONS if k in st.session_state["completed"]]
_completed_box.caption("Missions completed: " + (", ".join(_done) if _done else "none yet"))
