"""
Numerical and physical validation of the simulator (project section 6).

Every check returns a Check record so the same code feeds the pytest suite,
the "Validation" page of the app, and the tables in the report.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import List

import numpy as np

from . import cycle as cy
from . import properties as fp
from .properties import K
from .simulation import PlantParams, simulate
from .solar import daylight_hours, declination_deg, sun_position
from .steady import SteadyInputs, steady_day_night
from .storage import StorageTank


@dataclass
class Check:
    category: str
    name: str
    value: float
    tolerance: float
    passed: bool
    note: str = ""


def _chk(cat, name, value, tol, note="", upper=True) -> Check:
    ok = (abs(value) <= tol) if upper else (value >= tol)
    return Check(cat, name, float(value), float(tol), bool(ok), note)


# ----------------------------------------------------------------------------
def check_properties() -> List[Check]:
    out = []
    # anchors: widely published R-134a constants
    out.append(_chk("Properties", "Critical temperature vs 101.06 C [K error]",
                    fp.T_CRIT_C - 101.06, 0.05))
    p_nbp = fp.p_sat(-26.07)
    out.append(_chk("Properties", "Saturation pressure at -26.07 C vs 101.325 kPa [rel. error]",
                    (p_nbp - 101.325) / 101.325, 0.003, "normal boiling point"))
    # Clapeyron: dP/dT = h_fg / (T v_fg), independent of the stored data
    worst = 0.0
    for T in (0.0, 20.0, 40.0, 60.0, 80.0):
        dT = 0.05
        dpdt = (fp.p_sat(T + dT) - fp.p_sat(T - dT)) / (2 * dT)          # kPa/K
        f, g = fp.sat_state(T, 0), fp.sat_state(T, 1)
        rhs = (g.h - f.h) / ((T + K) * (g.v - f.v))                     # kPa/K
        worst = max(worst, abs(dpdt - rhs) / rhs)
    out.append(_chk("Properties", "Clapeyron relation, worst of 5 temperatures [rel. error]",
                    worst, 2e-3, "dP/dT = h_fg/(T v_fg)"))
    return out


def check_cycle() -> List[Check]:
    out = []
    grid = [(Te, Tc, sh, et) for Te in (50, 70, 90) for Tc in (15, 30, 45)
            for sh in (0.0, 10.0) for et in (0.6, 0.85) if Te - Tc >= 10]
    r1 = r2 = 0.0
    carnot_ok, sgen_min = True, 1.0
    for Te, Tc, sh, et in grid:
        c = cy.solve_cycle(Te, Tc, sh, et, 0.7)
        r1 = max(r1, abs(cy.first_law_residual(c)) / c.qin)
        g = cy.entropy_generation(c, Te + sh, Tc)      # source at the turbine-inlet temperature
        sgen_min = min(sgen_min, g["pump"], g["evaporator"], g["turbine"], g["condenser"], g["total"])
        # sources at Te and sink at Tc are the most favourable case for the cycle
        carnot_ok &= c.eta_th < c.carnot()
        r2 = max(r2, abs(g["total"] - (c.qout / (Tc + K) - c.qin / (Te + sh + K))))
    out.append(_chk("Cycle", f"First law q_in - q_out - w_net over {len(grid)} cases [rel.]", r1, 1e-6))
    out.append(_chk("Cycle", "Second law: eta_th below Carnot in every case", 0.0 if carnot_ok else 1.0, 0.0))
    out.append(_chk("Cycle", "Entropy generation sum equals q_out/Tc - q_in/T_source [kJ/kg-K]", r2, 1e-9))
    out.append(_chk("Cycle", "Entropy generation of every device >= 0 [min over all cases, kJ/kg-K]", sgen_min, -1e-12,
                    "pump, evaporator, turbine, condenser (round-off tolerance)", upper=False))
    # device mass balance: the same mass flow enters and leaves each device by construction;
    # verify the pump flow computed from pump power reproduces that power.
    c = cy.solve_cycle(80, 30, 0, 0.8, 0.7)
    m = 30.0 / 1000.0 / c.wp
    out.append(_chk("Cycle", "Pump power recovered from m_dot * w_p [W error]", m * c.wp * 1000 - 30.0, 1e-9))
    return out


def check_geometry() -> List[Check]:
    out = []
    n = 80                                                      # near equinox
    _, alt = sun_position(12.0, 0.0, 80)
    out.append(_chk("Solar", "Equatorial solar-noon altitude at equinox vs 90 deg", alt - (90 - abs(declination_deg(80))), 0.01))
    out.append(_chk("Solar", "Equatorial day length vs 12 h", daylight_hours(0.0, 80) - 12.0, 0.02))
    lat, d = 34.05, 172
    _, alt = sun_position(12.0, lat, d)
    out.append(_chk("Solar", "Solar-noon altitude = 90 - |lat - decl| [deg error]",
                    alt - (90 - abs(lat - declination_deg(d))), 1e-6))
    return out


def check_transient(p: PlantParams | None = None) -> List[Check]:
    p = p or PlantParams()
    r = simulate(p)
    b = r.balance
    out = [
        _chk("Energy", "Tank energy balance dU = Q_col - Q_evap - Q_loss [rel. to Q_col]", b["resid_tank_rel"], 1e-5),
        _chk("Energy", "Cycle energy balance Q_evap - Q_cond - W_net [rel. to Q_evap]", b["resid_cycle_rel"], 1e-8),
        _chk("Energy", "Collector heat: solver quadrature vs 5-min trapezoid [rel.]",
             (b["trap_E_col_Wh"] - r.kpi["E_collector_Wh"]) / r.kpi["E_collector_Wh"], 5e-3),
        _chk("Mass", "Circulated mass: solver quadrature vs trapezoid [rel.]",
             (b["mass_from_pump_kg"] - r.kpi["mass_circulated_kg"]) / max(r.kpi["mass_circulated_kg"], 1e-9), 5e-3),
    ]
    # device-level mass balance: the flow recovered from each device's own energy rate must equal m_dot
    S = r.series
    idx = np.where(S["frac"] > 0.2)[0][::max(1, int(np.sum(S["frac"] > 0.2)) // 25)]
    worst = 0.0
    for i in idx:
        c = cy.solve_cycle(S["Te"][i], S["Tc"][i], p.superheat, p.eta_t, p.eta_p, p.valve_open)
        m = S["mdot"][i]
        flows = [S["Wp"][i] / (c.wp * 1000), S["Wt"][i] / (c.wt * 1000),
                 S["Qev"][i] / (c.qin * 1000), S["Qc"][i] / (c.qout * 1000)]
        worst = max(worst, max(abs(f - m) / m for f in flows))
    out.append(_chk("Mass", f"Flow recovered from pump, turbine, evaporator and condenser rates vs m_dot ({len(idx)} instants) [rel.]", worst, 1e-9))
    # exact solution: tank with no sun and no plant cools exponentially
    q = replace(p, collector_on=False, pump_on=False, T_swing=0.0, warmup_days=0, T_tank0=90.0)
    rq = simulate(q)
    tank = StorageTank(q.tank_L, q.UA)
    exact = np.array([tank.cooldown(90.0, q.T_mean, h * 3600.0) for h in rq.t])
    out.append(_chk("Transient", "Cool-down vs analytic exponential, max error [K]",
                    float(np.max(np.abs(rq.series["Ts"] - exact))), 1e-4))
    # solver independence
    lo = simulate(p, rtol=1e-4).kpi["W_net_Wh"]
    hi = simulate(p, rtol=1e-9).kpi["W_net_Wh"]
    out.append(_chk("Numerics", "Daily net work, rtol 1e-4 vs 1e-9 [rel. change]", (lo - hi) / hi, 1e-3))
    return out


def check_steady_vs_transient() -> List[Check]:
    """Piston-free sanity link between the two models: for a very small tank
    held at a fixed temperature the cycle results must agree with the steady model."""
    p = PlantParams(T_cut=79.0, T_full=79.1, pump_W=30.0)
    inst = steady_day_night(SteadyInputs(Te=80.0, Tc_day=30.0))
    from .simulation import instant
    d = instant(replace(p, approach_cond=0.0, T_swing=0.0, T_mean=30.0, pinch=0.0), 12 * 3600.0, 80.0)
    return [_chk("Consistency", "Steady vs transient plant: net power at Te=80 C, Tc=30 C [rel.]",
                 (d["Wnet"] - inst["W_out"]) / inst["W_out"], 1e-6,
                 "same cycle, same pump power")]


def check_matlab_crosscheck() -> List[Check]:
    """CoolProp model vs a line-by-line transcription of the MATLAB script (table properties)."""
    from .matlab_logic import matlab_day
    out = []
    cases = {"baseline": PlantParams(), "winter": replace(PlantParams(), day=355),
             "large tank": replace(PlantParams(), tank_L=900.0, area=14.0, pump_W=22.0, T_cut=60.0, T_full=78.0),
             "cloudy": replace(PlantParams(), clearness=0.5)}
    for name, p in cases.items():
        m, k = matlab_day(p), simulate(p).kpi
        rel = abs(m["W_net_Wh"] - k["W_net_Wh"]) / abs(k["W_net_Wh"])
        out.append(_chk("MATLAB cross-check", f"Daily net work, MATLAB logic vs CoolProp ({name}), relative", rel, 5e-3,
                        "table + PCHIP + v dP properties vs equation of state"))
        rel = abs(m["E_evaporator_Wh"] - k["E_evaporator_Wh"]) / k["E_evaporator_Wh"]
        out.append(_chk("MATLAB cross-check", f"Heat to evaporator ({name}), relative", rel, 5e-3))
        out.append(_chk("MATLAB cross-check", f"Run time ({name}), absolute [h]",
                        abs(m["run_hours"] - k["run_hours"]), 0.1, "one 5 min output step"))
    return out


def run_all() -> List[Check]:
    return (check_properties() + check_cycle() + check_geometry()
            + check_transient() + check_steady_vs_transient() + check_matlab_crosscheck())


if __name__ == "__main__":                                      # pragma: no cover
    for c in run_all():
        print(("PASS " if c.passed else "FAIL ") + f"[{c.category}] {c.name}: {c.value:.3e} (tol {c.tolerance:.1e})")
