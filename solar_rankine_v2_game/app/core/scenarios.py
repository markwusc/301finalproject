"""
Seasonal weather scenarios, difficulty settings and randomised device limits.

Every game (and the sandbox) runs on one *scenario*: a representative day in
Los Angeles (latitude 34.05 N) for one season, in a best or worst case, plus a
random starting tank temperature. Engineer scenarios also draw random floors
and ceilings for the device efficiencies.

Season data: Downtown Los Angeles 1991-2020 normals (NOAA, as tabulated in the
Wikipedia article "Climate of Los Angeles"), averaged over the three months of
each season:

    season   months     mean max  mean min  possible sunshine
    winter   Dec-Feb    19.9 C     9.5 C     71 %
    spring   Mar-May    22.2 C    12.8 C     71 %
    summer   Jun-Aug    27.3 C    17.7 C     77 %
    fall     Sep-Nov    25.6 C    15.0 C     73 %

Best case  : clear sky (clearness 1.0), air 2 K cooler than normal.
Worst case : clearness equal to the season's fraction of possible sunshine,
             air 2 K warmer than normal (a hot condenser is the worst case for
             a Rankine plant).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, asdict, field
from typing import Dict, Optional, Tuple

from . import solar

LAT = 34.05

SEASONS: Dict[str, dict] = {
    #            representative day    normals (C)          possible sunshine
    "winter": dict(day=15,  label="Winter (15 Jan)", t_max=19.9, t_min=9.5,  sun=0.71),
    "spring": dict(day=105, label="Spring (15 Apr)", t_max=22.2, t_min=12.8, sun=0.71),
    "summer": dict(day=196, label="Summer (15 Jul)", t_max=27.3, t_min=17.7, sun=0.77),
    "fall":   dict(day=288, label="Fall (15 Oct)",   t_max=25.6, t_min=15.0, sun=0.73),
}
CASES = ("best", "worst")
CASE_DT = {"best": -2.0, "worst": +2.0}

# random efficiency floors and ceilings for Engineer scenarios: (floor range, ceiling range)
EFF_RANGES = {
    "eta_t": ((0.55, 0.65), (0.78, 0.88)),
    "eta_p": ((0.40, 0.50), (0.65, 0.80)),
    "eta0": ((0.55, 0.65), (0.72, 0.82)),
}
BASIC_EFF = {"eta_t": 0.80, "eta_p": 0.70, "eta0": 0.75}
T_TANK0_RANGE = (25.0, 55.0)


@dataclass(frozen=True)
class Scenario:
    season: str = "summer"
    case: str = "best"
    T_tank0: float = 30.0
    # efficiency limits: name -> (floor, ceiling); Basic uses fixed values
    limits: Tuple[Tuple[str, float, float], ...] = ()

    # ---- derived weather ---------------------------------------------------
    @property
    def day(self) -> int:
        return SEASONS[self.season]["day"]

    @property
    def lat(self) -> float:
        return LAT

    @property
    def clearness(self) -> float:
        return 1.0 if self.case == "best" else SEASONS[self.season]["sun"]

    @property
    def T_mean(self) -> float:
        s = SEASONS[self.season]
        return 0.5 * (s["t_max"] + s["t_min"]) + CASE_DT[self.case]

    @property
    def T_swing(self) -> float:
        s = SEASONS[self.season]
        return s["t_max"] - s["t_min"]

    @property
    def T_amb_min(self) -> float:
        return self.T_mean - 0.5 * self.T_swing

    @property
    def T_amb_max(self) -> float:
        return self.T_mean + 0.5 * self.T_swing

    @property
    def daylight(self) -> float:
        return solar.daylight_hours(LAT, self.day)

    @property
    def sunrise(self) -> float:
        return 12.0 - 0.5 * self.daylight

    @property
    def label(self) -> str:
        return f"{SEASONS[self.season]['label']}, {self.case} case"

    def limit(self, name: str) -> Optional[Tuple[float, float]]:
        for n, lo, hi in self.limits:
            if n == name:
                return lo, hi
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["limits"] = [list(x) for x in self.limits]
        return d

    @staticmethod
    def from_dict(d: dict) -> "Scenario":
        return Scenario(d["season"], d["case"], float(d["T_tank0"]),
                        tuple((str(a), float(b), float(c)) for a, b, c in d.get("limits", [])))

    def briefing(self) -> dict:
        """The numbers shown to the player at the start of a game."""
        out = dict(scenario=self.label, daylight_h=round(self.daylight, 2),
                   sunrise=round(self.sunrise, 2), sunset=round(24 - self.sunrise, 2),
                   clearness=self.clearness, T_amb_min=round(self.T_amb_min, 1),
                   T_amb_max=round(self.T_amb_max, 1), T_tank0=round(self.T_tank0, 1))
        for n, lo, hi in self.limits:
            out[f"{n}_range"] = (round(lo, 3), round(hi, 3))
        return out


def random_scenario(difficulty: str, rng: Optional[random.Random] = None,
                    season: Optional[str] = None, case: Optional[str] = None) -> Scenario:
    rng = rng or random.Random()
    s = season or rng.choice(list(SEASONS))
    c = case or rng.choice(CASES)
    T0 = round(rng.uniform(*T_TANK0_RANGE), 1)
    limits = ()
    if difficulty == "engineer":
        limits = tuple((n, round(rng.uniform(*f), 3), round(rng.uniform(*cl), 3))
                       for n, (f, cl) in EFF_RANGES.items())
    return Scenario(s, c, T0, limits)
