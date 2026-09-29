"""补回作战半径的第四代与教练战斗机端到端。"""
from __future__ import annotations

import pytest

from apps.combat_radius_web import run_combat_radius_json
from scripts.frontend_catalog import build_catalog_payload
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.combat_radius_results import run_preset_dashboard
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV

# 历史机库里缺分段浸润、因而从作战半径消失的型号，加公开资料补上的新型号。
_RESTORED_IDS = (
    'F-14', 'FA-18E', 'FA-18C', 'F-16', 'F-15', 'F-15E',
    'Gripen-CD', 'Gripen-EF', 'FC-1', 'MiG-29K', 'J-15', 'J-15T',
    'Mirage-2000', 'F-CK-1', 'FA-50', 'L-15B', 'Tejas',
)


@pytest.mark.e2e
def test_e2e_restored_fighters_in_combat_radius():
    """补齐几何后这些机型进入作战半径，升阻比与 Ma 0.8 半径可算。"""
    presets = load_presets()
    engines = load_engine_presets()
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    catalog = build_catalog_payload(aircraft, load_carriers_csv(CARRIERS_CSV))
    cr_ids = {p['id'] for p in catalog['combat_radius_presets']}
    takeoff_ids = {a['id'] for a in catalog['aircraft']}
    expected_engine = {
        'F-14': 'f110', 'FA-18E': 'f414', 'FA-18C': 'f404', 'F-16': 'f110ge129',
        'F-15': 'f100', 'F-15E': 'f100229', 'Gripen-CD': 'rm12', 'Gripen-EF': 'f414',
        'FC-1': 'rd93', 'MiG-29K': 'rd33mk', 'J-15': 'ws10h', 'J-15T': 'ws10h',
        'Mirage-2000': 'm53p2', 'F-CK-1': 'f125', 'FA-50': 'f404ge102',
        'L-15B': 'ai222k25f', 'Tejas': 'f404in20',
    }
    for aid in _RESTORED_IDS:
        tgt = get_preset_by_id(presets, aid)
        assert tgt is not None, aid
        assert aid in cr_ids, aid
        assert aid in takeoff_ids, aid
        assert tgt['store_mount'] == 'pylon', aid
        assert tgt['engine_id'] == expected_engine[aid], aid
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

    assert get_preset_by_id(presets, 'J-10C') is not None
    assert get_preset_by_id(presets, 'Mirage-2000')['layout'] == 'tailless'
    assert get_preset_by_id(presets, 'F-15E')['n_pilots'] == 2
    assert get_preset_by_id(presets, 'L-15B')['n_engines'] == 2
    assert get_preset_by_id(presets, 'FA-50')['nation'] == '韩国'
