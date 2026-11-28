"""
Game layer: modes, scoring, controls by difficulty, feasible random scenarios,
input checks (instant) and outcome checks (after Run), and before/after summaries.
"""
from __future__ import annotations

import math
import random
from dataclasses import replace, fields
from typing import Dict, List, Optional, Tuple

from .plant import PlantConfig, PlantResult, simulate, basic_lock, PINCH, COND_APPROACH, MIN_LIFT, TE_MAX, INSULATION_LEVELS
from .scenarios import Scenario, random_scenario, BASIC_EFF

W_MIN_EFF = 300.0          # Wh: minimum daily net work for the efficiency mode

MODES = {
    "efficiency": dict(title="Highest Thermal Efficiency", unit="%",
                       goal=f"Reach the highest cycle thermal efficiency (net work / heat into the evaporator) "
                            f"while producing at least {W_MIN_EFF:.0f} Wh of net work over the day."),
    "output": dict(title="Max Total Output", unit="kWh",
                   goal="Produce as much net work as possible over the day (sunrise to the next sunrise)."),
    "survive": dict(title="Survive 24 h", unit="kWh",
                    goal="Once the plant starts, keep the net power positive for the next 24 hours, through the night "
                         "and into the next morning. Among runs that survive, more net work scores higher."),
}

# (name, label, min, max, step, group); Engineer-only controls are flagged
CONTROLS = [
    ("area", "Collector area [m^2]", 2.0, 20.0, 0.5, "Collector", False),
    ("T_max", "Collector defocus temperature [C]", 80.0, 99.0, 0.5, "Collector", False),
    ("tracking", "Sun tracking", None, None, None, "Collector", True),
    ("tilt", "Fixed tilt from horizontal [deg]", 0.0, 80.0, 1.0, "Collector", True),
    ("eta0", "Optical efficiency [-]", None, None, 0.005, "Collector", True),
    ("tank_L", "Tank volume [L]", 100.0, 2000.0, 50.0, "Storage tank", False),
    ("insulation", "Insulation level", None, None, None, "Storage tank", False),
    ("ins_cm", "Insulation thickness [cm]", 0.5, 20.0, 0.5, "Storage tank", True),
    ("Te", "Evaporating temperature [C]", 40.0, 95.0, 0.5, "Power cycle", False),
    ("Tc", "Condensing temperature [C]", 10.0, 50.0, 0.5, "Power cycle", False),
    ("superheat", "Superheat [K]", 0.0, 15.0, 0.5, "Power cycle", True),
    ("T_start", "Plant start temperature (tank top) [C]", 45.0, 99.0, 0.5, "Power cycle", False),
    ("pump_W", "Pump input power at full flow [W]", 5.0, 100.0, 1.0, "Power cycle", False),
    ("eta_t", "Turbine isentropic efficiency [-]", None, None, 0.005, "Power cycle", True),
    ("eta_p", "Pump isentropic efficiency [-]", None, None, 0.005, "Power cycle", True),
]


def controls_for(difficulty: str, sc: Scenario) -> List[tuple]:
    """Controls visible in this difficulty, with scenario-specific limits filled in."""
    out = []
    for name, label, lo, hi, step, group, eng in CONTROLS:
        if difficulty == "basic" and (eng or name == "ins_cm"):
            continue
        if difficulty == "engineer" and name == "insulation":
            continue
        if name in ("eta0", "eta_t", "eta_p"):
            lim = sc.limit(name) or (BASIC_EFF[name], BASIC_EFF[name])
            lo, hi = lim
        out.append((name, label, lo, hi, step, group))
    return out


def default_config(difficulty: str, sc: Scenario) -> PlantConfig:
    c = PlantConfig(difficulty=difficulty)
    if difficulty == "engineer":
        mids = {n: round(0.5 * (lo + hi), 3) for n, lo, hi in sc.limits}
        c = replace(c, **mids)
    tc = max(c.Tc, math.ceil(sc.T_amb_min + COND_APPROACH + 1.0))
    return basic_lock(replace(c, Tc=float(tc)))


