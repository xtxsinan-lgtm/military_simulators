"""舰载起飞重量允许超 MTOW 3 t 端到端：校验放行、提示与硬上限。"""
from __future__ import annotations

import pytest

from apps.web_simulator import run_simulation
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV
from utils.takeoff.takeoff_input import (
    MTOW_OVERLOAD_ALLOWANCE_KG,
    takeoff_mass_over_mtow_warning,
    validate_takeoff_mass,
)


@pytest.mark.e2e
def test_e2e_takeoff_allows_mass_within_mtow_overload():
    """所有起飞机型：超 MTOW 但不超过 3 t 可仿真，并带回超重提示。"""
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    carrier = next(c for c in carriers if c.id == 'SHANDONG')
    ac = aircraft['53636']
    mass_kg = ac.mtow_kg + 1500
    assert validate_takeoff_mass(mass_kg, ac.mtow_kg, ac.empty_kg) is None
    warn = takeoff_mass_over_mtow_warning(mass_kg, ac.mtow_kg)
    assert warn is not None
    assert '超过最大起飞重量' in warn

    result = run_simulation(
        'ski_jump', ac, carrier, mass_kg, 15.0, carrier.max_speed_kt,
    )
    assert result['success'] is True
    assert result.get('mass_warning') == warn
    assert result.get('distance_m', 0) > 0


@pytest.mark.e2e
def test_e2e_takeoff_rejects_mass_beyond_mtow_overload():
    """超过 MTOW 逾 3 t 仍在搜索前拒绝。"""
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    carrier = next(c for c in carriers if c.id == 'SHANDONG')
    ac = aircraft['J-15']
    mass_kg = ac.mtow_kg + MTOW_OVERLOAD_ALLOWANCE_KG + 1
    result = run_simulation(
        'ski_jump', ac, carrier, mass_kg, 30.0, carrier.max_speed_kt,
    )
    assert result['success'] is False
    assert '超出最大起飞重量' in result['error']
    assert '3000' in result['error']
