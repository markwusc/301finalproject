"""
Steady-state day/night calculator.

This is the original "quick" model: the user states how many hours of sun
there are and the sun elevation, and the code returns the net work output.
It mirrors the MATLAB companion script line for line, which is how the two
implementations are cross-checked in tests/test_validation.py.

Pump input power sets the mass flow; if the collector cannot boil that flow,
the flow is reduced to what the sun can supply. Surplus heat charges an ideal
thermal store which runs the plant again at night with a colder condenser.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

from . import cycle as cy
from .solar import collector_heat


@dataclass
class SteadyInputs:
    hours_sun: float = 6.0
    sun_elevation: float = 60.0      # deg above horizon
    tilt: float = 30.0               # deg, collector faces the sun azimuth
    area: float = 6.0                # m^2
    dni: float = 900.0               # W/m^2
    T_amb: float = 25.0              # C
    Te: float = 80.0                 # C
    Tc_day: float = 30.0             # C
    Tc_night: float = 20.0           # C
    pump_W: float = 30.0             # W
    eta_t: float = 0.80
    eta_p: float = 0.70
    eta_store: float = 0.80          # 0 = no storage
    superheat: float = 0.0           # K
    eta0: float = 0.75
    a1: float = 1.5
    a2: float = 0.005


def _flow_from_pump(pump_W: float, c: cy.CycleResult) -> float:
    return pump_W / 1000.0 / c.wp                    # kW / (kJ/kg) = kg/s


def steady_day_night(p: SteadyInputs) -> dict:
    cos_th = max(0.0, math.sin(math.radians(p.sun_elevation + p.tilt)))
    g_eff = p.dni * cos_th
    # the collector must run at the turbine-inlet temperature Te + superheat
    q_sol = collector_heat(g_eff, p.Te + p.superheat, p.T_amb, p.area, p.eta0, p.a1, p.a2)

    day = cy.solve_cycle(p.Te, p.Tc_day, p.superheat, p.eta_t, p.eta_p)
    m_pump = _flow_from_pump(p.pump_W, day)
    m_sun = q_sol / 1000.0 / day.qin
    m = min(m_pump, m_sun)
    q_req = m_pump * day.qin * 1000.0
    surplus = max(0.0, q_sol - q_req)

    out = dict(cos_theta=cos_th, G_eff=g_eff, Q_sol=q_sol, day=day,
               eta_collector=(q_sol / (p.area * g_eff) if g_eff > 0 else 0.0),
               m_pump=m_pump, m_sun=m_sun, m=m, Q_req=q_req, surplus=surplus,
               flow_limited_by="pump" if m_pump <= m_sun else "sunlight",
               W_turb=m * day.wt * 1000.0, W_pump=m * day.wp * 1000.0,
               W_out=m * day.wnet * 1000.0, Q_in=m * day.qin * 1000.0,
               Q_out=m * day.qout * 1000.0,
               carnot=day.carnot())
    out["eta_system"] = out["W_out"] / (g_eff * p.area) if g_eff > 0 else 0.0

    night, t_night, w_night, e_store, m_night = None, 0.0, 0.0, 0.0, 0.0
    if p.eta_store > 0 and surplus > 0:
        night = cy.solve_cycle(p.Te, p.Tc_night, p.superheat, p.eta_t, p.eta_p)
        m_night = _flow_from_pump(p.pump_W, night)
        q_night = m_night * night.qin * 1000.0
        e_store = p.eta_store * surplus * p.hours_sun              # Wh
        t_night = min(24.0 - p.hours_sun, e_store / q_night)
        w_night = m_night * night.wnet * 1000.0
    out.update(night=night, t_night=t_night, W_night=w_night, E_store=e_store, m_night=m_night)
    out["E_day"] = out["W_out"] * p.hours_sun
    out["E_night"] = w_night * t_night
    out["E_total"] = out["E_day"] + out["E_night"]
    denom = g_eff * p.area * p.hours_sun
    out["eta_daily"] = out["E_total"] / denom if denom > 0 else 0.0
    out["inputs"] = asdict(p)
    return out
