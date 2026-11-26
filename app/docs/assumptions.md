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
