"""平直翼机型起飞襟翼 25° 进入滑跃仿真端到端。"""
from __future__ import annotations

import pytest

from apps.web_simulator import aircraft_from_dict, run_simulation
from scripts.frontend_catalog import build_catalog_payload
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV


@pytest.mark.e2e
def test_e2e_kj600_catalog_exposes_takeoff_flap_and_ski_jump_succeeds():
    """空警-600 目录含 takeoff_flap_deg=25，山东舰正常起飞重量可滑跃。"""
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    catalog = build_catalog_payload(aircraft, carriers)
    row = next(a for a in catalog['aircraft'] if a['id'] == 'KJ-600')
    assert row['takeoff_flap_deg'] == pytest.approx(25.0)
    spec = aircraft_from_dict(row)
    carrier = next(c for c in carriers if c.id == 'SHANDONG')
    result = run_simulation(
        'ski_jump', spec, carrier, spec.a2a_mass_kg, 30.0, 30.0,
    )
    assert result['success'] is True
    assert result['distance_m'] is not None