def clamp_config(c: PlantConfig, sc: Scenario) -> PlantConfig:
    """Keep efficiencies inside the scenario limits (Engineer) or fixed (Basic)."""
    if c.difficulty == "basic":
        return basic_lock(c)
    ch = {}
    for n, lo, hi in sc.limits:
        v = getattr(c, n)
        ch[n] = min(max(v, lo), hi)
    return replace(c, **ch)


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------
def score(mode: str, r: PlantResult) -> dict:
    k, s = r.kpi, r.survive
    if mode == "efficiency":
        ok = bool(k["W_net_Wh"] >= W_MIN_EFF)
        val = k["eta_cycle"] * 100.0 if ok else 0.0
        msg = (f"Cycle efficiency {k['eta_cycle']*100:.2f} % with {k['W_net_Wh']:.0f} Wh of net work."
               if ok else f"Only {k['W_net_Wh']:.0f} Wh of net work: at least {W_MIN_EFF:.0f} Wh is needed for the efficiency to count.")
    elif mode == "output":
        ok = bool(k["W_net_Wh"] > 0)
        val = k["W_net_Wh"] / 1000.0 if ok else 0.0
        msg = f"{k['W_net_Wh']/1000:.3f} kWh of net work over the day."
    else:
        ok = bool(s["passed"])
        val = s["w_W_net_Wh"] / 1000.0 if ok else 0.0
        if ok:
            msg = f"Survived: positive net power for 24 h from start-up at hour {s['start_h']:.1f}; {val:.3f} kWh."
        elif math.isnan(s["start_h"]):
            msg = "The plant never started, so it could not survive."
        else:
            msg = f"Net power dropped to zero {s['fail_h'] - s['start_h']:.1f} h after start-up."
    return dict(mode=mode, passed=ok, score=val, unit=MODES[mode]["unit"], message=msg)


def headline(r: PlantResult) -> dict:
    """The system parameters shown on the scoreboard."""
    k = r.kpi
    return dict(peak_W=k["peak_W_net"], total_kWh=k["W_net_Wh"] / 1000.0,
                heat_in_kWh=k["E_collector_Wh"] / 1000.0, heat_lost_kWh=k["E_loss_Wh"] / 1000.0,
                net_heat_kWh=(k["E_collector_Wh"] - k["E_loss_Wh"]) / 1000.0,
                after_sunset_h=k["night_run_hours"], after_sunset_kWh=k["W_after_sunset_Wh"] / 1000.0,
                eta_cycle=k["eta_cycle"], eta_collector=k["eta_collector"], eta_daily=k["eta_daily"],
                eta_II=k["eta_II"])


# --------------------------------------------------------------------------
# feasible random scenarios
# --------------------------------------------------------------------------
def _reference(mode: str, difficulty: str, sc: Scenario) -> List[PlantConfig]:
    base = default_config(difficulty, sc)
    top = {n: hi for n, lo, hi in sc.limits}
    ins = dict(insulation="good") if difficulty == "basic" else dict(ins_cm=20.0)
    tc = float(math.ceil(sc.T_amb_min + COND_APPROACH + 1.0))
    if mode == "survive":
        return [replace(base, area=20.0, tank_L=2000.0, Te=te, Tc=tc, T_start=te + PINCH + 1.0,
                        pump_W=p, T_max=97.0, **ins, **top)
                for te, p in ((55.0, 8.0), (50.0, 6.0), (60.0, 10.0))]
    return [replace(base, area=20.0, tank_L=300.0, Te=70.0, Tc=tc, T_start=76.0, pump_W=40.0, **ins, **top)]


def feasible(mode: str, difficulty: str, sc: Scenario) -> bool:
    for c in _reference(mode, difficulty, sc):
        if score(mode, simulate(c, sc))["passed"]:
            return True
    return False


