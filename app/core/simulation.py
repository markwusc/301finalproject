"""
24-hour transient simulation of the solar Rankine plant.

Plant layout
    sun -> collector -> storage tank -> evaporator (R-134a) -> turbine
                                         ^                         |
                                         pump <- condenser <-------+

The tank is a transient control volume; the pump, evaporator, turbine and
condenser are steady-flow devices that follow the tank temperature through a
quasi-steady cycle solution (their time constants are seconds, the tank's are
hours). This is the "combination of SSSF devices and a transient system" of
project category 6.

State vector (SI units)
    y[0] tank temperature [C]
    y[1] incident beam energy on the aperture [J]
    y[2] collector heat [J]        y[3] evaporator heat [J]
    y[4] tank loss [J]             y[5] turbine work [J]
    y[6] pump work [J]             y[7] condenser heat [J]
    y[8] exergy supplied to the cycle [J]      y[9] circulated mass [kg]
The quadrature states let the energy balance be checked without any
post-processing error: they are integrated by the same solver step as the
tank temperature.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Dict

import numpy as np
from scipy.integrate import solve_ivp

from . import cycle as cy
from . import solar
from .properties import K
from .storage import StorageTank

TE_MAX = 95.0          # keep clear of the R-134a critical point (101 C)
MIN_LIFT = 6.0         # K between Te and Tc below which the plant is stopped


@dataclass(frozen=True)
class PlantParams:
    # site and sun
    lat: float = 34.05            # deg N (Los Angeles)
    day: int = 172                # day of year (Jun 21)
    clearness: float = 1.0        # 1 = clear sky
    T_mean: float = 22.0          # mean ambient, C
    T_swing: float = 12.0         # peak-to-peak daily ambient swing, K
    # collector
    tilt: float = 30.0            # deg from horizontal
    area: float = 8.0             # m^2
    eta0: float = 0.75
    a1: float = 1.5               # W/m^2-K
    a2: float = 0.005             # W/m^2-K^2
    # storage
    tank_L: float = 500.0
    UA: float = 3.0               # W/K
    T_tank0: float = 30.0         # C (initial value of the warm-up day)
    # cycle
    pinch: float = 5.0            # K between tank and turbine-inlet temperature
    approach_cond: float = 8.0    # K between ambient and condensing temperature
    superheat: float = 0.0        # K
    eta_t: float = 0.80
    eta_p: float = 0.70
    pump_W: float = 30.0          # electrical pump power at full flow
    # control
    T_cut: float = 70.0           # tank temperature at which the plant starts, C
    T_full: float = 85.0          # tank temperature for full flow, C
    T_max: float = 98.0           # collector defocuses as the tank nears this, C
    # operator switches
    pump_on: bool = True
    valve_open: bool = True       # False = turbine isolated, throttle bypass
    collector_on: bool = True
    warmup_days: int = 3          # days run before the reported day so the tank state is periodic


@dataclass
class SimResult:
    params: PlantParams
    t: np.ndarray                 # hours, 0-24
    series: Dict[str, np.ndarray]
    kpi: Dict[str, float]
    balance: Dict[str, float]
    nfev: int


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def instant(p: PlantParams, t_s: float, Ts: float) -> dict:
    """All instantaneous quantities for time t_s [s] and tank temperature Ts [C]."""
    tank = StorageTank(p.tank_L, p.UA)
    hour = (t_s / 3600.0) % 24.0
    sin_alt, alt = solar.sun_position(hour, p.lat, p.day)
    dni = solar.beam_irradiance(sin_alt, p.day, p.clearness)
    cos_i = solar.cos_incidence(hour, p.lat, p.day, p.tilt)
    g_eff = dni * cos_i
    Ta = solar.ambient_temperature(hour, p.T_mean, p.T_swing)

    # collector: useful heat falls to zero as the tank approaches T_max
    taper = _clip01((p.T_max - Ts) / 5.0)
    Qcol = (solar.collector_heat(g_eff, Ts, Ta, p.area, p.eta0, p.a1, p.a2) * taper
            if p.collector_on else 0.0)
    Qloss = tank.loss(Ts, Ta)

    # evaporator and condenser temperatures follow the tank and the ambient air
    Te = min(Ts - p.pinch - p.superheat, TE_MAX)     # turbine-inlet temperature = Ts - pinch
    Tc = Ta + p.approach_cond
    frac = _clip01((Ts - p.T_cut) / max(p.T_full - p.T_cut, 1e-6)) if p.pump_on else 0.0
    frac *= _clip01((Te - Tc - MIN_LIFT) / 4.0)

    out = dict(hour=hour, alt=alt, sin_alt=sin_alt, dni=dni, cos_i=cos_i, g_eff=g_eff,
               Ta=Ta, Ts=Ts, Te=Te, Tc=Tc, Qcol=Qcol, Qloss=Qloss, frac=frac,
               mdot=0.0, Qev=0.0, Qc=0.0, Wt=0.0, Wp=0.0, Wnet=0.0, Ex=0.0,
               Pe=float("nan"), Pc=float("nan"), x4=float("nan"), eta_th=0.0)
    if frac > 0.0:
        c = cy.solve_cycle(Te, Tc, p.superheat, p.eta_t, p.eta_p, p.valve_open)
        m = frac * p.pump_W / 1000.0 / c.wp             # kg/s
        out.update(mdot=m, Qev=m * c.qin * 1000.0, Qc=m * c.qout * 1000.0,
                   Wt=m * c.wt * 1000.0, Wp=m * c.wp * 1000.0,
                   Wnet=m * c.wnet * 1000.0, Pe=c.Pe, Pc=c.Pc,
                   x4=(c.x4 if c.x4 is not None else 1.0), eta_th=c.eta_th)
        out["Ex"] = out["Qev"] * (1.0 - (Ta + K) / (Ts + K))
    return out


def _rhs(p: PlantParams, C: float):
    def f(t, y):
        d = instant(p, t, y[0])
        return [(d["Qcol"] - d["Qev"] - d["Qloss"]) / C,
                d["g_eff"] * p.area, d["Qcol"], d["Qev"], d["Qloss"],
                d["Wt"], d["Wp"], d["Qc"], d["Ex"], d["mdot"]]
    return f


@lru_cache(maxsize=128)
def simulate(p: PlantParams, rtol: float = 1e-6, step_min: float = 5.0) -> SimResult:
    """Integrate the plant over warmup_days + 1 days and report the last day."""
    C = StorageTank(p.tank_L, p.UA).capacity
    t_end = (p.warmup_days + 1) * 86400.0
    t0 = p.warmup_days * 86400.0
    t_eval = np.unique(np.concatenate([np.arange(t0, t_end + 1.0, step_min * 60.0), [t0, t_end]]))
    y0 = [p.T_tank0] + [0.0] * 9
    atol = [1e-8, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-9]
    sol = solve_ivp(_rhs(p, C), (0.0, t_end), y0, method="RK45", rtol=rtol, atol=atol,
                    max_step=300.0, t_eval=t_eval)
    if not sol.success:
        raise RuntimeError(sol.message)

    keys = ["hour", "alt", "dni", "g_eff", "Ta", "Te", "Tc", "Qcol", "Qloss", "frac", "mdot",
            "Qev", "Qc", "Wt", "Wp", "Wnet", "Pe", "Pc", "x4", "eta_th"]
    S = {k: np.zeros(sol.t.size) for k in keys}
    for i, (t, Ts) in enumerate(zip(sol.t, sol.y[0])):
        d = instant(p, t, Ts)
        for k in keys:
            S[k][i] = d[k]
    S["Ts"] = sol.y[0].copy()
    th = (sol.t - t0) / 3600.0
    Y0, Y1 = sol.y[:, 0], sol.y[:, -1]
    D = Y1 - Y0                                     # window increments

    # ---- key performance indicators (daily, last simulated day) -----------
    wh = 1.0 / 3600.0
    running = S["frac"] > 0.05
    night = S["alt"] <= 0.0
    dd = np.diff(th)
    dt_h = np.concatenate([[dd[0] / 2], (dd[:-1] + dd[1:]) / 2, [dd[-1] / 2]])   # trapezoid weights, sum = 24 h
    E_in, E_col, E_ev, E_loss = D[1] * wh, D[2] * wh, D[3] * wh, D[4] * wh
    Wt_d, Wp_d, Qc_d, Ex_d = D[5] * wh, D[6] * wh, D[7] * wh, D[8] * wh
    W_net = Wt_d - Wp_d
    kpi = dict(
        E_incident_Wh=E_in, E_collector_Wh=E_col, E_evaporator_Wh=E_ev, E_loss_Wh=E_loss,
        W_turbine_Wh=Wt_d, W_pump_Wh=Wp_d, W_net_Wh=W_net, Q_condenser_Wh=Qc_d,
        eta_collector=E_col / E_in if E_in > 0 else 0.0,
        eta_cycle=W_net / E_ev if E_ev > 0 else 0.0,
        eta_daily=W_net / E_in if E_in > 0 else 0.0,
        eta_II=W_net / Ex_d if Ex_d > 0 else 0.0,
        run_hours=float(np.sum(dt_h[running])),
        night_run_hours=float(np.sum(dt_h[running & night])),
        peak_W_net=float(S["Wnet"].max()), Ts_max=float(S["Ts"].max()),
        Ts_min=float(S["Ts"].min()),
        x4_min=float(np.nanmin(S["x4"][running])) if running.any() else float("nan"),
        mass_circulated_kg=D[9],
        Pe_max=float(np.nanmax(S["Pe"])) if running.any() else float("nan"),
    )

    # ---- conservation checks ------------------------------------------------
    dU = C * (Y1[0] - Y0[0]) * wh                                   # tank energy change, Wh
    resid_tank = dU - (E_col - E_ev - E_loss)
    resid_cycle = E_ev - Qc_d - W_net
    trap = lambda a: float(np.trapezoid(a, th))      # Wh from W values on an hourly axis
    bal = dict(
        dU_tank_Wh=dU, resid_tank_Wh=resid_tank,
        resid_tank_rel=abs(resid_tank) / max(E_col, 1e-9),
        resid_cycle_Wh=resid_cycle, resid_cycle_rel=abs(resid_cycle) / max(E_ev, 1e-9),
        trap_E_col_Wh=trap(S["Qcol"]), trap_E_ev_Wh=trap(S["Qev"]),
        mass_from_pump_kg=float(np.trapezoid(
            np.where(S["Wp"] > 0, S["mdot"], 0.0), th * 3600.0)),
    )
    return SimResult(p, th, S, kpi, bal, sol.nfev)


def run_with(p: PlantParams, **changes) -> SimResult:
    """Convenience: simulate a modified copy of p."""
    return simulate(replace(p, **changes))
