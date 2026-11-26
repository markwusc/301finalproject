"""
Mission mode: engineering objectives that the player must meet by changing
operating conditions. Scoring is based on engineering quantities (efficiency,
power, temperature limits, conservation residuals), never on arbitrary points.

Each mission lists
    kind      'steady' (steady-state calculator) or 'day' (24 h transient)
    fixed     parameters the player cannot change
    knobs     parameters the player may change: name -> (label, min, max, default, step)
    criteria  functions that turn a result into (label, actual, requirement, passed)
"""
from __future__ import annotations

from dataclasses import dataclass, replace, field
from typing import Callable, Dict, List, Tuple

import numpy as np

from .simulation import PlantParams, SimResult, simulate
from .steady import SteadyInputs, steady_day_night

Criterion = Tuple[str, str, str, bool]       # label, actual, requirement, passed


@dataclass
class Mission:
    key: str
    title: str
    kind: str
    brief: str
    objective: str
    fixed: Dict[str, float]
    knobs: Dict[str, Tuple[str, float, float, float, float]]
    hint: str
    evaluate: Callable[[object], List[Criterion]]
    solution: Dict[str, float] = field(default_factory=dict)    # reference solution (tested)

    def build_inputs(self, choice: Dict[str, float]):
        base = SteadyInputs if self.kind == "steady" else PlantParams
        vals = {k: v[3] for k, v in self.knobs.items()}
        vals.update(choice)
        vals.update(self.fixed)
        return base(**vals)

    def run(self, choice: Dict[str, float]):
        p = self.build_inputs(choice)
        return steady_day_night(p) if self.kind == "steady" else simulate(p)


def _c(label, actual, requirement, ok) -> Criterion:
    return (label, actual, requirement, bool(ok))


# ---- mission 1: Rankine efficiency (steady) ---------------------------------
def _eval_eff(o) -> List[Criterion]:
    d = o["day"]
    x4 = d.x4 if d.x4 is not None else 1.0
    p = o["inputs"]
    return [
        _c("Thermal efficiency", f"{d.eta_th*100:.2f} %", ">= 11.0 %", d.eta_th >= 0.11),
        _c("Turbine exit quality", "superheated" if d.x4 is None else f"{x4:.3f}", ">= 0.88", x4 >= 0.88),
        _c("Condenser temperature", f"{p['Tc_day']:.1f} C", ">= 25 C (hot-climate air cooling)", p["Tc_day"] >= 25.0),
        _c("Evaporator temperature", f"{p['Te']:.1f} C", "<= 95 C (critical point is 101 C)", p["Te"] <= 95.0),
    ]


# ---- mission 2: turbine power (steady) --------------------------------------
def _eval_turbine(o) -> List[Criterion]:
    d, p = o["day"], o["inputs"]
    x4 = d.x4 if d.x4 is not None else 1.0
    return [
        _c("Net power output", f"{o['W_out']:.0f} W", "260 W +/- 5 %", 247.0 <= o["W_out"] <= 273.0),
        _c("Pump input power", f"{p['pump_W']:.0f} W", "<= 40 W", p["pump_W"] <= 40.0),
        _c("Collector area", f"{p['area']:.1f} m^2", "<= 5 m^2", p["area"] <= 5.0),
        _c("Flow supplied by the sun", f"{o['m']/o['m_pump']*100:.0f} % of pump flow", ">= 99 %",
           o["m"] >= 0.99 * o["m_pump"]),
        _c("Turbine exit quality", "superheated" if d.x4 is None else f"{x4:.3f}", ">= 0.88", x4 >= 0.88),
    ]


# ---- mission 3: night shift (day simulation) --------------------------------
def _eval_night(r: SimResult) -> List[Criterion]:
    k = r.kpi
    return [
        _c("Operating hours after sunset", f"{k['night_run_hours']:.1f} h", ">= 6 h", k["night_run_hours"] >= 6.0),
        _c("Daily net work", f"{k['W_net_Wh']:.0f} Wh", ">= 1800 Wh", k["W_net_Wh"] >= 1800.0),
        _c("Peak tank temperature", f"{k['Ts_max']:.1f} C", "<= 96 C", k["Ts_max"] <= 96.0),
        _c("Minimum turbine exit quality", f"{k['x4_min']:.3f}", ">= 0.88", k["x4_min"] >= 0.88),
    ]


