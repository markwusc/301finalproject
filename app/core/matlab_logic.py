"""
Line-by-line Python transcription of the MATLAB companion script's transient mode.

Purpose: MATLAB is not available in every environment, so this module re-implements
exactly what matlab/solar_rankine_R134a.m does (saturation-table properties read from the
.m file itself, PCHIP interpolation, pump work v1*dP/eta_p, plain-MATLAB solar equations,
ode45-equivalent Dormand-Prince integration) and lets the CoolProp-based model be compared
with it. Agreement shows that the two programs use the same equations and that the
table-based properties are adequate. It is a cross-check of the logic, not a substitute
for running the script in MATLAB.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import PchipInterpolator

from .simulation import PlantParams

MFILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "matlab", "solar_rankine_R134a.m")


@lru_cache(maxsize=1)
def load_table(path: str = MFILE):
    """Parse the D = [ ... ]; block of loadR134aTable() in the .m file."""
    txt = open(path, encoding="utf-8").read()
    body = txt.split("function tab = loadR134aTable()")[1]
    block = body.split("D = [")[1].split("];")[0]
    rows = [[float(x) for x in ln.replace(";", " ").split()] for ln in block.strip().splitlines() if ln.strip()]
    D = np.array(rows)
    T = D[:, 0]
    return {"T": T, "P": PchipInterpolator(T, np.log(D[:, 1])), "vf": PchipInterpolator(T, D[:, 2]),
            "hf": PchipInterpolator(T, D[:, 3]), "hg": PchipInterpolator(T, D[:, 4]),
            "sf": PchipInterpolator(T, D[:, 5]), "sg": PchipInterpolator(T, D[:, 6])}


def sat(name, T):
    tab = load_table()
    v = float(tab[name](T))
    return math.exp(v) if name == "P" else v


def rankine_cycle(Te, Tc, eta_t, eta_p, valve_open=True):
    Pe, Pc = sat("P", Te), sat("P", Tc)
    h1, v1 = sat("hf", Tc), sat("vf", Tc)
    wp = v1 * (Pe - Pc) / eta_p
    h2 = h1 + wp
    h3, s3 = sat("hg", Te), sat("sg", Te)
    sfc, sgc, hgc = sat("sf", Tc), sat("sg", Tc), sat("hg", Tc)
    x4s = (s3 - sfc) / (sgc - sfc)
    h4s = h1 + x4s * (hgc - h1)
    wt = eta_t * (h3 - h4s) if valve_open else 0.0
    h4 = h3 - wt
    return dict(Pe=Pe, Pc=Pc, h1=h1, wp=wp, h2=h2, h3=h3, h4=h4, wt=wt, x4=(h4 - h1) / (hgc - h1),
                qin=h3 - h2, wnet=wt - wp, eta=(wt - wp) / (h3 - h2))


def _clip01(x):
    return min(max(x, 0.0), 1.0)


def _sind(x): return math.sin(math.radians(x))
def _cosd(x): return math.cos(math.radians(x))


def _hemi(lat, dec):
    return (-lat, -dec) if lat < 0 else (lat, dec)


def plant_instant(P: PlantParams, t, Ts):
    hour = (t / 3600.0) % 24.0
    phi, dec = _hemi(P.lat, 23.45 * _sind(360 * (284 + P.day) / 365))
    w = 15 * (hour - 12)
    sin_alt = max(-1.0, min(1.0, _sind(phi) * _sind(dec) + _cosd(phi) * _cosd(dec) * _cosd(w)))
    alt = math.degrees(math.asin(sin_alt))
    if sin_alt <= 0:
        dni = 0.0
    else:
        am = 1 / max(sin_alt, 0.02)
        e0 = 1 + 0.033 * _cosd(360 * P.day / 365)
        dni = P.clearness * 1353 * e0 * 0.7 ** (am ** 0.678) * min(1.0, sin_alt / _sind(3))
    cos_i = max(0.0, _sind(dec) * _sind(phi - P.tilt) + _cosd(dec) * _cosd(phi - P.tilt) * _cosd(w))
    Geff = dni * cos_i
    Ta = P.T_mean + 0.5 * P.T_swing * math.cos(2 * math.pi * (hour - 15) / 24)
    taper = _clip01((P.T_max - Ts) / 5)
    if P.collector_on:
        dT = Ts - Ta
        Qcol = P.area * max(0.0, P.eta0 * Geff - P.a1 * dT - P.a2 * dT * dT) * taper
    else:
        Qcol = 0.0
    Qloss = P.UA * (Ts - Ta)
    Te = min(Ts - P.pinch, 95.0)
    Tc = max(Ta + P.approach_cond, 1.0)
    frac = _clip01((Ts - P.T_cut) / max(P.T_full - P.T_cut, 1e-6)) if P.pump_on else 0.0
    frac *= _clip01((Te - Tc - 6) / 4)
    d = dict(hour=hour, alt=alt, Geff=Geff, Ta=Ta, Ts=Ts, Qcol=Qcol, Qloss=Qloss, frac=frac,
             mdot=0.0, Qev=0.0, Qc=0.0, Wt=0.0, Wp=0.0, Wnet=0.0, Ex=0.0, x4=float("nan"))
    if frac > 0:
        c = rankine_cycle(Te, Tc, P.eta_t, P.eta_p, P.valve_open)
        m = frac * P.pump_W / 1000 / c["wp"]
        d.update(mdot=m, Qev=m * c["qin"] * 1000, Qc=m * (c["h4"] - c["h1"]) * 1000,
                 Wt=m * c["wt"] * 1000, Wp=m * c["wp"] * 1000, x4=min(c["x4"], 1.0))
        d["Wnet"] = d["Wt"] - d["Wp"]
        d["Ex"] = d["Qev"] * (1 - (Ta + 273.15) / (Ts + 273.15))
    return d


@lru_cache(maxsize=32)
def matlab_day(P: PlantParams):
    """Same integration as simulateDay() in the .m file; returns the daily KPI dict."""
    C = P.tank_L * 4186.0
    t0, tend = 3 * 86400.0, 4 * 86400.0

    def f(t, y):
        d = plant_instant(P, t, y[0])
        return [(d["Qcol"] - d["Qev"] - d["Qloss"]) / C, d["Geff"] * P.area, d["Qcol"], d["Qev"],
                d["Qloss"], d["Wt"], d["Wp"], d["Qc"], d["Ex"], d["mdot"]]

    sol = solve_ivp(f, (0, tend), [P.T_tank0] + [0.0] * 9, method="RK45", rtol=1e-6,
                    atol=[1e-8] + [1e-3] * 8 + [1e-9], max_step=300.0, t_eval=np.arange(0, tend + 1, 300.0))
    keep = sol.t >= t0
    t, Y = sol.t[keep], sol.y[:, keep]
    S = [plant_instant(P, ti, Ts) for ti, Ts in zip(t, Y[0])]
    D = (Y[:, -1] - Y[:, 0]) / 3600.0
    th = (t - t0) / 3600.0
    dd = np.diff(th)
    w = np.concatenate([[dd[0] / 2], (dd[:-1] + dd[1:]) / 2, [dd[-1] / 2]])
    run = np.array([s["frac"] > 0.05 for s in S])
    night = np.array([s["alt"] <= 0 for s in S])
    Wnet = D[5] - D[6]
    return dict(E_incident_Wh=D[1], E_collector_Wh=D[2], E_evaporator_Wh=D[3], E_loss_Wh=D[4],
                W_turbine_Wh=D[5], W_pump_Wh=D[6], W_net_Wh=Wnet, Q_condenser_Wh=D[7],
                eta_cycle=Wnet / D[3] if D[3] > 0 else 0.0, eta_daily=Wnet / D[1] if D[1] > 0 else 0.0,
                eta_II=Wnet / D[8] if D[8] > 0 else 0.0, run_hours=float(w[run].sum()),
                night_run_hours=float(w[run & night].sum()), peak_W_net=max(s["Wnet"] for s in S),
                Ts_max=float(Y[0].max()), mass_circulated_kg=float(Y[9, -1] - Y[9, 0]))
