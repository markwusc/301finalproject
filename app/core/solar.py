"""
Solar geometry, clear-sky beam irradiance and collector model.

Fixed-tilt collector facing the equator (south in the northern hemisphere).
Times are solar time in hours (12.0 = solar noon), so no time-zone or
equation-of-time corrections are needed.

References
    Duffie & Beckman, Solar Engineering of Thermal Processes (geometry).
    Meinel & Meinel (1976) clear-sky direct-beam attenuation, 0.7^(AM^0.678).
"""
from __future__ import annotations

import math

SOLAR_CONSTANT = 1353.0        # W/m^2


def declination_deg(day_of_year: int) -> float:
    """Cooper's equation for solar declination [deg]."""
    return 23.45 * math.sin(math.radians(360.0 * (284 + day_of_year) / 365.0))


def _hemisphere(lat_deg: float, decl_deg: float):
    """Mirror the southern hemisphere so the collector always faces the equator."""
    if lat_deg < 0:
        return -lat_deg, -decl_deg
    return lat_deg, decl_deg


def sun_position(hour: float, lat_deg: float, day_of_year: int):
    """Return (sin of solar altitude, altitude in deg)."""
    lat, dec = _hemisphere(lat_deg, declination_deg(day_of_year))
    w = math.radians(15.0 * (hour - 12.0))
    sin_alt = (math.sin(math.radians(lat)) * math.sin(math.radians(dec))
               + math.cos(math.radians(lat)) * math.cos(math.radians(dec)) * math.cos(w))
    sin_alt = max(-1.0, min(1.0, sin_alt))
    return sin_alt, math.degrees(math.asin(sin_alt))


def cos_incidence(hour: float, lat_deg: float, day_of_year: int, tilt_deg: float) -> float:
    """Cosine of the angle between the sun and the collector normal (>= 0)."""
    lat, dec = _hemisphere(lat_deg, declination_deg(day_of_year))
    w = math.radians(15.0 * (hour - 12.0))
    phi_b = math.radians(lat - tilt_deg)
    d = math.radians(dec)
    c = math.sin(d) * math.sin(phi_b) + math.cos(d) * math.cos(phi_b) * math.cos(w)
    return max(0.0, c)


def daylight_hours(lat_deg: float, day_of_year: int) -> float:
    """Sunrise-to-sunset duration [h]."""
    lat, dec = _hemisphere(lat_deg, declination_deg(day_of_year))
    x = -math.tan(math.radians(lat)) * math.tan(math.radians(dec))
    x = max(-1.0, min(1.0, x))
    return 2.0 * math.degrees(math.acos(x)) / 15.0


def beam_irradiance(sin_alt: float, day_of_year: int, clearness: float = 1.0) -> float:
    """Clear-sky direct normal irradiance [W/m^2], scaled by a clearness factor.

    Blended to zero between 0 and 3 degrees of altitude so the solver sees a
    continuous function at sunrise and sunset.
    """
    if sin_alt <= 0.0:
        return 0.0
    air_mass = 1.0 / max(sin_alt, 0.02)
    e0 = 1.0 + 0.033 * math.cos(math.radians(360.0 * day_of_year / 365.0))
    g = SOLAR_CONSTANT * e0 * 0.7 ** (air_mass ** 0.678)
    ramp = min(1.0, sin_alt / math.sin(math.radians(3.0)))
    return clearness * g * ramp


def collector_heat(G_beam_eff: float, T_col: float, T_amb: float, area: float,
                   eta0: float, a1: float, a2: float) -> float:
    """Useful heat of a quadratic-loss collector [W].

    q = A [eta0 G cos(theta) - a1 (Tc - Ta) - a2 (Tc - Ta)^2]
    """
    dT = T_col - T_amb
    return area * max(0.0, eta0 * G_beam_eff - a1 * dT - a2 * dT * dT)


def ambient_temperature(hour: float, T_mean: float, T_swing: float) -> float:
    """Sinusoidal day: warmest at 15:00, coldest at 03:00 (peak-to-peak = T_swing)."""
    return T_mean + 0.5 * T_swing * math.cos(2.0 * math.pi * (hour - 15.0) / 24.0)