# ---- mission 4: tank heating (transient, plant off) --------------------------
def _eval_tank(r: SimResult) -> List[Criterion]:
    i = int(np.argmin(np.abs(r.t - 12.0)))
    T12 = float(r.series["Ts"][i])
    k = r.kpi
    return [
        _c("Tank temperature at 12:00 solar time", f"{T12:.1f} C", ">= 80 C", T12 >= 80.0),
        _c("Collector area", f"{r.params.area:.1f} m^2", "<= 14 m^2 (roof space)", r.params.area <= 14.0),
        _c("Tank volume", f"{r.params.tank_L:.0f} L", ">= 400 L (hot-water demand)", r.params.tank_L >= 400.0),
        _c("Peak tank temperature", f"{k['Ts_max']:.1f} C", "<= 98 C", k["Ts_max"] <= 98.0),
    ]


# ---- mission 5: integrated system -----------------------------------------
def _eval_integrated(r: SimResult) -> List[Criterion]:
    k, b = r.kpi, r.balance
    ratio = k["W_pump_Wh"] / k["W_turbine_Wh"] if k["W_turbine_Wh"] > 0 else 1.0
    return [
        _c("Daily net work", f"{k['W_net_Wh']:.0f} Wh", ">= 2400 Wh", k["W_net_Wh"] >= 2400.0),
        _c("Pump work / turbine work", f"{ratio*100:.1f} %", "<= 11 %", ratio <= 0.11),
        _c("Peak tank temperature", f"{k['Ts_max']:.1f} C", "<= 97 C", k["Ts_max"] <= 97.0),
        _c("Minimum turbine exit quality", f"{k['x4_min']:.3f}", ">= 0.88", k["x4_min"] >= 0.88),
        _c("Energy-balance closure", f"{b['resid_tank_rel']:.1e}", "<= 1e-4", b["resid_tank_rel"] <= 1e-4),
    ]


