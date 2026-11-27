"""Generate R-134a property tables for the standalone HTML lab (CoolProp, ASHRAE reference state)."""
import json, sys
import numpy as np
sys.path.insert(0, "/home/claude/work/solar_rankine_lab")
import CoolProp.CoolProp as CP
from CoolProp import CoolProp as _c
from CoolProp.CoolProp import AbstractState
import CoolProp
F = "R134a"
CP.set_reference_state(F, "ASHRAE")
K = 273.15
A = AbstractState("HEOS", F)

def r(x, n): return float(f"{x:.{n}g}")

# ---- saturation table: -40..100 C, 0.5 K
T0, T1, dT = -40.0, 100.0, 0.5
Ts = np.arange(T0, T1 + 1e-9, dT)
sat = {k: [] for k in ("P", "hf", "hg", "sf", "sg", "vf", "vg")}
for T in Ts:
    A.update(CoolProp.QT_INPUTS, 0.0, T + K); P = A.p()/1e3
    hf, sf, vf = A.hmass()/1e3, A.smass()/1e3, 1/A.rhomass()
    A.update(CoolProp.QT_INPUTS, 1.0, T + K)
    hg, sg, vg = A.hmass()/1e3, A.smass()/1e3, 1/A.rhomass()
    for k, v, n in (("P", P, 10), ("hf", hf, 9), ("hg", hg, 9), ("sf", sf, 9), ("sg", sg, 9), ("vf", vf, 9), ("vg", vg, 9)):
        sat[k].append(r(v, n))

# ---- superheated vapour: offsets from saturated vapour on a (Tsat, superheat) grid
TS0, TS1, dTS = -40.0, 100.0, 1.0
D0, D1, dD = 0.0, 60.0, 1.0
Tsn = np.arange(TS0, TS1 + 1e-9, dTS)
Dn = np.arange(D0, D1 + 1e-9, dD)
dh, ds = [], []
for Tsat in Tsn:
    A.update(CoolProp.QT_INPUTS, 1.0, Tsat + K)
    P, hg, sg = A.p(), A.hmass()/1e3, A.smass()/1e3
    for d in Dn:
        if d == 0:
            dh.append(0.0); ds.append(0.0); continue
        A.update(CoolProp.PT_INPUTS, P, Tsat + d + K)
        dh.append(r(A.hmass()/1e3 - hg, 7)); ds.append(r(A.smass()/1e3 - sg, 7))

# ---- effective liquid specific volume for isentropic pump work: vbar = (h2s-h1)/(Pe-Pc)
TC0, TC1, dTC = -30.0, 80.0, 2.5
TE0, TE1, dTE = -30.0, 100.0, 2.5
Tcn = np.arange(TC0, TC1 + 1e-9, dTC); Ten = np.arange(TE0, TE1 + 1e-9, dTE)
vbar = []
for Tc in Tcn:
    A.update(CoolProp.QT_INPUTS, 0.0, Tc + K)
    Pc, h1, s1, vf = A.p(), A.hmass(), A.smass(), 1/A.rhomass()
    for Te in Ten:
        A.update(CoolProp.QT_INPUTS, 0.0, Te + K); Pe = A.p()
        if abs(Pe - Pc) < 1.0:
            vbar.append(r(vf, 9)); continue
        A.update(CoolProp.PSmass_INPUTS, Pe, s1)
        vbar.append(r((A.hmass() - h1) / (Pe - Pc), 9))

# ---- reference points (for the in-page validation page)
rng = np.random.default_rng(7)
refs = []
for T in (-20.0, 0.0, 25.0, 50.0, 70.0, 90.0):
    A.update(CoolProp.QT_INPUTS, 1.0, T + K)
    refs.append(dict(T=T, P=A.p()/1e3, hg=A.hmass()/1e3, sg=A.smass()/1e3))
tcrit = CP.PropsSI("Tcrit", F) - K; pcrit = CP.PropsSI("pcrit", F)/1e3

out = dict(fluid=F, Tcrit=tcrit, Pcrit=pcrit,
           sat=dict(T0=T0, dT=dT, n=len(Ts), **sat),
           sh=dict(Ts0=TS0, dTs=dTS, nTs=len(Tsn), D0=D0, dD=dD, nD=len(Dn), dh=dh, ds=ds),
           pump=dict(Tc0=TC0, dTc=dTC, nTc=len(Tcn), Te0=TE0, dTe=dTE, nTe=len(Ten), vbar=vbar),
           refs=refs)
json.dump(out, open("src/tables.json", "w"), separators=(",", ":"))
import os; print(os.path.getsize("src/tables.json")/1024, "KB", tcrit, pcrit)
