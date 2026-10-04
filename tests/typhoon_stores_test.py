"""台风挂点与弹药兼容目录单元测试。"""
from __future__ import annotations

import pytest

from utils.database_csv import (
    load_typhoon_store_compatibility_csv,
    load_typhoon_store_stations_csv,
    load_weapon_store_csv,
)
from utils.paths import (
    TYPHOON_STORE_COMPATIBILITY_CSV,
    TYPHOON_STORE_STATIONS_CSV,
    WEAPON_STORE_CSV,
)
from utils.weapon_loadout.typhoon_stores import (
    TYPHOON_EXTERNAL_STATION_COUNT,
    build_typhoon_stores_payload,
    build_weapon_loadout_catalog_payload,
)


def test_weapon_store_csv_loads_all_typhoon_weapons():
    """武器库应包含用户清单中的全部弹种。"""
    weapons = load_weapon_store_csv(WEAPON_STORE_CSV)
    ids = {item['id'] for item in weapons}
    expected = {
        'amraam', 'bvraam', 'aim9', 'asraam', 'iris_t', 'sky_flash', 'aspide',
        'lgb', 'jdam', 'alarm', 'harm', 'storm_shadow', 'taurus',
        'brimstone', 'bl755', 'dws39', 'harpoon', 'penguin', 'fuel', 'bk27',
    }
    assert expected <= ids


def test_typhoon_stations_left_to_right_numbering():
    """挂点按图表从左至右编号 1–10。"""
    stations = load_typhoon_store_stations_csv(TYPHOON_STORE_STATIONS_CSV)
    assert len(stations) == 10
    assert [item['station_id'] for item in sorted(stations, key=lambda x: x['position_index'])] == list(range(1, 11))
    assert stations[0]['name'] == '左翼最外侧挂点'
    assert stations[-1]['name'] == '内置固定武器'
    assert stations[-1]['mount'] == 'fixed'


def test_station1_outer_wing_single_rack_a2a_and_strike():
    """1 号挂点：各弹种单枚。"""
    payload = build_typhoon_stores_payload()
    station = next(s for s in payload['stations'] if s['id'] == 1)
    by_weapon = {item['weapon_id']: item for item in station['stores']}
    for weapon_id in ('amraam', 'bvraam', 'aim9', 'asraam', 'iris_t'):
        assert by_weapon[weapon_id]['max_qty'] == 1
        assert by_weapon[weapon_id]['category'] == 'a2a'
    for weapon_id in ('lgb', 'jdam', 'alarm', 'harm'):
        assert by_weapon[weapon_id]['max_qty'] == 1
        assert by_weapon[weapon_id]['category'] == 'pgm'
    for weapon_id in ('brimstone', 'bl755', 'dws39'):
        assert by_weapon[weapon_id]['max_qty'] == 1
    for weapon_id in ('harpoon', 'penguin'):
        assert by_weapon[weapon_id]['max_qty'] == 1
        assert by_weapon[weapon_id]['category'] == 'asm'


def test_station2_dual_rack_wvr_and_cruise():
    """2 号挂点：中距弹单枚，近距弹双联装；含巡航导弹。"""
    payload = build_typhoon_stores_payload()
    station = next(s for s in payload['stations'] if s['id'] == 2)
    by_weapon = {item['weapon_id']: item for item in station['stores']}
    assert by_weapon['amraam']['max_qty'] == 1
    assert by_weapon['bvraam']['max_qty'] == 1
    assert by_weapon['aim9']['max_qty'] == 2
    assert by_weapon['asraam']['max_qty'] == 2
    assert by_weapon['iris_t']['max_qty'] == 2
    assert by_weapon['storm_shadow']['max_qty'] == 1
    assert by_weapon['taurus']['max_qty'] == 1


def test_station3_inner_wing_dual_lgb_jdam_and_fuel():
    """3 号挂点：LGB/JDAM/BL-755 双联装，可挂副油箱。"""
    payload = build_typhoon_stores_payload()
    station = next(s for s in payload['stations'] if s['id'] == 3)
    by_weapon = {item['weapon_id']: item for item in station['stores']}
    assert by_weapon['lgb']['max_qty'] == 2
    assert by_weapon['jdam']['max_qty'] == 2
    assert by_weapon['bl755']['max_qty'] == 2
    assert by_weapon['fuel']['max_qty'] == 1
    assert by_weapon['fuel']['category'] == 'aux'


