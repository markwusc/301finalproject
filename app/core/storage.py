"""
Lumped thermal-storage tank (transient control volume).

Energy balance of the stored water (no mass crosses the boundary, so mass is
constant and only energy changes):

    C dT/dt = Q_collector - Q_evaporator - UA (T - T_ambient)

with C = m cp. Water properties are taken as constant (cp = 4.186 kJ/kg-K,
1 kg per litre), which is accurate to about 1 % between 20 and 100 C.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

CP_WATER = 4186.0      # J/kg-K
RHO_WATER = 1.0        # kg/L


@dataclass(frozen=True)
class StorageTank:
    volume_L: float = 500.0
    UA: float = 3.0            # overall loss coefficient, W/K

    @property
    def mass(self) -> float:
        return self.volume_L * RHO_WATER

    @property
    def capacity(self) -> float:
        """Heat capacity C [J/K]."""
        return self.mass * CP_WATER

    def loss(self, T: float, T_amb: float) -> float:
        return self.UA * (T - T_amb)

    def cooldown(self, T0: float, T_amb: float, t_seconds: float) -> float:
        """Analytic solution with no heat input: T = Ta + (T0 - Ta) exp(-UA t / C)."""
        return T_amb + (T0 - T_amb) * math.exp(-self.UA * t_seconds / self.capacity)
