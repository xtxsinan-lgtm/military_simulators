"""53636 / 53636N 最大起飞重量端到端：CSV → catalog / API → 滑跃仿真。"""
from __future__ import annotations

import json

import pytest

from apps.miniprogram_api import handle_request
from apps.web_simulator import aircraft_from_dict, filter_aircraft_for_mode, run_simulation_json
from scripts.frontend_catalog import build_catalog_payload
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_presets
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV


@pytest.mark.e2e
def test_e2e_53636_mtow_catalog_and_ski_jump():
    """普通版 14.6 t、舰载版 15.2 t 进入三端目录，且空战重量可在山东舰滑跃。"""
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    catalog = build_catalog_payload(aircraft, carriers)
    takeoff_ids = {a['id'] for a in catalog['aircraft']}
    ski_ids = {a.id for a in filter_aircraft_for_mode('ski_jump', list(aircraft.values()))}

    assert aircraft['53636'].mtow_kg == pytest.approx(14600)
    assert aircraft['53636N'].mtow_kg == pytest.approx(15200)
    assert '53636' in takeoff_ids
    assert '53636N' in takeoff_ids
    assert '53636' in ski_ids
    assert '53636N' in ski_ids

    status, _, body = handle_request('GET', '/api/data', None)
    assert status == 200
    api = json.loads(body.decode())
    api_uav = next(a for a in api['aircraft'] if a['id'] == '53636')
    api_uav_n = next(a for a in api['aircraft'] if a['id'] == '53636N')
    assert api_uav['mtow_kg'] == pytest.approx(14600)
    assert api_uav_n['mtow_kg'] == pytest.approx(15200)

    carrier = next(c for c in catalog['carriers'] if c['id'] == 'SHANDONG')
    for aid in ('53636', '53636N'):
        row = next(a for a in catalog['aircraft'] if a['id'] == aid)
        spec = aircraft_from_dict(row)
        assert spec.a2a_mass_kg < spec.mtow_kg, aid
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
        assert result['trajectory'], aid
        assert result.get('distance_m', 0) > 0, aid

    presets = load_presets()
    land = get_preset_by_id(presets, '53636')
    naval = get_preset_by_id(presets, '53636N')
    assert land is not None and naval is not None
    assert land['carrier'] is False
    assert naval['carrier'] is True
