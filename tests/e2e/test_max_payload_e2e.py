"""最大载弹量字段端到端：CSV → catalog → 仿真入口。"""
from __future__ import annotations

import pytest

from apps.web_simulator import aircraft_from_dict, run_simulation_json
from scripts.frontend_catalog import build_catalog_payload
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV


@pytest.mark.e2e
def test_max_payload_flows_to_catalog_and_simulation_payload():
    """机库 max_payload_kg 进入前端目录，且可被仿真反序列化。"""
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    catalog = build_catalog_payload(aircraft, carriers)
    j15 = next(a for a in catalog['aircraft'] if a['id'] == 'J-15')
    assert j15['max_payload_kg'] == 6500

    carrier = next(c for c in catalog['carriers'] if c['id'] == 'SHANDONG')
    ac = next(a for a in catalog['aircraft'] if a['id'] == 'J-15')
    spec = aircraft_from_dict(ac)
    assert spec.max_payload_kg == 6500

    result = run_simulation_json({
        'mode': 'ski_jump',
        'aircraft': ac,
        'carrier': carrier,
        'mass_kg': aircraft['J-15'].a2a_mass_kg,
        'temp_c': 30.0,
        'wind_kt': carrier['max_speed_kt'],
        'ski_jump_angle_deg': carrier['ski_jump_angle_deg'],
        'total_deck_length_m': carrier['total_deck_length_m'],
    })
    assert result['success'] is True
    assert 'output' in result


@pytest.mark.e2e
def test_e2e_f35c_carrier_ski_jump_and_land_excluded():
    """F-35C 进入起飞仿真；陆基 F-22 不得出现在起飞机库。"""
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    catalog = build_catalog_payload(aircraft, carriers)
    ids = {a['id'] for a in catalog['aircraft']}
    assert 'F-35C' in ids
    assert 'J-50N' in ids
    assert 'F-22' not in ids
    ac = next(a for a in catalog['aircraft'] if a['id'] == 'F-35C')
    carrier = next(c for c in catalog['carriers'] if c['id'] == 'SHANDONG')
    result = run_simulation_json({
        'mode': 'ski_jump',
        'aircraft': ac,
        'carrier': carrier,
        'mass_kg': aircraft['F-35C'].a2a_mass_kg,
        'temp_c': 15.0,
        'wind_kt': carrier['max_speed_kt'],
        'ski_jump_angle_deg': carrier['ski_jump_angle_deg'],
        'total_deck_length_m': carrier['total_deck_length_m'],
    })
    assert result['success'] is True
    assert 'output' in result
