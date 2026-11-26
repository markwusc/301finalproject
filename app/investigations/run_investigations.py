"""Seven parameter investigations. Writes one CSV and one PNG per study into this folder.
Run from the project root:  python investigations/run_investigations.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dataclasses import replace
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from core import cycle as cy
from core.simulation import PlantParams, simulate
from core.visuals import BLUE, ORANGE, AQUA, YELLOW

OUT = os.path.dirname(os.path.abspath(__file__))
BASE = PlantParams()
INK, GRID = "#2b2b2b", "#e6e6e6"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": "#999", "axes.labelcolor": INK, "text.color": INK,
                     "xtick.color": INK, "ytick.color": INK, "axes.spines.top": False, "axes.spines.right": False})


def sim(**kw):
    return simulate(replace(BASE, **kw)).kpi


def sweep(name, xs, fn):
    df = pd.DataFrame([{"x": x, **fn(x)} for x in xs])
    df.to_csv(os.path.join(OUT, f"{name}.csv"), index=False)
    return df


def panels(name, df, xlabel, specs, title, vline=None):
    """specs: list of panels; each panel = (ylabel, [(column, label, color), ...])."""
    n = len(specs)
    fig, axes = plt.subplots(1, n, figsize=(4.2 * n, 3.4), dpi=150)
    axes = np.atleast_1d(axes)
    for ax, (yl, series) in zip(axes, specs):
        for col, lab, colr in series:
            ax.plot(df["x"], df[col], color=colr, lw=2, marker="o", ms=4, mfc=colr, mec="white", mew=1, label=lab)
        if vline is not None:
            ax.axvline(vline, color="#bbb", lw=1, ls=":")
        ax.set_xlabel(xlabel); ax.set_ylabel(yl)
        ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
        if len(series) > 1:
            ax.legend(frameon=False, fontsize=8.5, loc="best")
    fig.suptitle(title, x=0.01, ha="left", fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(os.path.join(OUT, f"{name}.png")); plt.close(fig)


# 1 evaporator temperature (steady cycle, Tc = 30 C, no superheat)
def inv1(Te):
    c = cy.solve_cycle(Te, 30.0, 0.0, 0.8, 0.7)
    return dict(eta_th=c.eta_th * 100, carnot=c.carnot() * 100, wnet=c.wnet, x4=c.x4, Pe=c.Pe, Pc=c.Pc)
d1 = sweep("inv1_evaporator_temperature", np.arange(40, 96, 5.0), inv1)
panels("inv1_evaporator_temperature", d1, "Evaporator temperature [C]",
       [("Efficiency [%]", [("eta_th", "Cycle", BLUE), ("carnot", "Carnot limit", ORANGE)]),
        ("Net work [kJ/kg]", [("wnet", "w_net", BLUE)]),
        ("Turbine exit quality [-]", [("x4", "x4", BLUE)])],
       "1. Evaporator temperature (condenser 30 C, eta_t 0.80)")

# 2 ambient temperature (day-night swing fixed)
d2 = sweep("inv2_ambient_temperature", np.arange(5, 41, 5.0),
           lambda T: {k: sim(T_mean=T)[k] for k in ("W_net_Wh", "eta_cycle", "eta_daily", "night_run_hours")})
d2["eta_cycle"] *= 100; d2["eta_daily"] *= 100
panels("inv2_ambient_temperature", d2, "Mean ambient temperature [C]",
       [("Daily net work [Wh]", [("W_net_Wh", "W_net", BLUE)]),
        ("Efficiency [%]", [("eta_cycle", "Cycle", BLUE), ("eta_daily", "Solar to work", ORANGE)])],
       "2. Ambient (condenser) temperature, 24 h simulation")

# 3 tank volume
d3 = sweep("inv3_tank_volume", np.arange(100, 2001, 150.0),
           lambda V_: {k: sim(tank_L=V_)[k] for k in ("W_net_Wh", "night_run_hours", "Ts_max", "eta_daily")})
d3["eta_daily"] *= 100
panels("inv3_tank_volume", d3, "Tank volume [L]",
       [("Daily net work [Wh]", [("W_net_Wh", "W_net", BLUE)]),
        ("Run time after sunset [h]", [("night_run_hours", "night run", BLUE)]),
        ("Peak tank temperature [C]", [("Ts_max", "Ts max", BLUE)])],
       "3. Storage tank volume")

# 4 season and tilt (two latitudes of tilt behaviour: summer, winter)
days = np.arange(1, 366, 30)
d4 = sweep("inv4_season", days, lambda d: {"W_net_Wh": sim(day=int(d))["W_net_Wh"],
                                          "E_incident_Wh": sim(day=int(d))["E_incident_Wh"]})
tilts = np.arange(0, 81, 10.0)
d4b = pd.DataFrame([{"x": t, "summer": sim(tilt=t, day=172)["W_net_Wh"], "winter": sim(tilt=t, day=355)["W_net_Wh"]} for t in tilts])
d4b.to_csv(os.path.join(OUT, "inv4_tilt.csv"), index=False)
fig, axes = plt.subplots(1, 3, figsize=(12.6, 3.4), dpi=150)
axes[0].plot(d4["x"], d4["E_incident_Wh"] / 1000, color=BLUE, lw=2, marker="o", ms=4, mec="white")
axes[0].set_ylabel("Solar energy on collector [kWh]")
axes[1].plot(d4["x"], d4["W_net_Wh"], color=BLUE, lw=2, marker="o", ms=4, mec="white")
axes[1].set_ylabel("Daily net work [Wh]")
for ax in axes[:2]:
    ax.set_xlabel("Day of year")
axes[2].plot(d4b["x"], d4b["summer"], color=ORANGE, lw=2, marker="o", ms=4, mec="white", label="21 June")
axes[2].plot(d4b["x"], d4b["winter"], color=BLUE, lw=2, marker="o", ms=4, mec="white", label="21 December")
axes[2].set_xlabel("Collector tilt [deg]"); axes[2].set_ylabel("Daily net work [Wh]")
axes[2].legend(frameon=False, fontsize=8.5)
for ax in axes:
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
fig.suptitle(f"4. Season and collector tilt (latitude {BASE.lat:.0f} N)", x=0.01, ha="left", fontsize=11, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.93)); fig.savefig(os.path.join(OUT, "inv4_season_tilt.png")); plt.close(fig)

# 5 pump power
d5 = sweep("inv5_pump_power", np.arange(5, 101, 10.0),
           lambda W: {k: sim(pump_W=W)[k] for k in ("W_net_Wh", "peak_W_net", "run_hours", "mass_circulated_kg", "eta_daily", "Ts_max")})
d5["eta_daily"] *= 100
panels("inv5_pump_power", d5, "Pump input power at full flow [W]",
       [("Daily net work [Wh]", [("W_net_Wh", "W_net", BLUE)]),
        ("Peak net power [W]", [("peak_W_net", "peak", BLUE)]),
        ("Run time [h]", [("run_hours", "run time", BLUE)])],
       "5. Pump power (sets the mass flow)")

# 6 turbine efficiency and superheat
d6 = sweep("inv6_turbine_efficiency", np.arange(0.5, 0.91, 0.05),
           lambda e: {k: sim(eta_t=e)[k] for k in ("W_net_Wh", "eta_cycle", "x4_min")})
d6["eta_cycle"] *= 100
d6b = sweep("inv6_superheat", np.arange(0, 12.1, 2.0),
            lambda s: {k: sim(superheat=s)[k] for k in ("W_net_Wh", "eta_cycle", "x4_min")})
d6b["eta_cycle"] *= 100
fig, axes = plt.subplots(1, 4, figsize=(16.5, 3.4), dpi=150)
axes[0].plot(d6["x"], d6["W_net_Wh"], color=BLUE, lw=2, marker="o", ms=4, mec="white"); axes[0].set_xlabel("Turbine isentropic efficiency [-]"); axes[0].set_ylabel("Daily net work [Wh]")
axes[1].plot(d6["x"], d6["x4_min"], color=BLUE, lw=2, marker="o", ms=4, mec="white"); axes[1].set_xlabel("Turbine isentropic efficiency [-]"); axes[1].set_ylabel("Minimum turbine exit quality [-]")
axes[2].plot(d6b["x"], d6b["W_net_Wh"], color=BLUE, lw=2, marker="o", ms=4, mec="white"); axes[2].set_xlabel("Superheat [K]"); axes[2].set_ylabel("Daily net work [Wh]")
axes[3].plot(d6b["x"], d6b["x4_min"], color=BLUE, lw=2, marker="o", ms=4, mec="white"); axes[3].set_xlabel("Superheat [K]"); axes[3].set_ylabel("Minimum turbine exit quality [-]")
for ax in axes:
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
fig.suptitle("6. Turbine efficiency and superheat", x=0.01, ha="left", fontsize=11, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.93)); fig.savefig(os.path.join(OUT, "inv6_turbine_superheat.png")); plt.close(fig)

# 7 collector area
d7 = sweep("inv7_collector_area", np.arange(2, 20.1, 2.0),
           lambda A: {k: sim(area=A)[k] for k in ("W_net_Wh", "eta_daily", "Ts_max", "run_hours", "E_loss_Wh", "E_collector_Wh")})
d7["eta_daily"] *= 100
panels("inv7_collector_area", d7, "Collector area [m^2]",
       [("Daily net work [Wh]", [("W_net_Wh", "W_net", BLUE)]),
        ("Solar to work [%]", [("eta_daily", "eta", BLUE)]),
        ("Peak tank temperature [C]", [("Ts_max", "Ts max", BLUE)])],
       "7. Collector area")

pd.set_option("display.width", 200)
for n, d in [("1", d1), ("2", d2), ("3", d3), ("4", d4), ("4b", d4b), ("5", d5), ("6", d6), ("6b", d6b), ("7", d7)]:
    print("---", n); print(d.round(3).to_string(index=False))
