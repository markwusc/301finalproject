"""Tests for the v2 plant model, scenarios and game rules."""
import math
import random

import pytest

from core.game import (default_config, feasible, input_problems, new_scenario, outcome_problems,
                       score, summary)
from core.plant import PlantConfig, simulate, tank_UA, tank_geometry
from core.scenarios import SEASONS, Scenario, random_scenario

LIMS = (("eta_t", 0.6, 0.85), ("eta_p", 0.45, 0.75), ("eta0", 0.6, 0.78))


@pytest.mark.parametrize("diff", ["basic", "engineer"])
@pytest.mark.parametrize("season", list(SEASONS))
def test_energy_is_conserved(diff, season):
    sc = Scenario(season, "best", 40.0, LIMS if diff == "engineer" else ())
    r = simulate(default_config(diff, sc), sc)
    assert r.balance["resid_tank_rel"] < 1e-6
    assert r.balance["resid_cycle_rel"] < 1e-6


def test_tank_geometry_and_insulation():
    D, H, A_side, A_end = tank_geometry(500.0)
    assert math.isclose(math.pi * D * D / 4 * H, 0.5, rel_tol=1e-12)
    assert tank_UA(500, 1) > tank_UA(500, 5) > tank_UA(500, 10) > 0


def test_stratified_tank_is_hotter_at_the_top():
    sc = Scenario("summer", "best", 40.0, LIMS)
    r = simulate(default_config("engineer", sc), sc)
    i = int(r.series["Qcol"].argmax())
    assert r.layers[0, i] > r.layers[-1, i] + 1.0
    assert r.layers.shape[0] == 10


def test_basic_locks_values():
    sc = Scenario("summer", "best", 40.0)
    c = PlantConfig(difficulty="basic", eta_t=0.99, tracking=False, superheat=8.0)
    r = simulate(c, sc)
    assert r.config.eta_t == 0.80 and r.config.tracking and r.config.superheat == 0.0


def test_tracking_collects_more_than_fixed():
    sc = Scenario("winter", "best", 40.0, LIMS)
    c = default_config("engineer", sc)
    from dataclasses import replace
    a = simulate(replace(c, tracking=True), sc).kpi["E_incident_Wh"]
    b = simulate(replace(c, tracking=False, tilt=30.0), sc).kpi["E_incident_Wh"]
    assert a > b


def test_input_problems_flag_impossible_settings():
    sc = Scenario("summer", "best", 40.0)
    c = default_config("basic", sc)
    from dataclasses import replace
    assert input_problems(c, sc) == []
    titles = {p["title"] for p in input_problems(replace(c, Tc=5.0), sc)}
    assert "Condenser colder than the air" in titles
    titles = {p["title"] for p in input_problems(replace(c, T_start=70.0, Te=75.0), sc)}
    assert "Evaporator hotter than the tank" in titles


def test_never_started_is_reported():
    sc = Scenario("winter", "worst", 25.0)
    from dataclasses import replace
    r = simulate(replace(default_config("basic", sc), area=2.0, tank_L=2000.0), sc)
    assert any(p["title"] == "Tank never got hot enough" for p in outcome_problems(r))
    assert score("output", r)["passed"] is False


def test_random_scenarios_are_feasible():
    rng = random.Random(3)
    for mode in ("efficiency", "output", "survive"):
        sc = new_scenario(mode, "basic", rng)
        assert feasible(mode, "basic", sc)


def test_summary_has_every_device():
    sc = Scenario("spring", "best", 40.0)
    from dataclasses import replace
    a = simulate(default_config("basic", sc), sc)
    b = simulate(replace(default_config("basic", sc), area=12.0), sc)
    rows = summary(a, b)
    assert {r["device"] for r in rows} >= {"Collector", "Storage tank", "Evaporator", "Turbine", "Condenser", "Pump"}
    coll = [r for r in rows if r["label"] == "Heat collected"][0]
    assert coll["delta"] > 0 and "aperture" in coll["why"]
