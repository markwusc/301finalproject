# Solar Rankine Lab (AME 310 interactive thermodynamics project)

Virtual laboratory for a solar-driven R-134a Rankine power plant:
sun -> collector -> storage tank -> evaporator -> turbine -> condenser -> pump.

## Run
    pip install -r requirements.txt
    streamlit run app.py            # v2: main page, sandbox, game modes, scoreboard
    streamlit run app_legacy.py     # v1 interface (missions, comparison, validation pages)

Website (no installation): open `Solar_Rankine_Lab_web.html` in a current browser.
Rebuild it with `python html_edition/build.py --web` (run `html_edition/gen_tables.py` first if
`html_edition/src/tables.json` is missing).

## Version 2 (main page and game modes)
- One main page: Sandbox, three game modes (Highest Thermal Efficiency, Max Total Output,
  Survive 24 h) and a Basic / Engineer difficulty switch.
- Every game draws a random scenario: a Los Angeles season (Downtown LA 1991-2020 normals),
  best or worst case, a random tank temperature at sunrise and, in Engineer, random floors and
  ceilings for the turbine, pump and optical efficiencies. Scenarios that no design can pass are
  rejected before the player sees them. Each game opens with a scenario briefing.
- Basic: uniform tank, sun tracking, fixed efficiencies (turbine 0.80, pump 0.70, optics 0.75),
  insulation level (poor / standard / good). Engineer: 10-layer stratified tank, tracking on or
  off with a fixed tilt, efficiencies inside the scenario limits, superheat, insulation thickness.
- The scoreboard keeps the best run for each mode and difficulty with its system parameters
  (browser storage on the website, `app/scores.json` in Streamlit) and can replay its scenario.
- Settings take effect when you press Run; a side panel compares the run with the previous one,
  device by device, and explains each change. Physically impossible settings open a pop-up at
  once with Undo; problems found after a run (tank never hot enough, no net work) do the same.
- Analysis windows: animated plant (phase-coloured pipes, flow, spinning turbine and pump, collector
  and tank sized by the settings, state tags with T, P, h, s, phase and quality), device states,
  T-s diagram with isentropic references, energy balance by device, tank charge/discharge rate
  against stored energy, day plots and data.

v2 model files: `core/scenarios.py`, `core/plant.py`, `core/game.py`, `core/visuals2.py`
(website: `html_edition/src/game.js`, `ui2.js`, `viz.js`, `feedback.js`, `style2.css`).

## Layout
    app.py                 Streamlit interface v2 (no thermodynamics)
    app_legacy.py          Streamlit interface v1
    core/scenarios.py      seasonal LA scenarios, random device limits
    core/plant.py          v2 plant: stratified/uniform tank, tracking, set-point cycle, 48 h run
    core/game.py           game modes, scoring, feasibility, pop-up checks, change summaries
    core/visuals2.py       v2 Plotly figures (animated plant, T-s, storage, energy by device)
    core/properties.py     R-134a properties (CoolProp)
    core/cycle.py          pump, evaporator, turbine, condenser, entropy generation
    core/solar.py          sun position, irradiance, collector heat
    core/storage.py        storage tank
    core/simulation.py     24 h transient simulation (tank ODE + quasi-steady cycle)
    core/steady.py         steady-state calculator (hours of sun, sun angle, pump power -> W_out)
    core/missions.py       mission definitions and engineering criteria
    core/validation.py     mass / energy / second-law / solver checks
    core/visuals.py        Plotly figures and the animated plant
    docs/assumptions.md    modelling assumptions
    tests/                 pytest suite  (python -m pytest -q)
    investigations/        parameter studies (run_investigations.py)
    matlab/                MATLAB companion script
