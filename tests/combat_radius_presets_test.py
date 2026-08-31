"""作战半径机型预设单元测试。"""
from __future__ import annotations

import pytest

from utils.combat_radius.combat_radius_presets import (
    build_combat_radius_engine_presets_payload,
    build_combat_radius_presets_payload,
    clear_injected_combat_radius_presets,
    get_preset_by_id,
    inject_combat_radius_presets,
    load_engine_presets,
    load_presets,
    preset_to_aircraft,
    preset_to_aircraft_dict,
)
from utils.paths import COMBAT_RADIUS_AIRCRAFT_CSV, COMBAT_RADIUS_ENGINE_CSV

# 统一库：原作战半径 12 型在前，其后为起飞库补入的舰载机
EXPECTED_COMBAT_RADIUS_AIRCRAFT_IDS = [
    'F-35C', 'F-22', 'F-35A', 'J-20', 'J-50', 'J-50N', 'J-36',
    'J-35', 'J-35A', '53636', '53636N', '53536',
    'F-35B', 'AV-8B', 'J-15', 'J-15T', 'MiG-29K', 'Rafale-M',
    'FA-18E', 'FA-18C', 'F-14', 'MV-22',
]


def test_load_presets_contains_anchors_and_j20():
    presets = load_presets()
    ids = [p['id'] for p in presets]
    assert ids == EXPECTED_COMBAT_RADIUS_AIRCRAFT_IDS
    f35 = get_preset_by_id(presets, 'F-35C')
    assert f35 is not None
    assert f35['rough'] is True
    assert 'ld_known' not in f35
    assert f35['n_engines'] == 1
    assert f35['engine_id'] == 'f135'
    j20 = get_preset_by_id(presets, 'J-20')
    assert j20 is not None
    assert j20['planform'] == 'trapezoidal'
    assert j20['layout'] == 'canard'
    assert 'ld_known' not in j20
    j50 = get_preset_by_id(presets, 'J-50')
    assert j50 is not None
    assert j50['planform'] == 'lambda'
    uav = get_preset_by_id(presets, '53636')
    assert uav is not None
    assert uav['n_pilots'] == 0
    assert uav['length_m'] == pytest.approx(14.6)
    assert uav['engine_id'] == 'ws10c'
    ac_uav = preset_to_aircraft(uav)
    assert ac_uav.canopy is False
    assert ac_uav.mach_angle_deg == pytest.approx(22.9)
    j36 = get_preset_by_id(presets, 'J-36')
    assert j36 is not None
    assert j36['n_engines'] == 3
    assert j36['n_pilots'] == 2
    assert j36['planform'] == 'double_delta'
    assert j36['bwb'] is True
    uav535 = get_preset_by_id(presets, '53536')
    assert uav535 is not None
    assert uav535['planform'] == 'diamond'
    assert uav535['bwb'] is True
    assert uav535['engine_id'] == 'ws10c'
    assert j36['sweep_inner_deg'] == pytest.approx(67.8)
    assert j36['sweep_outer_deg'] == pytest.approx(55.3)
    ac36 = preset_to_aircraft(j36)
    assert ac36.sweep_inner_deg == pytest.approx(67.8)
    assert ac36.sweep_outer_deg == pytest.approx(55.3)
    j15 = get_preset_by_id(presets, 'J-15')
    assert j15 is not None
    assert j15['carrier'] is True
    assert j15['engine_id'] == 'ws10h'
    f22 = get_preset_by_id(presets, 'F-22')
    assert f22['carrier'] is False
    assert f22['inlet'] == 'caret'
    assert j36['inlet'] == 'caret'
    assert uav['inlet'] == 'caret'
    uav_n = get_preset_by_id(presets, '53636N')
    assert uav_n is not None
    assert uav_n['engine_id'] == 'ws10c'
    assert uav_n['inlet'] == 'caret'
    assert j20['inlet'] == 'dsi'
    assert f35['inlet'] == 'dsi'


def test_get_preset_by_id_missing_returns_none():
    assert get_preset_by_id(load_presets(), 'NO-SUCH') is None


