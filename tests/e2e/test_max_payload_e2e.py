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
    assert 'J-10C' in ids
    assert 'J-20' in ids
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
    from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_presets
    from utils.combat_radius.lift_drag import aircraft_from_dict as cr_from_dict, estimate_takeoff_cd0

    preset = get_preset_by_id(load_presets(), 'F-35C')
    assert ac['cd0'] == pytest.approx(estimate_takeoff_cd0(cr_from_dict(preset)))


@pytest.mark.e2e
def test_e2e_j50n_takeoff_weights_match_combat_radius():
    """歼-50舰载起飞重量与作战半径库同源，满内油 4 弹空战重量可上舰仿真。"""
    from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_presets
    from utils.specs import A2A_MISSILE_COUNT, PILOT_LOAD_KG

    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    catalog = build_catalog_payload(aircraft, carriers)
    takeoff = next(a for a in catalog['aircraft'] if a['id'] == 'J-50N')
    cr = get_preset_by_id(load_presets(), 'J-50N')
    land = get_preset_by_id(load_presets(), 'J-50')
    assert takeoff['empty_kg'] == cr['empty_kg'] == land['empty_kg'] == 20800
    assert takeoff['internal_fuel_kg'] == cr['internal_fuel_kg'] == 13000
    assert takeoff['mtow_kg'] == 41000
    spec = aircraft_from_dict(takeoff)
    expected_a2a = (
        20800 + 13000 + A2A_MISSILE_COUNT * spec.missile_mass_kg
        + spec.n_pilots * PILOT_LOAD_KG
    )
    assert spec.a2a_mass_kg == pytest.approx(expected_a2a)
    assert spec.a2a_mass_kg == pytest.approx(34740)
    carrier = next(c for c in catalog['carriers'] if c['id'] == 'SHANDONG')
    result = run_simulation_json({
        'mode': 'ski_jump',
        'aircraft': takeoff,
        'carrier': carrier,
        'mass_kg': spec.a2a_mass_kg,
        'temp_c': 15.0,
        'wind_kt': carrier['max_speed_kt'],
        'ski_jump_angle_deg': carrier['ski_jump_angle_deg'],
        'total_deck_length_m': carrier['total_deck_length_m'],
    })
    assert result['success'] is True
    assert 'output' in result
