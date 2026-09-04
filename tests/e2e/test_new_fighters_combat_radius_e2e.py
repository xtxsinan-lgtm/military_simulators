"""台风、阵风、苏-57、KF-21、KAAN、苏-75 作战半径端到端。"""
from __future__ import annotations

import pytest

from apps.combat_radius_web import run_combat_radius_json
from scripts.frontend_catalog import build_catalog_payload
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.combat_radius_results import run_preset_dashboard
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV

_NEW_CR_IDS = (
    'Typhoon', 'Rafale', 'Rafale-M', 'Su-57', 'KF-21', 'KAAN', 'Su-75',
)


@pytest.mark.e2e
def test_e2e_new_fighters_in_catalog_and_combat_radius():
    """新机型进入作战半径目录，升阻比与仪表盘可算。"""
    presets = load_presets()
    engines = load_engine_presets()
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    catalog = build_catalog_payload(aircraft, load_carriers_csv(CARRIERS_CSV))
    cr_ids = {p['id'] for p in catalog['combat_radius_presets']}
    takeoff_ids = {a['id'] for a in catalog['aircraft']}

    expected_engine = {
        'Typhoon': 'ej200', 'Rafale': 'm88', 'Rafale-M': 'm88',
        'Su-57': 'al41f1', 'KF-21': 'f414', 'KAAN': 'f110ge129', 'Su-75': 'al51f1',
    }
    expected_carrier = {
        'Typhoon': False, 'Rafale': False, 'Rafale-M': True,
        'Su-57': False, 'KF-21': False, 'KAAN': False, 'Su-75': False,
    }
    for aid in _NEW_CR_IDS:
        tgt = get_preset_by_id(presets, aid)
        assert tgt is not None, aid
        assert aid in cr_ids, aid
        assert aid in takeoff_ids, aid
        assert tgt['engine_id'] == expected_engine[aid], aid
        assert tgt['carrier'] is expected_carrier[aid], aid
        assert get_preset_by_id(engines, tgt['engine_id']) is not None, aid
        ld = run_combat_radius_json({'action': 'predict_ld', 'params': {'target': tgt}})
        assert ld['success'] is True, aid
        assert 6.0 < ld['target']['ld'] < 18.0, (aid, ld['target']['ld'])
        dash = run_preset_dashboard(aid)
        assert dash['success'] is True, aid
        assert dash.get('max_speed', {}).get('max_speed_mach', 0) > 1.0, aid
        m08 = next(p for p in dash['points'] if p['id'] == 'mach_0_8')
        assert m08['feasible'] is True, aid
        assert m08['radius_km'] > 200, (aid, m08['radius_km'])

    su75 = get_preset_by_id(presets, 'Su-75')
    assert su75['planform'] == 'lambda'
    assert su75['layout'] == 'pelican'
    typhoon = get_preset_by_id(presets, 'Typhoon')
    rafale = get_preset_by_id(presets, 'Rafale')
    assert typhoon['planform'] == rafale['planform'] == 'delta'
    assert typhoon['layout'] == rafale['layout'] == 'canard'
    su57 = get_preset_by_id(presets, 'Su-57')
    kaan = get_preset_by_id(presets, 'KAAN')
    assert su57['inlet'] == kaan['inlet'] == 'caret'
    kf21 = get_preset_by_id(presets, 'KF-21')
    assert kf21['inlet'] == 'dsi'