def test_preset_to_aircraft_and_dict():
    p = get_preset_by_id(load_presets(), 'F-22')
    ac = preset_to_aircraft(p)
    d = preset_to_aircraft_dict(p)
    assert ac.name == 'F-22 Raptor'
    assert d['AR'] == 2.37
    assert 'id' not in d
    assert 'ld_known' not in d
    assert p['mach_angle_deg'] == pytest.approx(28.5)
    assert ac.mach_angle_deg == pytest.approx(28.5)
    assert p['empty_kg'] == 19800
    assert p['bvr_missile'] == 'AIM-120D'


def test_build_combat_radius_presets_payload():
    payload = build_combat_radius_presets_payload()
    assert payload[0]['id'] == 'F-35C'
    assert COMBAT_RADIUS_AIRCRAFT_CSV.is_file()


def test_load_presets_missing_file_returns_empty(tmp_path):
    missing = tmp_path / 'no.csv'
    assert load_presets(missing) == []


def test_load_engine_presets_contains_f119_and_optional_tsl():
    engines = load_engine_presets()
    ids = [p['id'] for p in engines]
    assert 'f119' in ids
    assert 'ws15' in ids
    f119 = get_preset_by_id(engines, 'f119')
    assert f119 is not None
    assert f119['bpr'] == 0.30
    assert f119['tsl_kN'] == 116.0
    ws15 = get_preset_by_id(engines, 'ws15')
    assert ws15 is not None
    assert ws15['tsl_kN'] == 105.0
    assert ws15['max_tsl_kN'] == 156.0
    ws15i = get_preset_by_id(engines, 'ws15i')
    assert ws15i is not None
    assert ws15i['tsl_kN'] == pytest.approx(13.5 * 9.80665, abs=0.05)
    expected = {
        'ws15': (0.25, 25.5, 1841.0),
        'ws15i': (0.25, 29.0, 1975.0),
        'ws19': (0.50, 35.0, 1850.0),
        'ws10c': (0.60, 30.0, 1800.0),
        'ws21': (0.68, 26.0, 1650.0),
        'f119': (0.30, 26.0, 1922.0),
        'f135': (0.57, 28.0, 2260.0),
        'ws10h': (0.60, 30.0, 1800.0),
        'f414': (0.40, 30.0, 1850.0),
        'f404': (0.34, 26.0, 1700.0),
        'f110': (0.76, 30.7, 1700.0),
        'rd33mk': (0.49, 21.0, 1680.0),
        'm88': (0.30, 24.5, 1850.0),
        'f402': (1.20, 16.0, 1400.0),
    }
    for eid, (bpr, opr, t4) in expected.items():
        row = get_preset_by_id(engines, eid)
        assert row is not None
        assert row['bpr'] == pytest.approx(bpr)
        assert row['opr'] == pytest.approx(opr)
        assert row['t4_K'] == pytest.approx(t4)
    f135 = get_preset_by_id(engines, 'f135')
    assert f135 is not None
    assert f135['tsfc_install_mult'] == pytest.approx(1.15)


def test_build_combat_radius_engine_presets_payload():
    payload = build_combat_radius_engine_presets_payload()
    assert payload[0]['id'] == 'ws15'
    assert COMBAT_RADIUS_ENGINE_CSV.is_file()
    assert COMBAT_RADIUS_ENGINE_CSV.name == 'aircraft_engine_database.csv'


def test_load_engine_presets_missing_file_returns_empty(tmp_path):
    missing = tmp_path / 'no_eng.csv'
    assert load_engine_presets(missing) == []


def test_inject_combat_radius_presets_overrides_csv():
    inject_combat_radius_presets(
        aircraft=[{'id': 'X', 'name': '注入机'}],
        engines=[{'id': 'e', 'name': '注入发'}],
    )
    try:
        assert load_presets()[0]['id'] == 'X'
        assert load_engine_presets()[0]['id'] == 'e'
    finally:
        clear_injected_combat_radius_presets()
    assert get_preset_by_id(load_presets(), 'F-22') is not None
