"""
Plant model v2: transient (optionally stratified) storage tank, sun-tracking or
fixed collector, and a Rankine cycle held at user set points.

Layout
    sun -> collector -> tank (N layers) -> evaporator (R-134a) -> turbine
                         ^                     |                       |
                         +-- collector loop    +-- pump <- condenser <-+

Tank (transient control volume, N layers, layer 1 = top)
    Basic    N = 1  : uniform temperature (lumped model).
    Engineer N = 10 : stratified. The collector loop draws from the bottom and
                      returns at the top; the evaporator draws hot water from
                      the top and returns it, cooled to Te + pinch, at the
                      bottom. The net flow between layers carries energy up or
                      down; a small conduction/mixing conductance couples
                      neighbours and a large one mixes any layer that is colder
                      than the layer below it (no stable inversions).
    Energy of layer i (mass M/N):
        (M/N) cp dT_i/dt = flow terms + mixing - UA_i (T_i - T_amb)
    For N = 1 this reduces exactly to C dT/dt = Q_col - Q_evap - UA (T - T_amb).

Collector
    Tracking (Basic, optional in Engineer): the aperture always faces the sun,
    so cos(theta) = 1 while the sun is up. Fixed (Engineer): south-facing at a
    chosen tilt, cos(theta) from the solar geometry.
    Q_col = A [eta0 G cos(theta) - a1 dT - a2 dT^2],  dT = T_inlet - T_amb,
    tapered to zero as the top of the tank reaches the defocus temperature.

Cycle (steady-flow devices, quasi-steady)
    Evaporating temperature Te is a set point (constant boiler pressure);
    superheat SH heats the vapour to Te + SH. The plant can only run while the
    top of the tank is at least Te + SH + pinch: the start temperature set by
    the user must respect that.
    Condensing temperature Tc is a set point, but an air-cooled condenser needs
    the air at least 3 K colder: Tc = max(Tc_set, T_amb + 3) (the condenser
    "floats" up on hot afternoons, which raises the back pressure).
    Pump input power sets the mass flow, m = f W_pump / w_p, with f ramping
    from 0 to 1 over the 3 K above the start temperature.

Time
    The run starts at sunrise with the scenario's tank temperature and lasts
    48 h (two identical days of weather). The scored day is the first 24 h;
    the survival window is the 24 h that follow the first start-up.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace, asdict
from functools import lru_cache
from typing import Dict

import numpy as np
from scipy.integrate import solve_ivp

from . import cycle as cy
from . import solar
from .properties import K
from .scenarios import Scenario, BASIC_EFF

CP_W = 4186.0          # J/kg-K, water
K_INS = 0.025          # W/m-K, polyurethane foam
H_OUT = 10.0           # W/m^2-K, outside air film
PINCH = 5.0            # K, evaporator pinch
COND_APPROACH = 3.0    # K, minimum condenser-to-air difference
MIN_LIFT = 6.0         # K, minimum Te - Tc for the turbine to run
RAMP = 3.0             # K above the start temperature for full flow
TE_MAX = 95.0          # C, stay clear of the R-134a critical point (101 C)
M_COL = 0.015          # kg/s per m^2, collector-loop water flow
G_MIX = 2.0            # W/K, conduction and mixing between layers
G_INV = 200.0          # W/K per K of inversion, buoyant mixing
INSULATION_LEVELS = {"poor": 1.0, "standard": 5.0, "good": 10.0}   # cm of foam
HOURS = 48.0


@dataclass(frozen=True)
class PlantConfig:
    difficulty: str = "basic"            # 'basic' or 'engineer'
    # collector
    area: float = 8.0                    # m^2
    T_max: float = 95.0                  # C, defocus temperature (top of tank)
    tracking: bool = True
    tilt: float = 30.0                   # deg, used when tracking is off
    eta0: float = 0.75
    a1: float = 1.5
    a2: float = 0.005
    # tank
    tank_L: float = 500.0
    insulation: str = "standard"         # Basic level
    ins_cm: float = 5.0                  # Engineer thickness, cm
    # cycle
    Te: float = 75.0                     # evaporating temperature set point, C
    Tc: float = 30.0                     # condensing temperature set point, C
    superheat: float = 0.0               # K (Engineer only)
    T_start: float = 82.0                # tank-top temperature at which the plant starts, C
    pump_W: float = 30.0                 # electrical pump input at full flow, W
    eta_t: float = 0.80
    eta_p: float = 0.70
    # switches (sandbox)
    pump_on: bool = True
    valve_open: bool = True
    collector_on: bool = True

    @property
    def layers(self) -> int:
        return 10 if self.difficulty == "engineer" else 1

    @property
    def thickness_cm(self) -> float:
        return self.ins_cm if self.difficulty == "engineer" else INSULATION_LEVELS[self.insulation]


def basic_lock(c: PlantConfig) -> PlantConfig:
    """Apply the Basic-mode fixed values."""
    if c.difficulty != "basic":
        return c
    return replace(c, tracking=True, superheat=0.0, **BASIC_EFF)


# --------------------------------------------------------------------------
# tank geometry and losses
# --------------------------------------------------------------------------
def tank_geometry(volume_L: float):
    """Cylinder with height = 2 x diameter. Returns D, H, side area, one end area [m, m^2]."""
    V = volume_L / 1000.0
    D = (2.0 * V / math.pi) ** (1.0 / 3.0)
    H = 2.0 * D
    return D, H, math.pi * D * H, math.pi * D * D / 4.0


def tank_U(thickness_cm: float) -> float:
    """Overall loss coefficient through foam plus the outside air film [W/m^2-K]."""
    return 1.0 / (thickness_cm / 100.0 / K_INS + 1.0 / H_OUT)


def tank_UA(volume_L: float, thickness_cm: float) -> float:
    D, H, A_side, A_end = tank_geometry(volume_L)
    return tank_U(thickness_cm) * (A_side + 2.0 * A_end)


def layer_UA(volume_L: float, thickness_cm: float, n: int):
    D, H, A_side, A_end = tank_geometry(volume_L)
    U = tank_U(thickness_cm)
    ua = [U * A_side / n for _ in range(n)]
    ua[0] += U * A_end
    ua[-1] += U * A_end
    return ua


# --------------------------------------------------------------------------
# cycle at fixed set points (cached: Te is fixed, Tc changes only when floating)
# --------------------------------------------------------------------------
@lru_cache(maxsize=4096)
def _cycle(Te: float, Tc: float, sh: float, eta_t: float, eta_p: float, valve: bool):
    return cy.solve_cycle(Te, Tc, sh, eta_t, eta_p, valve)


def cycle_at(c: PlantConfig, Tc: float):
    return _cycle(round(c.Te, 6), round(Tc, 4), round(c.superheat, 6), c.eta_t, c.eta_p, c.valve_open)


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def weather(sc: Scenario, clock: float, c: PlantConfig):
    sin_alt, alt = solar.sun_position(clock, sc.lat, sc.day)
    dni = solar.beam_irradiance(sin_alt, sc.day, sc.clearness)
    if c.tracking:
        cos_i = 1.0 if sin_alt > 0 else 0.0
    else:
        cos_i = solar.cos_incidence(clock, sc.lat, sc.day, c.tilt)
    Ta = solar.ambient_temperature(clock, sc.T_mean, sc.T_swing)
    return alt, dni, cos_i, Ta


def instant(c: PlantConfig, sc: Scenario, t_s: float, T: np.ndarray) -> dict:
    """Instantaneous plant state for time t_s (s after sunrise) and layer temperatures T."""
    n = len(T)
    clock = (sc.sunrise + t_s / 3600.0) % 24.0
    alt, dni, cos_i, Ta = weather(sc, clock, c)
    G = dni * cos_i
    T_top, T_bot = T[0], T[-1]
    taper = _clip01((c.T_max - T_top) / 3.0)
    Qcol = 0.0
    if c.collector_on:
        Qcol = solar.collector_heat(G, T_bot, Ta, c.area, c.eta0, c.a1, c.a2) * taper
    Tc = max(c.Tc, Ta + COND_APPROACH)
    frac = 0.0
    if c.pump_on:
        frac = _clip01((T_top - c.T_start) / RAMP)
        frac *= _clip01((T_top - (c.Te + c.superheat + PINCH)) / 1.0)
        frac *= _clip01((c.Te - Tc - MIN_LIFT) / 2.0)
    out = dict(clock=clock, alt=alt, dni=dni, cos_i=cos_i, G=G, Ta=Ta, T_top=T_top, T_bot=T_bot,
               T_avg=float(np.mean(T)), Tc=Tc, Qcol=Qcol, frac=frac, mdot=0.0, Qev=0.0, Qc=0.0,
               Wt=0.0, Wp=0.0, Wnet=0.0, Ex=0.0, Pe=float("nan"), Pc=float("nan"),
               x4=float("nan"), eta_th=0.0, floating=Tc > c.Tc + 1e-9)
    if frac > 0.0:
        cyc = cycle_at(c, Tc)
        m = frac * c.pump_W / 1000.0 / cyc.wp
        Qev = m * cyc.qin * 1000.0
        out.update(mdot=m, Qev=Qev, Qc=m * cyc.qout * 1000.0, Wt=m * cyc.wt * 1000.0,
                   Wp=m * cyc.wp * 1000.0, Wnet=m * cyc.wnet * 1000.0, Pe=cyc.Pe, Pc=cyc.Pc,
                   x4=(cyc.x4 if cyc.x4 is not None else 1.0), eta_th=cyc.eta_th)
        out["Ex"] = Qev * (1.0 - (Ta + K) / (T_top + K))
    return out


def _rhs(c: PlantConfig, sc: Scenario, n: int, Mi: float, ua: list):
    T_ret_set = c.Te + PINCH

    def f(t, y):
        T = y[:n]
        d = instant(c, sc, t, T)
        Qcol, Qev, Ta = d["Qcol"], d["Qev"], d["Ta"]
        mc = M_COL * c.area * _clip01(Qcol / 20.0)
        Tco = T[-1] + (Qcol / (mc * CP_W) if mc > 0 else 0.0)
        dT_ev = max(T[0] - T_ret_set, 2.0)
        me = Qev / (CP_W * dT_ev)
        Tret = T[0] - dT_ev
        F = mc - me                                    # net downward flow between layers
        dT = np.zeros(n)
        loss = 0.0
        for i in range(n):
            q = 0.0
            if i == 0:
                q += mc * CP_W * (Tco - T[0])
            if i == n - 1:
                q += me * CP_W * (Tret - T[-1])
            if i > 0 and F > 0:
                q += F * CP_W * (T[i - 1] - T[i])
            if i < n - 1 and F < 0:
                q += -F * CP_W * (T[i + 1] - T[i])
            if i > 0:                                  # mixing with the layer above
                g = G_MIX + G_INV * max(0.0, T[i] - T[i - 1])
                q += g * (T[i - 1] - T[i])
            if i < n - 1:                              # mixing with the layer below
                g = G_MIX + G_INV * max(0.0, T[i + 1] - T[i])
                q += g * (T[i + 1] - T[i])
            ql = ua[i] * (T[i] - Ta)
            loss += ql
            dT[i] = (q - ql) / (Mi * CP_W)
        return np.concatenate([dT, [d["G"] * c.area, Qcol, Qev, loss, d["Wt"], d["Wp"],
                                    d["Qc"], d["Ex"], d["mdot"]]])
    return f


@dataclass
class PlantResult:
    config: PlantConfig
    scenario: Scenario
    t: np.ndarray                      # hours after sunrise, 0..48
    clock: np.ndarray                  # solar clock time, h
    series: Dict[str, np.ndarray]
    layers: np.ndarray                 # (n_layers, n_times) tank temperatures
    kpi: Dict[str, float]              # first 24 h (the scored day)
    survive: Dict[str, float]
    balance: Dict[str, float]

    def to_dict(self) -> dict:
        return dict(kpi=self.kpi, survive=self.survive, balance=self.balance)


def _window(th, S, Y, a, b, wh, run_mask):
    """Daily totals between hours a and b (after sunrise) from the quadrature states."""
    i0 = int(np.searchsorted(th, a - 1e-9))
    i1 = int(np.searchsorted(th, b + 1e-9)) - 1
    D = Y[:, i1] - Y[:, i0]
    return i0, i1, D


@lru_cache(maxsize=256)
def simulate(c: PlantConfig, sc: Scenario, rtol: float = 1e-6, step_min: float = 5.0) -> PlantResult:
    c = basic_lock(c)
    n = c.layers
    M = c.tank_L * 1.0
    Mi = M / n
    ua = layer_UA(c.tank_L, c.thickness_cm, n)
    t_end = HOURS * 3600.0
    t_eval = np.arange(0.0, t_end + 1.0, step_min * 60.0)
    y0 = np.concatenate([np.full(n, sc.T_tank0), np.zeros(9)])
    atol = np.concatenate([np.full(n, 1e-6), [1e-3] * 8, [1e-9]])
    sol = solve_ivp(_rhs(c, sc, n, Mi, ua), (0.0, t_end), y0, method="RK45", rtol=rtol,
                    atol=atol, max_step=300.0, t_eval=t_eval)
    if not sol.success:
        raise RuntimeError(sol.message)
    th = sol.t / 3600.0
    keys = ["clock", "alt", "dni", "cos_i", "G", "Ta", "T_top", "T_bot", "T_avg", "Tc", "Qcol",
            "frac", "mdot", "Qev", "Qc", "Wt", "Wp", "Wnet", "Pe", "Pc", "x4", "eta_th"]
    S = {k: np.zeros(th.size) for k in keys}
    for i in range(th.size):
        d = instant(c, sc, sol.t[i], sol.y[:n, i])
        for k in keys:
            S[k][i] = d[k]
    L = sol.y[:n, :]
    Y = sol.y[n:, :]
    ua_tot = sum(ua)
    S["Qloss"] = np.array([float(np.dot(ua, L[:, i] - S["Ta"][i])) for i in range(th.size)])
    S["E_tank_kWh"] = (Mi * CP_W * (L - L[:, :1]).sum(axis=0)) / 3.6e6     # stored relative to the start
    S["Q_store"] = S["Qcol"] - S["Qev"] - S["Qloss"]                        # charge (+) / discharge (-) rate, W

    wh = 1.0 / 3600.0
    running = S["frac"] > 0.05
    night = S["alt"] <= 0.0
    dt_h = np.gradient(th) if th.size > 1 else np.ones(1)

    def totals(a, b):
        i0 = int(np.searchsorted(th, a - 1e-9))
        i1 = int(np.searchsorted(th, b + 1e-9)) - 1
        D = (Y[:, i1] - Y[:, i0]) * wh
        sl = slice(i0, i1 + 1)
        w = dt_h[sl].copy()
        w[0] *= 0.5
        w[-1] *= 0.5
        run, nt = running[sl], night[sl]
        E_in, E_col, E_ev, E_loss, Wt, Wp, Qc, Ex, mass = D
        Wn = Wt - Wp
        dU = Mi * CP_W * float((L[:, i1] - L[:, i0]).sum()) * wh
        after_sunset = nt & (th[sl] > 1.0)               # night after the first sunset
        e_night = float(np.trapezoid(np.where(after_sunset, S["Wnet"][sl], 0.0), th[sl]))
        return dict(
            E_incident_Wh=E_in, E_collector_Wh=E_col, E_evaporator_Wh=E_ev, E_loss_Wh=E_loss,
            W_turbine_Wh=Wt, W_pump_Wh=Wp, W_net_Wh=Wn, Q_condenser_Wh=Qc, dU_tank_Wh=dU,
            eta_collector=E_col / E_in if E_in > 0 else 0.0,
            eta_cycle=Wn / E_ev if E_ev > 0 else 0.0,
            eta_daily=Wn / E_in if E_in > 0 else 0.0,
            eta_II=Wn / Ex if Ex > 0 else 0.0,
            run_hours=float(np.sum(w[run])), night_run_hours=float(np.sum(w[run & after_sunset])),
            W_after_sunset_Wh=e_night,
            peak_W_net=float(S["Wnet"][sl].max()), Ts_max=float(L[:, sl].max()), Ts_min=float(L[:, sl].min()),
            x4_min=float(np.nanmin(S["x4"][sl][run])) if run.any() else float("nan"),
            Pe_max=float(np.nanmax(S["Pe"][sl][run])) if run.any() else float("nan"),
            float_hours=float(np.sum(w[(S["Tc"][sl] > c.Tc + 1e-6) & run])),
            defocus_hours=float(np.sum(w[L[0, sl] > c.T_max - 1.0])),
            mass_kg=mass,
            resid_tank_Wh=dU - (E_col - E_ev - E_loss), resid_cycle_Wh=E_ev - Qc - Wn,
        )

    kpi = totals(0.0, 24.0)
    # survival: 24 h of positive net power after the first start-up
    starts = np.nonzero(running & (th <= 24.0))[0]
    if starts.size:
        ts = th[starts[0]]
        win = (th >= ts) & (th <= ts + 24.0)
        ok = bool(np.all(S["Wnet"][win] > 0.0)) and ts + 24.0 <= HOURS
        survive = dict(start_h=float(ts), passed=ok, **{f"w_{k}": v for k, v in totals(ts, ts + 24.0).items()
                                                        if k in ("W_net_Wh", "peak_W_net", "eta_cycle")})
        bad = np.nonzero(win & (S["Wnet"] <= 0.0))[0]
        survive["fail_h"] = float(th[bad[0]]) if bad.size else float("nan")
    else:
        survive = dict(start_h=float("nan"), passed=False, w_W_net_Wh=0.0, w_peak_W_net=0.0,
                       w_eta_cycle=0.0, fail_h=float("nan"))
    bal = dict(resid_tank_Wh=kpi["resid_tank_Wh"], resid_cycle_Wh=kpi["resid_cycle_Wh"],
               resid_tank_rel=abs(kpi["resid_tank_Wh"]) / max(kpi["E_collector_Wh"], 1e-9),
               resid_cycle_rel=abs(kpi["resid_cycle_Wh"]) / max(kpi["E_evaporator_Wh"], 1e-9),
               UA=ua_tot, layers=n)
    return PlantResult(c, sc, th, S["clock"], S, L, kpi, survive, bal)
