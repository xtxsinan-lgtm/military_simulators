"""歼-10C / 歼-20 滑跃起飞端到端：陆基机填起飞字段后可在滑跃舰上仿真。"""
from __future__ import annotations

import pytest

from apps.web_simulator import aircraft_from_dict, run_simulation_json
from scripts.frontend_catalog import build_catalog_payload
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV


@pytest.mark.e2e
def test_e2e_j10c_and_j20_ski_jump_on_shandong():
    """歼-10C、歼-20 出现在起飞机库，并可在山东舰上完成滑跃仿真。"""
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    catalog = build_catalog_payload(aircraft, carriers)
    ids = {a['id'] for a in catalog['aircraft']}
    assert 'J-10C' in ids
    assert 'J-20' in ids
    carrier = next(c for c in catalog['carriers'] if c['id'] == 'SHANDONG')
    for aid, empty_kg, fuel_kg, mtow, thrust_n in (
        ('J-10C', 9750, 3860, 19277, 144000),
        ('J-20', 18000, 10000, 37000, 312000),
    ):
        row = next(a for a in catalog['aircraft'] if a['id'] == aid)
        spec = aircraft_from_dict(row)
        assert spec.mtow_kg == pytest.approx(mtow)
        assert spec.t_max_sl_n == pytest.approx(thrust_n)
        assert spec.a2a_mass_kg == pytest.approx(empty_kg + fuel_kg + 100 + 4 * spec.missile_mass_kg)
        assert spec.a2a_mass_kg < spec.mtow_kg
        result = run_simulation_json({
            'mode': 'ski_jump',
            'aircraft': row,
            'carrier': carrier,
            'mass_kg': spec.a2a_mass_kg,
            'temp_c': 15.0,
            'wind_kt': carrier['max_speed_kt'],
            'ski_jump_angle_deg': carrier['ski_jump_angle_deg'],
            'total_deck_length_m': carrier['total_deck_length_m'],
        })
        assert result['success'] is True, aid
        assert 'output' in result
        assert result['trajectory']
        assert result['deck_profile']


@pytest.mark.e2e
def test_e2e_j10c_j20_remain_land_based_in_combat_radius():
    """作战半径仍按陆基油量储备；起飞选项不把歼-10C / 歼-20 改成舰载机。"""
    from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_presets

    presets = load_presets()
    j10c = get_preset_by_id(presets, 'J-10C')
    j20 = get_preset_by_id(presets, 'J-20')
    assert j10c is not None and j20 is not None
    assert j10c['carrier'] is False
    assert j20['carrier'] is False
    assert j10c['engine_id'] == 'ws10b'
    assert j20['engine_id'] == 'ws15'
