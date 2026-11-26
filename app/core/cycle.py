"""
Steady-state, steady-flow (SSSF) models of the four Rankine-cycle devices and
the complete cycle.

State numbering follows Borgnakke & Sonntag:
    1  saturated liquid leaving the condenser (pump inlet)
    2  compressed liquid leaving the pump (evaporator inlet)
    3  vapor leaving the evaporator (turbine inlet), saturated or superheated
    4  turbine exhaust (condenser inlet)

Each device is analysed per kilogram of working fluid with the steady-flow
first law (kinetic and potential energy neglected):
    pump         w_p  = (h2s - h1) / eta_p
    evaporator   q_in = h3 - h2
    turbine      w_t  = eta_t (h3 - h4s)
    condenser    q_out = h4 - h1
and the second law (entropy generation) for every device.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import properties as fp
from .properties import K, State


@dataclass(frozen=True)
class CycleResult:
    s1: State
    s2: State
    s3: State
    s4: State
    Te: float            # evaporating (saturation) temperature, C
    Tc: float            # condensing temperature, C
    superheat: float     # K above Te at turbine inlet
    eta_t: float
    eta_p: float
    valve_open: bool     # False = turbine isolated, flow throttled through bypass
    wp: float            # pump work, kJ/kg
    wt: float            # turbine work, kJ/kg
    qin: float           # heat added, kJ/kg
    qout: float          # heat rejected, kJ/kg

    @property
    def wnet(self) -> float:
        return self.wt - self.wp

    @property
    def eta_th(self) -> float:
        return self.wnet / self.qin

    @property
    def x4(self):
        """Turbine exit quality; None when the exhaust is superheated."""
        return self.s4.x

    @property
    def Pe(self) -> float:
        return self.s3.P

    @property
    def Pc(self) -> float:
        return self.s1.P

    def carnot(self, T_hot_C=None, T_cold_C=None) -> float:
        th = (self.Te if T_hot_C is None else T_hot_C) + K
        tc = (self.Tc if T_cold_C is None else T_cold_C) + K
        return 1.0 - tc / th


# --------------------------------------------------------------------------
# individual devices
# --------------------------------------------------------------------------
def pump(s1: State, P_out: float, eta_p: float):
    """Liquid pump. Returns (state 2, specific work kJ/kg)."""
    h2s = fp.state_Ps(P_out, s1.s).h            # isentropic compression
    wp = (h2s - s1.h) / eta_p
    return fp.state_Ph(P_out, s1.h + wp), wp


def evaporator(s2: State, Te: float, superheat: float):
    """Boiler at constant pressure. Returns (state 3, heat kJ/kg)."""
    if superheat > 0.0:
        s3 = fp.state_PT(s2.P, Te + superheat)
    else:
        s3 = fp.sat_state(Te, 1.0)
    return s3, s3.h - s2.h


def turbine(s3: State, P_out: float, eta_t: float, valve_open: bool = True):
    """Turbine, or an isenthalpic throttle when the turbine valve is closed."""
    if not valve_open:
        return fp.state_Ph(P_out, s3.h), 0.0
    h4s = fp.state_Ps(P_out, s3.s).h
    wt = eta_t * (s3.h - h4s)
    return fp.state_Ph(P_out, s3.h - wt), wt


def condenser(s4: State, Tc: float):
    """Condenser to saturated liquid. Returns (state 1, heat rejected kJ/kg)."""
    s1 = fp.sat_state(Tc, 0.0)
    return s1, s4.h - s1.h


# --------------------------------------------------------------------------
# complete cycle
# --------------------------------------------------------------------------
def solve_cycle(Te: float, Tc: float, superheat: float = 0.0, eta_t: float = 0.80,
                eta_p: float = 0.70, valve_open: bool = True) -> CycleResult:
    """Solve the Rankine cycle for the given operating conditions."""
    if Te - Tc < 3.0:
        raise ValueError("Evaporator temperature must exceed condenser temperature by 3 K.")
    if Te > fp.T_CRIT_C - 3.0:
        raise ValueError("Evaporator temperature too close to the critical point.")
    s1 = fp.sat_state(Tc, 0.0)
    s2, wp = pump(s1, fp.p_sat(Te), eta_p)
    s3, qin = evaporator(s2, Te, superheat)
    s4, wt = turbine(s3, s1.P, eta_t, valve_open)
    s1b, qout = condenser(s4, Tc)
    return CycleResult(s1b, s2, s3, s4, Te, Tc, superheat, eta_t, eta_p,
                       valve_open, wp, wt, qin, qout)


def entropy_generation(c: CycleResult, T_source_C: float, T_sink_C: float) -> dict:
    """Entropy generation per kg for each device [kJ/kg-K].

    T_source_C is the temperature of the heat source feeding the evaporator
    (the storage tank) and T_sink_C the ambient air that receives the
    condenser heat.
    """
    Ts, Ta = T_source_C + K, T_sink_C + K
    g = {
        "pump": c.s2.s - c.s1.s,
        "evaporator": (c.s3.s - c.s2.s) - c.qin / Ts,
        "turbine": c.s4.s - c.s3.s,
        "condenser": (c.s1.s - c.s4.s) + c.qout / Ta,
    }
    g["total"] = sum(g.values())
    return g


def second_law_efficiency(c: CycleResult, T_source_C: float, T0_C: float) -> float:
    """Net work divided by the exergy of the heat drawn from the source."""
    return c.wnet / (c.qin * (1.0 - (T0_C + K) / (T_source_C + K)))


def first_law_residual(c: CycleResult) -> float:
    """q_in - q_out - w_net for one kilogram; zero for a closed cycle."""
    return c.qin - c.qout - c.wnet
