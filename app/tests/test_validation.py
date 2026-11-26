"""Run with:  pytest -q   (from the project root)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from core import validation as v

CHECKS = v.run_all()

@pytest.mark.parametrize("chk", CHECKS, ids=[f"{c.category}: {c.name[:60]}" for c in CHECKS])
def test_check(chk):
    assert chk.passed, f"{chk.name}: value {chk.value:.3e}, tolerance {chk.tolerance:.1e}"
