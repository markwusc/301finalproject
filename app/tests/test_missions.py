"""Every mission must be solvable (reference solution passes) and must not pass at default settings."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from core.missions import MISSIONS

@pytest.mark.parametrize("key", list(MISSIONS))
def test_reference_solution_passes(key):
    m = MISSIONS[key]
    crit = m.evaluate(m.run(m.solution))
    assert all(c[3] for c in crit), [c for c in crit if not c[3]]

@pytest.mark.parametrize("key", list(MISSIONS))
def test_default_settings_do_not_pass(key):
    m = MISSIONS[key]
    assert not all(c[3] for c in m.evaluate(m.run({})))
