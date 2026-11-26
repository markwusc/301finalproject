# Solar Rankine Lab (AME 310 interactive thermodynamics project)

Virtual laboratory for a solar-driven R-134a Rankine power plant:
sun -> collector -> storage tank -> evaporator -> turbine -> condenser -> pump.

## Run
    pip install -r requirements.txt
    streamlit run app.py

## Layout
    app.py                 Streamlit interface only (no thermodynamics)
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