def new_scenario(mode: Optional[str], difficulty: str, rng: Optional[random.Random] = None,
                 tries: int = 40) -> Scenario:
    rng = rng or random.Random()
    for _ in range(tries):
        sc = random_scenario(difficulty, rng)
        if mode is None or feasible(mode, difficulty, sc):
            return sc
    raise RuntimeError("No feasible scenario found")


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------
def input_problems(c: PlantConfig, sc: Scenario) -> List[dict]:
    """Physically impossible settings, caught before running (shown at once with Undo)."""
    p = []
    lift_need = c.Te - c.Tc
    if c.Tc < sc.T_amb_min + COND_APPROACH:
        p.append(dict(field="Tc", title="Condenser colder than the air",
                      what=f"A condensing temperature of {c.Tc:.1f} C is below the coldest air of the day plus {COND_APPROACH:.0f} K "
                           f"({sc.T_amb_min + COND_APPROACH:.1f} C). Heat cannot flow from the condenser into warmer air.",
                      impact="The condenser could never reject heat, so the vapour would not condense and the cycle would stop."))
    if lift_need < MIN_LIFT:
        p.append(dict(field="Te", title="Temperature lift too small",
                      what=f"The evaporating temperature ({c.Te:.1f} C) is only {lift_need:.1f} K above the condensing temperature; "
                           f"the turbine needs at least {MIN_LIFT:.0f} K.",
                      impact="There is almost no pressure difference across the turbine, so it cannot produce work."))
    need = c.Te + c.superheat + PINCH
    if c.T_start < need:
        p.append(dict(field="T_start", title="Evaporator hotter than the tank",
                      what=f"The plant would start with the tank at {c.T_start:.1f} C, but boiling at {c.Te:.1f} C"
                           + (f" with {c.superheat:.1f} K of superheat" if c.superheat > 0 else "")
                           + f" needs water at {need:.1f} C or more (5 K pinch).",
                      impact="Heat cannot flow from colder water into hotter refrigerant: the evaporator would not boil the fluid."))
    if c.T_start >= c.T_max - 0.5:
        p.append(dict(field="T_start", title="Start temperature above the collector limit",
                      what=f"The collector defocuses at {c.T_max:.1f} C, so the tank can never reach the {c.T_start:.1f} C start temperature.",
                      impact="The plant would never start."))
    if c.Te > TE_MAX:
        p.append(dict(field="Te", title="Too close to the critical point",
                      what=f"R-134a becomes supercritical at 101 C; boiling above {TE_MAX:.0f} C is not allowed.",
                      impact="The evaporator could not produce a two-phase boiling process."))
    return p


def outcome_problems(r: PlantResult, mode: Optional[str] = None) -> List[dict]:
    """Physically unrealistic or failed outcomes found after a run (pop-up with Undo)."""
    k, c = r.kpi, r.config
    p = []
    if c.pump_on and k["run_hours"] < 0.1:
        p.append(dict(title="Tank never got hot enough",
                      what=f"The top of the tank peaked at {k['Ts_max']:.1f} C, below the {c.T_start:.1f} C start temperature.",
                      impact="The plant never started: no flow, no work. Add collector area, use a smaller tank or lower the start and evaporating temperatures."))
    elif c.pump_on and k["W_net_Wh"] <= 0:
        p.append(dict(title="Net work is not positive",
                      what=f"The pump used {k['W_pump_Wh']:.0f} Wh and the turbine produced {k['W_turbine_Wh']:.0f} Wh.",
                      impact="The plant consumes more work than it makes. Open the turbine valve, raise the evaporating temperature or lower the condensing temperature."))
    return p


def outcome_warnings(r: PlantResult) -> List[Tuple[str, str]]:
    k, c, b = r.kpi, r.config, r.balance
    w = []
    if not c.valve_open and c.pump_on:
        w.append(("warning", "Turbine valve closed: the vapour goes through the bypass throttle and no work is produced."))
    if k["run_hours"] >= 0.1 and k["x4_min"] < 0.88:
        w.append(("warning", f"Turbine exit quality fell to {k['x4_min']:.3f}. Below about 0.88 droplets erode the blades; superheat dries the exhaust."))
    if k["defocus_hours"] > 0.1:
        w.append(("warning", f"The tank reached the defocus temperature for {k['defocus_hours']:.1f} h: sunlight was thrown away."))
    if k["float_hours"] > 0.1:
        w.append(("warning", f"For {k['float_hours']:.1f} h the air was too warm for the condenser set point; the condenser floated up to air + 3 K."))
    if k["night_run_hours"] > 0.2:
        w.append(("success", f"The plant ran {k['night_run_hours']:.1f} h after sunset on stored heat ({k['W_after_sunset_Wh']:.0f} Wh)."))
    if b["resid_tank_rel"] < 1e-4 and b["resid_cycle_rel"] < 1e-6:
        w.append(("success", f"Energy is conserved: tank residual {b['resid_tank_rel']:.1e}, cycle residual {b['resid_cycle_rel']:.1e}."))
    return w


