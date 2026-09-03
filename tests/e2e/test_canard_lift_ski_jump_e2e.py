"""近距耦合鸭翼增升进入滑跃起飞端到端。"""
from __future__ import annotations

from dataclasses import replace

import pytest

from apps.web_simulator import run_simulation
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV
from utils.takeoff.takeoff_physics import calc_canard_lift_factor


@pytest.mark.e2e
def test_e2e_canard_lift_shortens_j10c_ski_jump():
    """歼-10C 计入鸭翼净增升后，山东舰滑跃距离短于关掉鸭翼的同一机。"""
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    j10 = aircraft['J-10C']
    carrier = next(c for c in carriers if c.id == 'SHANDONG')
    factor = calc_canard_lift_factor(j10.layout, j10.canard_htail_area_m2, j10.wing_area_m2)
    assert factor == pytest.approx(1.0 + 0.5 * 4.9 / 37.0)
    r_on = run_simulation(
        'ski_jump', j10, carrier, j10.a2a_mass_kg, 15.0, carrier.max_speed_kt,
    )
    r_off = run_simulation(
        'ski_jump', replace(j10, layout='conventional'),
        carrier, j10.a2a_mass_kg, 15.0, carrier.max_speed_kt,
    )
    assert r_on['success'] is True
    assert r_off['success'] is True
    assert r_on['distance_m'] < r_off['distance_m']
