"""美军 Legacy 舰载机滑跃起飞端到端：A-6/A-7/S-3/C-2/A-3/A-5 进入机库并可仿真。"""
from __future__ import annotations

import pytest

from apps.web_simulator import aircraft_from_dict, filter_aircraft_for_mode, run_simulation_json
from scripts.frontend_catalog import build_catalog_payload
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV

_USN_LEGACY_IDS = ('A-6', 'A-7', 'S-3', 'C-2', 'A-3', 'A-5')


@pytest.mark.e2e
def test_e2e_usn_legacy_in_ski_jump_catalog_and_shandong():
    """六型出现在滑跃机库，并在山东舰上以空战重量完成滑跃仿真。"""
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    catalog = build_catalog_payload(aircraft, carriers)
    ids = {a['id'] for a in catalog['aircraft']}
    ski_ids = {a.id for a in filter_aircraft_for_mode('ski_jump', list(aircraft.values()))}
    carrier = next(c for c in catalog['carriers'] if c['id'] == 'SHANDONG')
    for aid in _USN_LEGACY_IDS:
        assert aid in ids, aid
        assert aid in ski_ids, aid
        row = next(a for a in catalog['aircraft'] if a['id'] == aid)
        spec = aircraft_from_dict(row)
        assert spec.a2a_mass_kg < spec.mtow_kg, aid
        assert spec.t_max_sl_n and spec.t_max_sl_n > 0, aid
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
        assert result['deck_profile'], aid
        assert result.get('distance_m', 0) > 0, aid


@pytest.mark.e2e
def test_e2e_usn_legacy_stay_out_of_combat_radius():
    """未填分段浸润几何，作战半径库不含这六型（与歼-15 等起飞专用机一致）。"""
    from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_presets

    presets = load_presets()
    for aid in _USN_LEGACY_IDS:
        assert get_preset_by_id(presets, aid) is None, aid
        assert get_preset_by_id(presets, 'J-15') is None