# --------------------------------------------------------------------------
# before / after summaries
# --------------------------------------------------------------------------
DEVICE_ROWS = [
    ("Collector", [("E_collector_Wh", "Heat collected", "Wh"), ("eta_collector", "Collector efficiency", "%")]),
    ("Storage tank", [("Ts_max", "Peak tank temperature", "C"), ("E_loss_Wh", "Heat lost to the air", "Wh")]),
    ("Evaporator", [("E_evaporator_Wh", "Heat into the cycle", "Wh"), ("Pe_max", "Boiler pressure", "kPa")]),
    ("Turbine", [("W_turbine_Wh", "Turbine work", "Wh"), ("x4_min", "Lowest exit quality", "-")]),
    ("Condenser", [("Q_condenser_Wh", "Heat rejected", "Wh"), ("float_hours", "Hours floating above set point", "h")]),
    ("Pump", [("W_pump_Wh", "Pump work", "Wh"), ("mass_kg", "Fluid circulated", "kg")]),
    ("Whole plant", [("W_net_Wh", "Net work", "Wh"), ("eta_cycle", "Cycle efficiency", "%"),
                     ("run_hours", "Run time", "h"), ("night_run_hours", "Run time after sunset", "h")]),
]


def changed_settings(a: PlantConfig, b: PlantConfig) -> List[Tuple[str, object, object]]:
    return [(f.name, getattr(a, f.name), getattr(b, f.name)) for f in fields(PlantConfig)
            if getattr(a, f.name) != getattr(b, f.name)]


def _why(device: str, key: str, d: float, changes: Dict[str, Tuple]) -> str:
    """One-line physical explanation of a device change."""
    ch = set(changes)
    up = d > 0
    if device == "Collector":
        if "area" in ch: return "More aperture collects more sunlight." if up else "Less aperture collects less sunlight."
        if ch & {"tracking", "tilt"}: return "The aperture angle to the sun changed, so the beam on it changed."
        if "eta0" in ch: return "The optical efficiency scales the absorbed sunlight."
        if ch & {"tank_L", "T_start", "Te", "pump_W"}: return "Collector losses grow with its inlet temperature, which follows the tank."
        return "Follows the tank temperature."
    if device == "Storage tank":
        if ch & {"insulation", "ins_cm"}: return "Insulation sets UA, the loss per kelvin above ambient."
        if "tank_L" in ch: return "A larger tank warms more slowly and stores more; a smaller one runs hotter."
        return "The tank temperature is the balance of heat collected, drawn and lost."
    if device == "Evaporator":
        if "pump_W" in ch: return "Pump power sets the refrigerant flow, which sets the heat drawn."
        if ch & {"Te", "superheat"}: return "The boiling temperature sets the boiler pressure and the heat per kg."
        return "Heat drawn follows how long the plant runs."
    if device == "Turbine":
        if ch & {"Te", "Tc", "superheat", "eta_t"}: return "Work per kg depends on the pressure ratio, the inlet state and the isentropic efficiency."
        return "Turbine work follows the flow and the run time."
    if device == "Condenser":
        if "Tc" in ch: return "A colder condenser lowers the back pressure and rejects heat at a lower temperature."
        return "Heat rejected = heat in - net work (first law)."
    if device == "Pump":
        if ch & {"pump_W", "eta_p"}: return "Pump input power and efficiency set the flow and the pump work."
        return "Pump work follows the run time."
    return "Net work = turbine work - pump work; efficiency = net work / heat in."


def summary(before: PlantResult, after: PlantResult) -> List[dict]:
    changes = {n: (a, b) for n, a, b in changed_settings(before.config, after.config)}
    rows = []
    for dev, items in DEVICE_ROWS:
        for key, label, unit in items:
            a, b = before.kpi[key], after.kpi[key]
            if unit == "%":
                a, b = a * 100.0, b * 100.0
            d = (b - a) if (math.isfinite(a) and math.isfinite(b)) else float("nan")
            rows.append(dict(device=dev, label=label, unit=unit, before=a, after=b, delta=d,
                             why=_why(dev, key, d if math.isfinite(d) else 0.0, changes)))
    return rows
