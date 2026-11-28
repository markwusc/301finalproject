**Working fluid.** R-134a (Freon) with CoolProp's Helmholtz-energy equation of state, ASHRAE reference state.

**Plant.** Sun, fixed-tilt collector, insulated water tank, evaporator, turbine, air-cooled condenser, pump.

**Collector.** Heat output per area is `eta0 G cos(theta) - a1 (T - Ta) - a2 (T - Ta)^2` with clear-sky beam irradiance from the Meinel
model (`0.7^(AM^0.678)`) scaled by a clearness factor. Solar geometry from declination and hour angle (Duffie and Beckman). The collector faces the equator.
Useful heat falls to zero as the tank approaches the defocus limit.

**Storage tank (transient control volume).** Lumped, uniform temperature, constant water properties (4.186 kJ/kg-K), no mass crossing the boundary:
`C dT/dt = Q_collector - Q_evaporator - UA (T - Ta)`.

**Steady-flow devices (SSSF).** Pump, evaporator, turbine and condenser are in quasi-steady operation (their time constants are seconds, the tank's are hours).
Kinetic and potential energy changes are negligible, no pressure drops in heat exchangers or pipes, saturated liquid leaves the condenser.
`w_p = (h2s - h1)/eta_p`, `q_in = h3 - h2`, `w_t = eta_t (h3 - h4s)`, `q_out = h4 - h1`. Closed turbine valve: isenthalpic throttle, `w_t = 0`.

**Pump power sets the mass flow.** `m_dot = f P_pump / w_p`, where `f` is a controller ramp between the start and full-flow tank temperatures.

**Temperatures.** Turbine-inlet temperature is the tank temperature minus a pinch; with superheat, the evaporating temperature is lower by the same amount. Condensing temperature is ambient plus an approach.
Evaporating temperature is capped at 95 C, clear of the 101 C critical point.

**Second law.** Entropy generation is evaluated per device against the tank (source) and ambient (sink). Second-law efficiency is net work over the exergy of the heat drawn from the tank.

**Numerics.** Adaptive RK45 (`scipy.integrate.solve_ivp`), relative tolerance 1e-6, 5 min output grid, three warm-up days so the tank starts the reported day in a periodic state (end-of-day tank energy equals start-of-day to within 0.3 Wh).
Energy, exergy, work and mass are carried as quadrature states in the same solver.

## Version 2 model (main page and game modes)

**Scenarios.** Los Angeles, 34.05 N. One representative day per season (15 Jan, 15 Apr, 15 Jul, 15 Oct) with the
Downtown Los Angeles 1991-2020 normals averaged over the season's three months (mean daily maximum and minimum, fraction
of possible sunshine). Best case: clear sky, air 2 K cooler than normal. Worst case: clearness equal to the season's
fraction of possible sunshine, air 2 K warmer than normal. Ambient temperature is sinusoidal (warmest at 15:00) between
the scenario minimum and maximum. The tank starts at a random 25-55 C at sunrise. Engineer scenarios draw random floors
and ceilings for the turbine (0.55-0.65 / 0.78-0.88), pump (0.40-0.50 / 0.65-0.80) and optical (0.55-0.65 / 0.72-0.82)
efficiencies. A scenario is used only if a reference design passes the chosen mode.

**Run.** 48 h from sunrise with two identical days of weather. The scored day is the first 24 h; the survival window is the
24 h after the first start-up.

**Tank.** Basic: one uniform layer. Engineer: 10 layers. The collector loop draws from the bottom (0.015 kg/s per m^2)
and returns at the top; the evaporator draws from the top and returns the water at Te + 5 K to the bottom. The net flow
carries energy between layers; a 2 W/K conductance couples neighbours and 200 W/K per kelvin of inversion mixes any layer
colder than the one below. Cylinder with height = 2 x diameter; losses through polyurethane foam (k = 0.025 W/m-K) and an
outside air film (10 W/m^2-K): U = 1 / (t/k + 1/h), UA = U x (side + both ends). Basic insulation levels: poor 1 cm,
standard 5 cm, good 10 cm. For one layer the model reduces to C dT/dt = Q_col - Q_evap - UA (T - T_amb).

**Collector.** Tracking (Basic, optional in Engineer): cos(theta) = 1 while the sun is up. Fixed: south-facing at the
chosen tilt. Collector losses use the inlet (tank bottom) temperature. The collector defocuses over the 3 K below the
defocus temperature of the tank top.

**Cycle.** The evaporating temperature Te is a set point; superheat (Engineer) heats the vapour to Te + SH. The plant runs
only while the tank top is at least Te + SH + 5 K, and starts at the start temperature (full flow 3 K above it). The
condensing temperature is a set point but cannot be closer than 3 K to the air: Tc = max(Tc_set, T_amb + 3 K). The turbine
needs Te - Tc of at least 6 K. Pump input power sets the mass flow.

**Checks.** Settings that are impossible at once (condenser colder than the coldest air + 3 K, lift below 6 K, start
temperature below Te + SH + 5 K, start temperature above the defocus temperature) open a pop-up with Undo. After a run, a
tank that never reaches the start temperature and a day with no net work open the same pop-up.