def test_station4_semi_recessed_bvr_pairs():
    """4 号半埋挂点：AMRAAM/BVRAAM 各 2 枚，另含 SKY FLASH / ASPIDE。"""
    payload = build_typhoon_stores_payload()
    station = next(s for s in payload['stations'] if s['id'] == 4)
    assert station['mount'] == 'semi_recessed'
    by_weapon = {item['weapon_id']: item for item in station['stores']}
    assert by_weapon['amraam']['max_qty'] == 2
    assert by_weapon['bvraam']['max_qty'] == 2
    assert by_weapon['sky_flash']['max_qty'] == 1
    assert by_weapon['aspide']['max_qty'] == 1


def test_station5_centerline_cruise_and_fuel():
    """5 号机腹中心：精确制导弹 + 副油箱。"""
    payload = build_typhoon_stores_payload()
    station = next(s for s in payload['stations'] if s['id'] == 5)
    assert station['mount'] == 'centerline'
    ids = {item['weapon_id'] for item in station['stores']}
    assert ids == {'lgb', 'storm_shadow', 'taurus', 'jdam', 'fuel'}


def test_station6_mirrors_station4():
    """6 号半埋挂点与 4 号对称。"""
    payload = build_typhoon_stores_payload()
    left = next(s for s in payload['stations'] if s['id'] == 4)
    right = next(s for s in payload['stations'] if s['id'] == 6)
    assert left['stores'] == right['stores']


def test_right_wing_stations_mirror_left():
    """7/8/9 号挂点分别与 3/2/1 号对称。"""
    payload = build_typhoon_stores_payload()
    by_id = {s['id']: s for s in payload['stations']}
    assert by_id[7]['stores'] == by_id[3]['stores']
    assert by_id[8]['stores'] == by_id[2]['stores']
    assert by_id[9]['stores'] == by_id[1]['stores']


def test_station10_bk27_cannon():
    """10 号内置航炮：BK-27。"""
    payload = build_typhoon_stores_payload()
    station = next(s for s in payload['stations'] if s['id'] == 10)
    assert station['mount'] == 'fixed'
    assert len(station['stores']) == 1
    assert station['stores'][0]['weapon_id'] == 'bk27'
    assert station['stores'][0]['name'] == 'BK-27'
    assert '27 mm' in station['stores'][0]['notes']


def test_external_station_count_is_thirteen():
    """目录元数据：13 个外挂位 + 半埋物理站位说明。"""
    payload = build_typhoon_stores_payload()
    assert payload['external_station_count'] == TYPHOON_EXTERNAL_STATION_COUNT == 13
    assert payload['semi_recessed_physical_count'] == 4
    assert payload['aircraft_id'] == 'Typhoon'


def test_compatibility_csv_covers_every_station():
    """兼容表每个逻辑挂点至少一条记录。"""
    stations = load_typhoon_store_stations_csv(TYPHOON_STORE_STATIONS_CSV)
    compat = load_typhoon_store_compatibility_csv(TYPHOON_STORE_COMPATIBILITY_CSV)
    covered = {int(row['station_id']) for row in compat}
    assert covered == {int(row['station_id']) for row in stations}


def test_build_weapon_loadout_catalog_has_typhoon():
    """前端 catalog 根节点含 typhoon 子目录。"""
    catalog = build_weapon_loadout_catalog_payload()
    assert 'typhoon' in catalog
    assert catalog['typhoon']['aircraft_name'] == '台风'
    assert len(catalog['typhoon']['stations']) == 10


def test_unknown_weapon_in_compatibility_raises():
    """兼容表引用未知武器时应报错。"""
    weapons = load_weapon_store_csv(WEAPON_STORE_CSV)
    stations = load_typhoon_store_stations_csv(TYPHOON_STORE_STATIONS_CSV)
    compat = load_typhoon_store_compatibility_csv(TYPHOON_STORE_COMPATIBILITY_CSV)
    bad = [dict(row) for row in compat]
    bad[0] = dict(bad[0], weapon_id='no_such_weapon')
    with pytest.raises(ValueError, match='未知武器'):
        build_typhoon_stores_payload(weapons=weapons, stations=stations, compatibility=bad)
