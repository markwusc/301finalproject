"""
Solar Rankine Lab v2: an interactive thermodynamics virtual laboratory.

Run with:   streamlit run app.py

One main page with a Sandbox, three game modes and a Basic / Engineer
difficulty switch, a scoreboard of best runs (saved to scores.json next to
this file), animated plant, analysis windows, pop-ups for physically
impossible settings and a before/after summary of every change.
All thermodynamics lives in core/ (plant.py, scenarios.py, game.py).
"""
from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from core import game as G
from core import visuals2 as V
from core.plant import PlantConfig, simulate, INSULATION_LEVELS, tank_UA
from core.scenarios import SEASONS, CASES, Scenario, random_scenario

st.set_page_config(page_title="Solar Rankine Lab", layout="wide")
SCORES = Path(__file__).with_name("scores.json")
SS = st.session_state


# ---------------------------------------------------------------------------
# scores (local file)
# ---------------------------------------------------------------------------
def load_scores() -> dict:
    try:
        return json.loads(SCORES.read_text())
    except Exception:
        return {}


def save_scores(s: dict):
    try:
        SCORES.write_text(json.dumps(s, indent=1))
    except Exception:
        pass


def record(mode, diff, sc: Scenario, cfg: PlantConfig, r, res) -> bool:
    if not res["passed"]:
        return False
    s = load_scores()
    key = f"{mode}|{diff}"
    if key in s and s[key]["score"] >= res["score"]:
        return False
    s[key] = dict(score=res["score"], scenario=sc.to_dict(), config=asdict(cfg), headline=G.headline(r),
                  date=dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    save_scores(s)
    return True


FMT = {"efficiency": lambda v: f"{v:.2f} %", "output": lambda v: f"{v:.3f} kWh", "survive": lambda v: f"{v:.3f} kWh"}


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------
SS.setdefault("view", "home")
SS.setdefault("difficulty", "basic")
SS.setdefault("mode", None)
SS.setdefault("history", [])
SS.setdefault("popup", None)
SS.setdefault("run", None)
SS.setdefault("prev", None)
WIDGETS = ["area", "T_max", "tracking", "tilt", "eta0", "tank_L", "insulation", "ins_cm", "Te", "Tc", "superheat",
           "T_start", "pump_W", "eta_t", "eta_p", "pump_on", "valve_open", "collector_on"]


def load_widgets(cfg: PlantConfig):
    for n in WIDGETS:
        SS[f"w_{n}"] = getattr(cfg, n)
    SS["committed"] = {n: getattr(cfg, n) for n in WIDGETS}


def config_from_widgets() -> PlantConfig:
    vals = {n: SS[f"w_{n}"] for n in WIDGETS if f"w_{n}" in SS}
    return G.clamp_config(replace(PlantConfig(difficulty=SS.difficulty), **vals), SS.scenario)


def start_play(mode, scenario: Scenario = None, cfg: PlantConfig = None):
    SS.mode, SS.view = mode, "play"
    if scenario is None and mode is None:          # sandbox opens on a friendly day
        lim = random_scenario("engineer").limits if SS.difficulty == "engineer" else ()
        scenario = Scenario("summer", "best", 40.0, lim)
    SS.scenario = scenario or G.new_scenario(mode, SS.difficulty)
    base = G.default_config(SS.difficulty, SS.scenario)
    if cfg is not None:
        base = G.clamp_config(replace(cfg, difficulty=SS.difficulty), SS.scenario)
    load_widgets(base)
    SS.run, SS.prev, SS.history, SS.popup = None, None, [], None
    SS.brief = mode is not None
    if mode is None:
        do_run()


def set_difficulty():
    d = SS["diff_pick"]
    if not d or d == SS.difficulty:
        return
    SS.difficulty = d
    if SS.view == "play":
        lim = random_scenario("engineer").limits if d == "engineer" else ()
        SS.scenario = Scenario(SS.scenario.season, SS.scenario.case, SS.scenario.T_tank0, lim)
        cfg = replace(config_from_widgets(), difficulty=d)
        if d == "engineer":
            cfg = replace(cfg, **{n: round(0.5 * (lo + hi), 3) for n, lo, hi in lim})
        load_widgets(G.clamp_config(cfg, SS.scenario))
        SS.run, SS.prev, SS.history = None, None, []
        SS.brief = SS.mode is not None
        if SS.mode is None:
            do_run()


def on_widget(name: str):
    """Instant check: physically impossible settings open a pop-up with Undo."""
    cfg = config_from_widgets()
    probs = G.input_problems(cfg, SS.scenario)
    if probs:
        SS.popup = dict(kind="input", probs=probs, field=name, old=SS["committed"].get(name))
    else:
        SS["committed"][name] = SS[f"w_{name}"]


def do_run():
    cfg = config_from_widgets()
    probs = G.input_problems(cfg, SS.scenario)
    if probs:
        SS.popup = dict(kind="blocked", probs=probs)
        return
    r = simulate(cfg, SS.scenario)
    if SS.run is not None:
        SS.history.append((SS.run, SS.prev))
        SS.history = SS.history[-30:]
    SS.prev, SS.run = SS.run, r
    SS.committed = {n: getattr(cfg, n) for n in WIDGETS}
    SS.score = G.score(SS.mode, r) if SS.mode else None
    SS.new_best = record(SS.mode, SS.difficulty, SS.scenario, cfg, r, SS.score) if SS.mode else False
    out = G.outcome_problems(r)
    if out:
        SS.popup = dict(kind="outcome", probs=out, can_undo=bool(SS.history))


def undo_run():
    if not SS.history:
        return
    SS.run, SS.prev = SS.history.pop()
    load_widgets(SS.run.config)
    SS.score = G.score(SS.mode, SS.run) if SS.mode else None
    SS.new_best = False


def undo_field(name, old):
    SS[f"w_{name}"] = old
    SS.popup = None


def close_popup():
    SS.popup = None


@st.dialog("Physically impossible", width="large")
def popup_dialog():
    p = SS.popup
    title = {"input": "This setting is not physically possible", "blocked": "Fix these settings before running",
             "outcome": "The run shows a problem"}[p["kind"]]
    st.subheader(title)
    for q in p["probs"]:
        st.error(f"**{q['title']}**\n\n**What was violated.** {q['what']}\n\n**Impact on the plant.** {q['impact']}")
    a, b = st.columns(2)
    if p["kind"] == "input":
        a.button("Undo change", type="primary", on_click=undo_field, args=(p["field"], p["old"]), width="stretch")
        b.button("Keep and edit", on_click=close_popup, width="stretch")
    elif p["kind"] == "outcome" and p.get("can_undo"):
        a.button("Undo (back to the previous run)", type="primary", on_click=lambda: (undo_run(), close_popup()), width="stretch")
        b.button("Keep this result", on_click=close_popup, width="stretch")
    else:
        a.button("Back to the settings", type="primary", on_click=close_popup, width="stretch")


@st.dialog("Scenario briefing", width="large")
def briefing_dialog():
    m = G.MODES[SS.mode]
    st.subheader(m["title"])
    st.write(m["goal"])
    st.table(pd.DataFrame(briefing_rows(SS.scenario), columns=["", "Value"]).set_index(""))
    st.caption("Basic: uniform tank, sun tracking, fixed efficiencies (turbine 0.80, pump 0.70, optics 0.75)." if SS.difficulty == "basic"
               else "Engineer: stratified tank; efficiencies are adjustable only inside the limits above.")
    if st.button("Start", type="primary"):
        SS.brief = False
        st.rerun()


def clock(h):
    return V.clock_str(h)


def briefing_rows(sc: Scenario):
    rows = [("Scenario", sc.label), ("Daylight", f"{sc.daylight:.1f} h (sunrise {clock(sc.sunrise)}, sunset {clock(24 - sc.sunrise)} solar time)"),
            ("Sky clearness", f"{sc.clearness*100:.0f} % of clear-sky sunlight"), ("Air temperature", f"{sc.T_amb_min:.1f} to {sc.T_amb_max:.1f} C (warmest at 15:00)"),
            ("Tank at sunrise", f"{sc.T_tank0:.1f} C")]
    names = dict(eta_t="Turbine efficiency", eta_p="Pump efficiency", eta0="Collector optical efficiency")
    for n, lo, hi in sc.limits:
        rows.append((names[n], f"between {lo:.3f} and {hi:.3f} (this plant's limits)"))
    return rows


def diff_picker(where):
    SS["diff_pick"] = SS.difficulty
    opts = ["basic", "engineer"]
    try:
        where.segmented_control("Difficulty", opts, key="diff_pick", format_func=str.title, on_change=set_difficulty)
    except Exception:
        where.radio("Difficulty", opts, key="diff_pick", format_func=str.title, horizontal=True, on_change=set_difficulty)


# ---------------------------------------------------------------------------
# home
# ---------------------------------------------------------------------------
def scoreboard(compact=False):
    s = load_scores()
    rows = []
    for k, m in G.MODES.items():
        row = {"Mode": m["title"]}
        for d in ("basic", "engineer"):
            e = s.get(f"{k}|{d}")
            row[d.title()] = f"{FMT[k](e['score'])}  ({Scenario.from_dict(e['scenario']).label}, {e['date']})" if e else "no score yet"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if compact:
        return
    det = []
    for k, m in G.MODES.items():
        for d in ("basic", "engineer"):
            e = s.get(f"{k}|{d}")
            if not e:
                continue
            x = e["headline"]
            det.append({"Best run": f"{m['title']} ({d.title()})", "Peak power [W]": round(x["peak_W"]), "Total work [kWh]": round(x["total_kWh"], 3),
                        "Heat in [kWh]": round(x["heat_in_kWh"], 2), "Heat lost [kWh]": round(x["heat_lost_kWh"], 2), "Net heat [kWh]": round(x["net_heat_kWh"], 2),
                        "Run after sunset [h]": round(x["after_sunset_h"], 1), "Work after sunset [kWh]": round(x["after_sunset_kWh"], 3),
                        "Cycle eff. [%]": round(100 * x["eta_cycle"], 2), "Collector eff. [%]": round(100 * x["eta_collector"], 1),
                        "Solar to work [%]": round(100 * x["eta_daily"], 2), "Second law [%]": round(100 * x["eta_II"], 1)})
    if det:
        st.markdown("**System parameters of the best runs**")
        st.dataframe(pd.DataFrame(det), hide_index=True, width="stretch")
        cols = st.columns(len(det))
        i = 0
        for k, m in G.MODES.items():
            for d in ("basic", "engineer"):
                e = s.get(f"{k}|{d}")
                if e:
                    cols[i].button(f"Replay: {m['title']} ({d.title()})", key=f"rep_{k}_{d}",
                                   on_click=replay, args=(k, d, e))
                    i += 1
    st.caption(f"Scores are saved on this computer in {SCORES.name}.")


def replay(mode, diff, e):
    SS.difficulty = diff
    start_play(mode, Scenario.from_dict(e["scenario"]), PlantConfig(**e["config"]))


def page_home():
    st.title("Solar Rankine Lab")
    st.write("A solar-driven R-134a Rankine power plant with thermal storage. Sunlight heats a collector, a water tank stores the heat, "
             "and a pump, evaporator, turbine and condenser turn it into work. Every day is a real Los Angeles season.")
    diff_picker(st)
    st.caption({"basic": "Basic: uniform tank temperature, a collector that always faces the sun, fixed device efficiencies.",
                "engineer": "Engineer: stratified tank (10 layers), sun tracking on or off with a fixed tilt, device efficiencies inside this plant's random limits, superheat and insulation thickness."}[SS.difficulty])
    st.subheader("Choose a mode")
    cols = st.columns(4)
    with cols[0].container(border=True):
        st.markdown("**Sandbox**")
        st.write("Free play: any season and case, every setting, pump and valve switches. No score.")
        st.button("Open sandbox", type="primary", on_click=start_play, args=(None,))
    for col, (k, m) in zip(cols[1:], G.MODES.items()):
        with col.container(border=True):
            st.markdown(f"**{m['title']}**")
            st.write(m["goal"])
            st.button("Play", key=f"play_{k}", type="primary", on_click=start_play, args=(k,))
    st.subheader("Scoreboard")
    scoreboard()


# ---------------------------------------------------------------------------
# play
# ---------------------------------------------------------------------------
LABEL = {c[0]: c[1] for c in G.CONTROLS}


def controls():
    sc = SS.scenario
    sb = st.sidebar
    sb.header("Settings")
    groups = {}
    for name, label, lo, hi, step, group in G.controls_for(SS.difficulty, sc):
        groups.setdefault(group, []).append((name, label, lo, hi, step))
    for g in ("Collector", "Storage tank", "Power cycle"):
        with sb.expander(g, expanded=True):
            for name, label, lo, hi, step in groups.get(g, []):
                key = f"w_{name}"
                if name == "tracking":
                    st.toggle("Sun tracking", key=key, on_change=on_widget, args=(name,))
                    if not SS[key]:
                        st.slider("Fixed tilt from horizontal [deg]", 0.0, 80.0, step=1.0, key="w_tilt", on_change=on_widget, args=("tilt",))
                    else:
                        st.caption("Tracking: the aperture faces the sun all day (incidence angle 0 deg).")
                elif name == "tilt":
                    continue
                elif name == "insulation":
                    st.selectbox(label, list(INSULATION_LEVELS), key=key, on_change=on_widget, args=(name,))
                    lv = SS[key]
                    st.caption(f"{INSULATION_LEVELS[lv]:g} cm of foam: UA {tank_UA(SS['w_tank_L'], INSULATION_LEVELS[lv]):.2f} W/K at this volume")
                else:
                    SS[key] = float(min(max(SS[key], lo), hi))
                    st.slider(label, float(lo), float(hi), step=float(step), key=key, on_change=on_widget, args=(name,), disabled=lo == hi)
    if SS.mode is None:
        with sb.expander("Equipment operation", expanded=True):
            st.toggle("Pump running", key="w_pump_on", on_change=on_widget, args=("pump_on",))
            st.toggle("Turbine valve open (off = throttle bypass)", key="w_valve_open", on_change=on_widget, args=("valve_open",))
            st.toggle("Collector exposed to the sun", key="w_collector_on", on_change=on_widget, args=("collector_on",))
    cfg = config_from_widgets()
    if SS.run is not None:
        ch = [x for x in G.changed_settings(SS.run.config, cfg) if x[0] != "difficulty"]
        if ch:
            sb.info(f"{len(ch)} setting(s) changed. Press Run to see the effect.")
    a, b, c = sb.columns(3)
    a.button("Run", type="primary", on_click=do_run, width="stretch")
    b.button("Undo run", on_click=undo_run, disabled=not SS.history, width="stretch")
    c.button("Reset", on_click=lambda: load_widgets(G.default_config(SS.difficulty, SS.scenario)), width="stretch")


def briefing_panel():
    sc = SS.scenario
    with st.expander(f"Scenario briefing: {sc.label}", expanded=SS.mode is not None):
        st.table(pd.DataFrame(briefing_rows(sc), columns=["", "Value"]).set_index(""))
        if SS.mode:
            st.markdown(f"**Goal.** {G.MODES[SS.mode]['goal']}")
            st.button("New random scenario", on_click=start_play, args=(SS.mode,))
        else:
            a, b, c, d = st.columns(4)
            season = a.selectbox("Season", list(SEASONS), index=list(SEASONS).index(sc.season), format_func=lambda k: SEASONS[k]["label"])
            case = b.selectbox("Case", list(CASES), index=list(CASES).index(sc.case))
            t0 = c.slider("Tank temperature at sunrise [C]", 20.0, 70.0, float(sc.T_tank0), 1.0)
            if (season, case, t0) != (sc.season, sc.case, sc.T_tank0):
                SS.scenario = Scenario(season, case, t0, sc.limits)
                do_run()
                st.rerun()
            if d.button("Random scenario"):
                SS.scenario = random_scenario(SS.difficulty)
                do_run()
                st.rerun()


def summary_panel():
    st.markdown("#### Change summary")
    if SS.run is None or SS.prev is None:
        st.caption("Change some settings and press Run: this panel compares the new run with the previous one, device by device, and explains each change.")
        return
    ch = [x for x in G.changed_settings(SS.prev.config, SS.run.config) if x[0] != "difficulty"]
    st.info("You changed: " + ("; ".join(f"{LABEL.get(n, n)}: {a} -> {b}" for n, a, b in ch) if ch else "the scenario or nothing"))
    dev = None
    for row in G.summary(SS.prev, SS.run):
        if row["device"] != dev:
            dev = row["device"]
            st.markdown(f"**{dev}**")
        a, b, d = row["before"], row["after"], row["delta"]
        dig = 3 if row["unit"] == "-" else 2 if row["unit"] == "%" else 1 if row["unit"] in ("C", "h") else 0
        same = not math.isfinite(d) or abs(d) < max(1e-3, 0.002 * max(abs(a or 0), abs(b or 0)))
        arrow = "=" if same else ("▲" if d > 0 else "▼")
        fa = "-" if not math.isfinite(a) else f"{a:.{dig}f}"
        fb = "-" if not math.isfinite(b) else f"{b:.{dig}f}"
        st.markdown(f"{row['label']}: {fa} -> {fb} {'' if row['unit'] == '-' else row['unit']} {arrow}" + ("" if same else f"  \n<small>{row['why']}</small>"),
                    unsafe_allow_html=True)


def time_pick(r, key):
    H = 48.0 if SS.mode == "survive" else 24.0
    idx = [i for i in range(len(r.t)) if r.t[i] <= H + 1e-9 and abs((r.t[i] * 60) % 15) < 1e-6]
    best = max(idx, key=lambda i: r.series["Wnet"][i])
    return st.select_slider("Time of day (solar)", options=idx, value=best, key=key,
                            format_func=lambda i: f"{clock(r.scenario.sunrise + r.t[i])} ({r.t[i]:.2f} h after sunrise)")


def devices_tab(r):
    i = time_pick(r, "dev_t")
    S, c = r.series, r.config
    m = st.columns(5)
    m[0].metric("Sun", f"{S['alt'][i]:.0f} deg" if S["alt"][i] > 0 else "below horizon", f"beam {S['G'][i]:.0f} W/m^2", delta_color="off")
    m[1].metric("Collector", f"{S['Qcol'][i]/1000:.2f} kW", f"inlet {S['T_bot'][i]:.1f} C", delta_color="off")
    m[2].metric("Tank", f"{S['T_top'][i]:.1f} / {S['T_bot'][i]:.1f} C" if r.layers.shape[0] > 1 else f"{S['T_top'][i]:.1f} C",
                "top / bottom" if r.layers.shape[0] > 1 else "uniform", delta_color="off")
    m[3].metric("Tank losses", f"{S['Qloss'][i]:.0f} W", f"UA {r.balance['UA']:.2f} W/K", delta_color="off")
    m[4].metric("Stored since sunrise", f"{S['E_tank_kWh'][i]:.2f} kWh", f"{'charging' if S['Q_store'][i] >= 0 else 'discharging'} {abs(S['Q_store'][i]):.0f} W", delta_color="off")
    cyc = V.cycle_at_sample(r, i)
    if cyc is None:
        st.info("The power cycle is idle at this time: no refrigerant flow.")
        return
    st.markdown("**Refrigerant states (R-134a)**")
    rows = []
    for n, lab, s in [(1, "Pump inlet (condenser exit)", cyc.s1), (2, "Pump exit (evaporator inlet)", cyc.s2),
                      (3, "Turbine inlet (evaporator exit)", cyc.s3), (4, "Turbine exit (condenser inlet)", cyc.s4)]:
        rows.append({"State": n, "Location": lab, "T [C]": round(s.T, 2), "P [kPa]": round(s.P, 1), "h [kJ/kg]": round(s.h, 2),
                     "s [kJ/kg-K]": round(s.s, 4), "Phase": V.phase_text(s).split(",")[0], "Quality x": "-" if s.x is None else f"{s.x:.3f}"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    from core import cycle as cy
    g = cy.entropy_generation(cyc, S["T_top"][i], S["Ta"][i])
    mm = S["mdot"][i]
    dev = [("Pump", f"{S['Wp'][i]:.1f} W in", f"w_p = {cyc.wp:.3f} kJ/kg", g["pump"] * mm * 1000, "Raises the liquid from the condenser to the boiler pressure; liquid is nearly incompressible, so little work is needed."),
           ("Evaporator", f"{S['Qev'][i]/1000:.2f} kW in", f"q_in = {cyc.qin:.1f} kJ/kg", g["evaporator"] * mm * 1000, f"Hot tank water boils the refrigerant at {c.Te} C ({cyc.Pe:.0f} kPa)."),
           ("Turbine", f"{S['Wt'][i]:.1f} W out", f"w_t = {cyc.wt:.2f} kJ/kg", g["turbine"] * mm * 1000, f"Expands the vapour from {cyc.Pe:.0f} to {cyc.Pc:.0f} kPa; exit is {V.phase_text(cyc.s4)}."),
           ("Condenser", f"{S['Qc'][i]/1000:.2f} kW out", f"q_out = {cyc.qout:.1f} kJ/kg", g["condenser"] * mm * 1000, f"Rejects heat to the air at {S['Ta'][i]:.1f} C and returns saturated liquid at {cyc.Tc:.1f} C.")]
    st.markdown(f"**Devices** (mass flow {mm*1000:.2f} g/s)")
    st.dataframe(pd.DataFrame(dev, columns=["Device", "Rate", "Per kg", "Entropy generated [W/K]", "What happens"]), hide_index=True, width="stretch")


def ts_tab(r):
    i = time_pick(r, "ts_t")
    cyc = V.cycle_at_sample(r, i)
    if cyc is None:
        st.info("The plant is idle at this time.")
        return
    a, b = st.columns([3, 2])
    a.plotly_chart(V.ts_figure([cyc], [f"Cycle at {clock(r.scenario.sunrise + r.t[i])}"]), width="stretch", key="tsfig")
    h4s = cyc.s3.h - cyc.wt / cyc.eta_t
    h2s = cyc.s1.h + cyc.wp * cyc.eta_p
    b.metric("Thermal efficiency / Carnot", f"{cyc.eta_th*100:.2f} % / {cyc.carnot()*100:.1f} %", f"{cyc.eta_th/cyc.carnot()*100:.0f} % of Carnot", delta_color="off")
    b.metric(f"Turbine, eta_t = {cyc.eta_t:.3f}", f"{cyc.wt:.2f} kJ/kg", f"ideal {cyc.s3.h - h4s:.2f} kJ/kg", delta_color="off")
    b.metric(f"Pump, eta_p = {cyc.eta_p:.3f}", f"{cyc.wp:.3f} kJ/kg", f"ideal {h2s - cyc.s1.h:.3f} kJ/kg", delta_color="off")
    b.info(f"An ideal turbine would follow the dashed vertical line (constant entropy) from 3 to 4s. Friction leaves the real exit at a higher enthalpy, "
           f"generating {cyc.s4.s - cyc.s3.s:.4f} kJ/kg-K of entropy. The loop area is the net work per kg; the evaporator at {cyc.Te:.1f} C sets the top and the condenser at {cyc.Tc:.1f} C the bottom.")


def energy_tab(r):
    k = r.kpi
    st.markdown("**Energy in and out of each device over the day**")
    st.plotly_chart(V.energy_by_device(r), width="stretch", key="edev")
    st.info(f"Of {k['E_incident_Wh']/1000:.1f} kWh of sunlight on the aperture the collector delivers {k['E_collector_Wh']/1000:.1f} kWh ({k['eta_collector']*100:.0f} %). "
            f"The tank loses {k['E_loss_Wh']/1000:.2f} kWh and changes its store by {k['dU_tank_Wh']/1000:+.2f} kWh. The cycle turns {k['E_evaporator_Wh']/1000:.2f} kWh of heat "
            f"into {k['W_turbine_Wh']/1000:.3f} kWh of turbine work and must reject {k['Q_condenser_Wh']/1000:.2f} kWh in the condenser (second law).")
    st.plotly_chart(V.waterfall(r), width="stretch", key="ewf")
    st.caption(f"Conservation: tank residual {r.balance['resid_tank_Wh']:.1e} Wh, cycle residual {r.balance['resid_cycle_Wh']:.1e} Wh.")


def storage_tab(r):
    H = 48.0 if SS.mode == "survive" else 24.0
    st.info("The tank is the plant's battery. Top: the instantaneous rate at which energy enters (charging) or leaves (discharging) the tank. "
            "Middle: its running total since sunrise. Bottom: the temperature of each layer.")
    st.plotly_chart(V.storage_figure(r, H), width="stretch", key="stfig")
    k = r.kpi
    a, b, c = st.columns(3)
    a.metric("Peak stored", f"{np.max(r.series['E_tank_kWh'][: int(np.searchsorted(r.t, H))]):.2f} kWh")
    b.metric("Losses over the day", f"{k['E_loss_Wh']/1000:.2f} kWh")
    c.metric("Net change over the day", f"{k['dU_tank_Wh']/1000:.2f} kWh")


def page_play():
    m = G.MODES.get(SS.mode) if SS.mode else None
    top = st.columns([1, 4, 2, 2])
    top[0].button("< Main page", on_click=lambda: SS.update(view="home"))
    top[1].title(m["title"] if m else "Sandbox")
    diff_picker(top[2])
    if SS.mode:
        best = load_scores().get(f"{SS.mode}|{SS.difficulty}")
        top[3].metric("Best", FMT[SS.mode](best["score"]) if best else "none yet")
    controls()
    briefing_panel()
    main, side = st.columns([3, 1])
    with side:
        summary_panel()
        if SS.mode:
            st.markdown("#### Scoreboard")
            scoreboard(compact=True)
    with main:
        r = SS.run
        if r is None:
            st.info("Read the briefing, adjust the settings and press Run." if SS.mode else "Press Run to simulate the day.")
            return
        if SS.mode:
            s = SS.score
            (st.success if s["passed"] else st.error)(f"### {FMT[SS.mode](s['score']) if s['passed'] else 'No score'}\n{s['message']}"
                                                       + ("\n\n**New best score for this mode and difficulty!**" if SS.get("new_best") else ""))
        x = G.headline(r)
        c = st.columns(6)
        c[0].metric("Total net work", f"{x['total_kWh']:.2f} kWh")
        c[1].metric("Peak net power", f"{x['peak_W']:.0f} W")
        c[2].metric("Heat collected", f"{x['heat_in_kWh']:.1f} kWh", f"lost {x['heat_lost_kWh']:.2f} kWh", delta_color="off")
        c[3].metric("After sunset", f"{x['after_sunset_h']:.1f} h", f"{x['after_sunset_kWh']:.2f} kWh", delta_color="off")
        c[4].metric("Cycle efficiency", f"{x['eta_cycle']*100:.2f} %", f"solar to work {x['eta_daily']*100:.2f} %", delta_color="off")
        c[5].metric("Collector / 2nd law", f"{x['eta_collector']*100:.0f} % / {x['eta_II']*100:.0f} %")
        for lvl, txt in G.outcome_warnings(r):
            getattr(st, lvl)(txt)
        H = 48.0 if SS.mode == "survive" else 24.0
        tabs = st.tabs(["Plant", "Devices", "T-s diagram", "Energy balance", "Storage", "Day plots", "Data"])
        with tabs[0]:
            st.caption("Press Play: pipe colour shows the phase (blue liquid, purple two-phase, orange saturated vapour, red superheated), white dots move with the flow, "
                       "the turbine and pump rotors turn with their power, the collector follows the sun and grows with its area, the tank grows with its volume.")
            st.plotly_chart(V.plant_animation(r, H), width="stretch", key="plant")
        with tabs[1]:
            devices_tab(r)
        with tabs[2]:
            ts_tab(r)
        with tabs[3]:
            energy_tab(r)
        with tabs[4]:
            storage_tab(r)
        with tabs[5]:
            k = r.kpi
            st.info(f"The sun sets how much heat the collector delivers; the tank warms until its top reaches the {r.config.T_start:g} C start temperature, then the pump starts and "
                    f"the turbine produces power. The plant ran {k['run_hours']:.1f} h on the scored day, {k['night_run_hours']:.1f} h of it after sunset on stored heat. "
                    "Net power = turbine - pump; it stays roughly constant at full flow because the boiler and condenser are held at their set points"
                    + (f", except when warm air forces the condenser above its set point ({k['float_hours']:.1f} h)." if k["float_hours"] > 0.1 else "."))
            st.plotly_chart(V.day_plots(r, H), width="stretch", key="days")
        with tabs[6]:
            df = pd.DataFrame({"t_h_after_sunrise": r.t, **{k: v for k, v in r.series.items()}})
            for j in range(r.layers.shape[0] if r.layers.shape[0] > 1 else 0):
                df[f"T_layer{j+1}"] = r.layers[j]
            st.dataframe(df.iloc[::6].round(3), hide_index=True)
            st.download_button("Download full data (CSV)", df.to_csv(index=False), "solar_rankine_run.csv", "text/csv")


if SS.view == "home":
    page_home()
else:
    page_play()
    if SS.get("brief") and SS.mode and SS.popup is None:
        briefing_dialog()
if SS.popup is not None:
    popup_dialog()
