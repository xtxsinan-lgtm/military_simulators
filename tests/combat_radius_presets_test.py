"""作战半径机型预设单元测试。"""
from __future__ import annotations

from utils.combat_radius.combat_radius_presets import (
    build_combat_radius_engine_presets_payload,
    build_combat_radius_presets_payload,
    get_preset_by_id,
    load_engine_presets,
    load_presets,
    preset_to_aircraft,
    preset_to_aircraft_dict,
)
from utils.paths import COMBAT_RADIUS_AIRCRAFT_CSV, COMBAT_RADIUS_ENGINE_CSV


def test_load_presets_contains_anchors_and_j20():
    presets = load_presets()
    ids = [p['id'] for p in presets]
    assert ids == ['F-35C', 'F-22', 'J-20']
    f35 = get_preset_by_id(presets, 'F-35C')
    assert f35 is not None
    assert f35['rough'] is True
    assert f35['ld_known'] == 8.8
    j20 = get_preset_by_id(presets, 'J-20')
    assert j20 is not None
    assert j20['planform'] == 'delta'
    assert j20['layout'] == 'canard'
    assert 'ld_known' not in j20


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
    assert 'tsl_kN' not in ws15


def test_build_combat_radius_engine_presets_payload():
    payload = build_combat_radius_engine_presets_payload()
    assert payload[0]['id'] == 'ws15'
    assert COMBAT_RADIUS_ENGINE_CSV.is_file()


def test_load_engine_presets_missing_file_returns_empty(tmp_path):
    missing = tmp_path / 'no_eng.csv'
    assert load_engine_presets(missing) == []
