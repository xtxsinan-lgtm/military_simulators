"""战斗机外挂挂点与弹药模型单元测试。"""
import pytest

from utils.stores.stores_config import (
    build_aircraft_stores_payload,
    load_aircraft_stations,
    load_aircraft_store_limits,
    load_stores_database,
    loadout_mass_kg,
    station_allowed,
    store_count_ok,
    validate_loadout,
)
from utils.paths import (
    AIRCRAFT_STATIONS_CSV,
    AIRCRAFT_STORE_LIMITS_CSV,
    STORES_DATABASE_CSV,
)


def test_load_stores_database_mig29_weapons():
    """弹药目录须含 MiG-29 典型空对空/空对地弹药。"""
    stores = load_stores_database(STORES_DATABASE_CSV)
    assert 'rvv_ae' in stores
    assert 'r73e' in stores
    assert 'r27er1' in stores
    assert 'kh29t' in stores
    assert 'tank_2150l' in stores
    assert stores['rvv_ae']['mass_kg'] == pytest.approx(175.0)
    assert stores['built_in_gun']['category'] == 'gun'


def test_load_aircraft_stations_mig29k_nine_stations():
    """MiG-29K 须配置 9 个外部挂点。"""
    stations = load_aircraft_stations(AIRCRAFT_STATIONS_CSV)
    mig = stations['MiG-29K']
    assert len(mig) == 9
    ids = {s['station_id'] for s in mig}
    assert 'centerline' in ids
    assert 'wing_inner_l' in ids
    assert 'wing_outer_r' in ids


def test_station_allowed_r27er_only_inner():
    """R-27ER 仅最内侧挂点允许。"""
    assert station_allowed('MiG-29K', 'wing_inner_l', 'r27er1')
    assert station_allowed('MiG-29K', 'wing_inner_r', 'r27er1')
    assert not station_allowed('MiG-29K', 'wing_mid_inner_l', 'r27er1')
    assert not station_allowed('MiG-29K', 'wing_outer_l', 'r27er1')


def test_station_allowed_active_jammer_only_outer():
    """主动干扰机仅最外侧挂点允许。"""
    assert station_allowed('MiG-29K', 'wing_outer_l', 'active_jammer')
    assert not station_allowed('MiG-29K', 'wing_mid_outer_l', 'active_jammer')


def test_store_count_ok_r27er_max_two():
    """R-27ER 全机最多 2 枚。"""
    ok = {
        'wing_inner_l': 'r27er1',
        'wing_inner_r': 'r27er1',
    }
    assert store_count_ok('MiG-29K', ok)
    over = {
        'wing_inner_l': 'r27er1',
        'wing_inner_r': 'r27er1',
        'wing_mid_inner_l': 'r27er1',
    }
    assert not store_count_ok('MiG-29K', over)


def test_validate_loadout_typical_a2a():
    """典型空战挂载：2×RVV-AE + 2×R-73E。"""
    loadout = {
        'wing_inner_l': 'rvv_ae',
        'wing_inner_r': 'rvv_ae',
        'wing_outer_l': 'r73e',
        'wing_outer_r': 'r73e',
    }
    assert validate_loadout('MiG-29K', loadout) == []


def test_validate_loadout_rejects_wrong_station():
    """次外侧挂点不允许 Kh-29。"""
    loadout = {'wing_mid_outer_l': 'kh29t'}
    errs = validate_loadout('MiG-29K', loadout)
    assert any('不允许' in e for e in errs)


def test_validate_loadout_rejects_over_limit_tank():
    """1,500 L 副油箱全机最多 2 个。"""
    loadout = {
        'wing_inner_l': 'tank_1500l',
        'wing_inner_r': 'tank_1500l',
        'wing_mid_inner_l': 'tank_1500l',
    }
    errs = validate_loadout('MiG-29K', loadout)
    assert any('tank_1500l' in e for e in errs)


def test_loadout_mass_kg_a2a_four_missiles():
    """四枚空对空导弹外挂质量。"""
    loadout = {
        'wing_inner_l': 'rvv_ae',
        'wing_inner_r': 'rvv_ae',
        'wing_outer_l': 'r73e',
        'wing_outer_r': 'r73e',
    }
    mass = loadout_mass_kg(loadout)
    assert mass == pytest.approx(2 * 175 + 2 * 105)


def test_load_aircraft_store_limits_mig29k():
    """MiG-29K 全机弹药上限表可读。"""
    limits = load_aircraft_store_limits(AIRCRAFT_STORE_LIMITS_CSV)
    mig = limits['MiG-29K']
    by_store = {x['store_id']: x['max_count'] for x in mig}
    assert by_store['tank_2150l'] == 1
    assert by_store['active_jammer'] == 2


def test_build_aircraft_stores_payload_structure():
    """catalog 外挂目录须含 stores 与 aircraft 分组。"""
    payload = build_aircraft_stores_payload()
    assert 'stores' in payload
    assert 'aircraft' in payload
    assert 'MiG-29K' in payload['aircraft']
    ac = payload['aircraft']['MiG-29K']
    assert ac['station_count'] == 9
    assert ac['builtin_gun'] == 'built_in_gun'
    store_ids = {s['id'] for s in payload['stores']}
    assert 'rvv_ae' in store_ids
    assert 'active_jammer' in store_ids