MISSIONS: Dict[str, Mission] = {m.key: m for m in [
    Mission(
        "rankine", "Rankine Challenge: efficiency", "steady",
        "The plant is limited by temperature, not by sunlight. Improve the thermal efficiency "
        "of the cycle without letting the turbine ingest too much liquid.",
        "Reach a cycle thermal efficiency of 11 % or more.",
        dict(area=10.0, pump_W=30.0, hours_sun=6.0, sun_elevation=60.0, tilt=30.0, dni=900.0, T_amb=25.0),
        {"Te": ("Evaporator temperature [C]", 50.0, 100.0, 80.0, 0.5),
         "Tc_day": ("Condenser temperature [C]", 15.0, 45.0, 30.0, 0.5),
         "superheat": ("Superheat [K]", 0.0, 30.0, 0.0, 1.0),
         "eta_t": ("Turbine efficiency", 0.60, 0.88, 0.80, 0.01)},
        "Raise Te, keep the condenser as cold as the rules allow, and buy turbine efficiency. "
        "Superheat dries the exhaust but lowers the average heat-addition temperature.",
        _eval_eff,
        solution=dict(Te=95.0, Tc_day=25.0, superheat=0.0, eta_t=0.86)),
    Mission(
        "turbine", "Turbine Challenge: power output", "steady",
        "A small off-grid load needs 260 W. Size the pump and collector so that the sun can "
        "boil all of the flow the pump delivers.",
        "Deliver 260 W net (within 5 %) with at most 40 W of pump power and 5 m^2 of collector.",
        dict(hours_sun=6.0, sun_elevation=60.0, tilt=30.0, dni=900.0, T_amb=25.0,
             Tc_day=30.0, eta_t=0.80, eta_p=0.70),
        {"area": ("Collector area [m^2]", 2.0, 14.0, 6.0, 0.1),
         "pump_W": ("Pump input power [W]", 5.0, 60.0, 30.0, 0.5),
         "Te": ("Evaporator temperature [C]", 50.0, 95.0, 80.0, 0.5)},
        "Net power is roughly pump power times (w_t/w_p - 1): a higher evaporator temperature "
        "raises w_t/w_p, but the collector then loses more heat to the air.",
        _eval_turbine,
        solution=dict(area=5.0, pump_W=40.0, Te=85.0)),
    Mission(
        "night", "Night-Shift Challenge: day/night operation", "day",
        "Make the plant follow the day/night cycle. The tank stores daytime heat; run the cycle "
        "for at least six hours after the sun has set, without overheating the tank.",
        "Run 6 h or more after sunset, produce 1800 Wh or more, keep the tank at or below 96 C.",
        dict(lat=34.05, day=172, clearness=0.95),
        {"area": ("Collector area [m^2]", 4.0, 16.0, 8.0, 0.5),
         "tank_L": ("Storage volume [L]", 100.0, 2000.0, 500.0, 50.0),
         "pump_W": ("Pump input power [W]", 10.0, 60.0, 30.0, 1.0),
         "T_cut": ("Plant start temperature [C]", 55.0, 90.0, 70.0, 1.0),
         "T_full": ("Full-flow temperature [C]", 60.0, 95.0, 85.0, 1.0)},
        "Night hours come from stored heat: more storage and a lower start temperature keep the "
        "turbine turning longer, but a lower tank temperature costs cycle efficiency.",
        _eval_night,
        solution=dict(area=14.0, tank_L=900.0, pump_W=22.0, T_cut=60.0, T_full=78.0)),
    Mission(
        "tank", "Transient Challenge: heat the tank", "day",
        "A cold tank (25 C) is heated by the sun alone, with the pump switched off. Reach the "
        "target temperature by solar noon without boiling the collector loop.",
        "Tank at 80 C or more by 12:00 with at most 14 m^2 of collector and at least 400 L of water.",
        dict(lat=34.05, day=80, clearness=0.95, pump_on=False, warmup_days=0, T_tank0=25.0),
        {"area": ("Collector area [m^2]", 4.0, 20.0, 8.0, 0.5),
         "tilt": ("Collector tilt [deg]", 0.0, 80.0, 30.0, 1.0),
         "tank_L": ("Storage volume [L]", 100.0, 1500.0, 500.0, 50.0)},
        "Heating a larger tank takes more energy: the collector must deliver m c dT before noon, "
        "so area and an incidence angle near 0 matter more than anything else.",
        _eval_tank,
        solution=dict(area=14.0, tilt=34.0, tank_L=400.0)),
    Mission(
        "integrated", "Integrated System Challenge", "day",
        "Combine everything: collector, tank, pump and cycle controls. Maximise the daily "
        "work while the pump stays economical and every limit is respected.",
        "At least 2400 Wh net, pump work no more than 11 % of turbine work, tank at or below 97 C, "
        "exit quality 0.88 or more.",
        dict(lat=34.05, day=172, clearness=0.95),
        {"area": ("Collector area [m^2]", 4.0, 14.0, 8.0, 0.5),
         "tank_L": ("Storage volume [L]", 200.0, 1000.0, 500.0, 50.0),
         "pump_W": ("Pump input power [W]", 10.0, 50.0, 30.0, 1.0),
         "superheat": ("Superheat [K]", 0.0, 4.0, 0.0, 0.5),
         "T_cut": ("Plant start temperature [C]", 55.0, 90.0, 70.0, 1.0),
         "T_full": ("Full-flow temperature [C]", 60.0, 95.0, 85.0, 1.0)},
        "Every watt of pump power buys mass flow, and mass flow drains the tank. A hot tank "
        "raises cycle efficiency; a cold tank stores more heat per degree.",
        _eval_integrated,
        solution=dict(area=13.5, tank_L=650.0, pump_W=26.0, superheat=3.5, T_cut=58.0, T_full=72.0)),
]}


def engineering_rating(outcome) -> Dict[str, float]:
    """Engineering quantities shown after a mission (no arbitrary points)."""
    if isinstance(outcome, dict):                          # steady result
        d = outcome["day"]
        return {"Thermal efficiency [%]": d.eta_th * 100,
                "Fraction of Carnot": d.eta_th / d.carnot(),
                "Net power [W]": outcome["W_out"]}
    k = outcome.kpi
    return {"Daily net work [Wh]": k["W_net_Wh"],
            "Cycle efficiency [%]": k["eta_cycle"] * 100,
            "Second-law efficiency [%]": k["eta_II"] * 100,
            "Energy-balance residual": outcome.balance["resid_tank_rel"]}
