"""
Fluid property layer for the Solar Rankine Lab.

Working fluid: R-134a (tetrafluoroethane, "Freon"), evaluated with CoolProp's
Helmholtz-energy equation of state. ASHRAE reference state is used
(h = s = 0 for saturated liquid at -40 C), which is the reference of the
property tables in most thermodynamics textbooks.

Units used everywhere in the project
    T  [C]       P [kPa]      h [kJ/kg]     s [kJ/kg-K]     v [m^3/kg]
Heat and work rates are in W unless stated; energies in J or Wh.

CoolProp AbstractState objects are not thread safe, so each thread (Streamlit
runs every session in its own thread) gets its own instance.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

import CoolProp
import CoolProp.CoolProp as CP
from CoolProp.CoolProp import AbstractState

FLUID = "R134a"
CP.set_reference_state(FLUID, "ASHRAE")

K = 273.15                                   # C -> K offset
T_CRIT_C = CP.PropsSI("Tcrit", FLUID) - K    # about 101.1 C
P_CRIT_KPA = CP.PropsSI("pcrit", FLUID) / 1e3

_local = threading.local()


def _as() -> AbstractState:
    """Return this thread's AbstractState (created on first use)."""
    st = getattr(_local, "state", None)
    if st is None:
        st = AbstractState("HEOS", FLUID)
        _local.state = st
    return st


@dataclass(frozen=True)
class State:
    """Thermodynamic state point of R-134a."""
    T: float                 # C
    P: float                 # kPa
    h: float                 # kJ/kg
    s: float                 # kJ/kg-K
    v: float                 # m^3/kg
    x: Optional[float]       # quality, None when single phase
    phase: str               # 'liquid', 'two-phase', 'vapor'


def _snapshot(a: AbstractState) -> State:
    """Read all properties from the AbstractState after an update call."""
    ph = a.phase()
    if ph == CoolProp.iphase_twophase:
        x, phase = a.Q(), "two-phase"
    elif ph in (CoolProp.iphase_liquid, CoolProp.iphase_supercritical_liquid):
        x, phase = None, "liquid"
    else:
        x, phase = None, "vapor"
    return State(T=a.T() - K, P=a.p() / 1e3, h=a.hmass() / 1e3,
                 s=a.smass() / 1e3, v=1.0 / a.rhomass(), x=x, phase=phase)


def sat_state(T_C: float, quality: float) -> State:
    """Saturated state at temperature T_C; quality 0 = liquid, 1 = vapor."""
    a = _as()
    a.update(CoolProp.QT_INPUTS, quality, T_C + K)
    st = _snapshot(a)
    # a saturated state is reported as two-phase; label by the end it sits on
    phase = "liquid" if quality <= 0 else "vapor" if quality >= 1 else "two-phase"
    return State(st.T, st.P, st.h, st.s, st.v, quality, phase)


def p_sat(T_C: float) -> float:
    """Saturation pressure [kPa] at T_C."""
    a = _as()
    a.update(CoolProp.QT_INPUTS, 0.0, T_C + K)
    return a.p() / 1e3


def state_PT(P_kPa: float, T_C: float) -> State:
    a = _as()
    a.update(CoolProp.PT_INPUTS, P_kPa * 1e3, T_C + K)
    return _snapshot(a)


def state_Ph(P_kPa: float, h: float) -> State:
    a = _as()
    a.update(CoolProp.HmassP_INPUTS, h * 1e3, P_kPa * 1e3)
    return _snapshot(a)


def state_Ps(P_kPa: float, s: float) -> State:
    a = _as()
    a.update(CoolProp.PSmass_INPUTS, P_kPa * 1e3, s * 1e3)
    return _snapshot(a)


def saturation_dome(T_min: float = 0.0, T_max: float = 100.0, n: int = 51):
    """Return (T, s_liquid, s_vapor) arrays for drawing the T-s dome."""
    import numpy as np
    T = np.linspace(T_min, T_max, n)
    sf = [sat_state(t, 0).s for t in T]
    sg = [sat_state(t, 1).s for t in T]
    # close the dome at the critical point
    return T, np.array(sf), np.array(sg)
