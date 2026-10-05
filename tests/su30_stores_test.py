"""苏-30 挂载模型单元测试。"""
from __future__ import annotations

import pytest

from utils.database_csv import (
    load_su30_store_compatibility_csv,
    load_su30_store_database_csv,
    load_su30_store_limits_csv,
    load_su30_store_stations_csv,
)
from utils.paths import (
    SU30_STORE_COMPATIBILITY_CSV,
    SU30_STORE_DATABASE_CSV,
    SU30_STORE_LIMITS_CSV,
    SU30_STORE_STATIONS_CSV,
)
from utils.weapon_loadout.su30_stores import (
    SU30_AIRCRAFT_ID,
    SU30_EXTERNAL_STATION_COUNT,
    aircraft_weapon_max_count,
    build_su30_stores_payload,
    station_weapon_max_qty,
    validate_su30_loadout,
)
from utils.weapon_loadout.typhoon_stores import build_weapon_loadout_catalog_payload


def test_su30_csv_files_exist():
    """苏-30 数据文件路径有效。"""
    assert SU30_STORE_DATABASE_CSV.is_file()
    assert SU30_STORE_STATIONS_CSV.is_file()
    assert SU30_STORE_COMPATIBILITY_CSV.is_file()
    assert SU30_STORE_LIMITS_CSV.is_file()


def test_load_su30_store_stations_csv_twelve():
    """挂点 CSV 应为 1–12 连续编号。"""
    stations = load_su30_store_stations_csv()
    assert len(stations) == 12
    assert [s['station_id'] for s in stations] == list(range(1, 13))
    assert stations[0]['side'] == 'left'
    assert stations[11]['side'] == 'right'
    assert stations[5]['mount'] == 'centerline'
    assert stations[6]['mount'] == 'centerline'


def test_load_su30_store_database_has_chart_weapons():
    """弹药库须覆盖挂载图列出的主要型号。"""
    weapons = {w['id'] for w in load_su30_store_database_csv()}
    for wid in (
        'r27r1', 'r27er1', 'r27t1', 'r27et1', 'r27p1', 'r27ep1',
        'rvv_ae', 'r73e', 'kh59me', 'kh59mk', 'kh35e', 'kh31a', 'kh31p',
        'kh29t', 'kh29te', 'kh29l', 'kab500kr', 'kab1500kr', 'apk9e',
        'fab500', 'fab250', 'ofab100', 's8_b8m1', 's13_b13l', 's25', 'p50t',
    ):
        assert wid in weapons


def test_load_su30_store_compatibility_r73e_wing_outer():
    """R-73E 仅 1/2/3/10/11/12，各 1 枚。"""
    rows = load_su30_store_compatibility_csv()
    r73 = [r for r in rows if r['weapon_id'] == 'r73e']
    assert {r['station_id'] for r in r73} == {1, 2, 3, 10, 11, 12}
    assert all(r['max_qty'] == 1 for r in r73)


def test_load_su30_store_compatibility_fab250_multi_rack():
    """FAB-250：翼中侧各 6、翼内/进气各 2、机腹各 4。"""
    rows = load_su30_store_compatibility_csv()
    by_st = {r['station_id']: r['max_qty'] for r in rows if r['weapon_id'] == 'fab250'}
    assert by_st[3] == 6 and by_st[10] == 6
    assert by_st[4] == 2 and by_st[9] == 2
    assert by_st[5] == 2 and by_st[8] == 2
    assert by_st[6] == 4 and by_st[7] == 4
    assert sum(by_st.values()) == 28


def test_load_su30_store_limits_chart_totals():
    """全机上限与挂载图右侧标注一致。"""
    limits = {r['store_id']: r['max_count'] for r in load_su30_store_limits_csv()}
    assert limits['r27r1'] == 6
    assert limits['r27t1'] == 2
    assert limits['rvv_ae'] == 6
    assert limits['r73e'] == 6
    assert limits['kh59me'] == 2
    assert limits['apk9e'] == 1
    assert limits['kh59mk'] == 4
    assert limits['kab1500kr'] == 3
    assert limits['fab250'] == 28
    assert limits['ofab100'] == 32
    assert limits['s8_b8m1'] == 4
    assert limits['s13_b13l'] == 4


def test_build_su30_stores_payload_structure():
    """payload 含 12 挂点、武器与全机上限。"""
    payload = build_su30_stores_payload()
    assert payload['aircraft_id'] == SU30_AIRCRAFT_ID
    assert payload['external_station_count'] == SU30_EXTERNAL_STATION_COUNT
    assert len(payload['stations']) == 12
    assert payload['stations'][0]['id'] == 1
    assert payload['stations'][-1]['id'] == 12
    assert any(w['id'] == 'kh59me' for w in payload['weapons'])
    assert any(x['store_id'] == 'apk9e' for x in payload['limits'])


def test_station_weapon_max_qty_and_aircraft_limit():
    """单点与全机上限查询。"""
    payload = build_su30_stores_payload()
    assert station_weapon_max_qty(payload, 3, 'fab250') == 6
    assert station_weapon_max_qty(payload, 1, 'fab250') == 0
    assert station_weapon_max_qty(payload, 5, 'apk9e') == 1
    assert aircraft_weapon_max_count(payload, 'apk9e') == 1
    assert aircraft_weapon_max_count(payload, 'kab1500kr') == 3


def test_validate_su30_loadout_rejects_over_station_qty():
    """超过单挂点数量应报错。"""
    errs = validate_su30_loadout({3: {'weapon_id': 'fab250', 'qty': 7}})
    assert errs
    assert any('最多 6' in e for e in errs)


def test_validate_su30_loadout_rejects_apk9e_double():
    """APK-9E 全机最多 1 个。"""
    errs = validate_su30_loadout({
        5: {'weapon_id': 'apk9e', 'qty': 1},
        8: {'weapon_id': 'apk9e', 'qty': 1},
    })
    assert any('apk9e' in e and '最多 1' in e for e in errs)


def test_validate_su30_loadout_allows_full_a2a():
    """满载空战构型（6×R-73E + 6×RVV-AE）合法。"""
    sel = {sid: {'weapon_id': 'r73e', 'qty': 1} for sid in (1, 2, 3, 10, 11, 12)}
    sel.update({sid: {'weapon_id': 'rvv_ae', 'qty': 1} for sid in (4, 5, 6, 7, 8, 9)})
    assert validate_su30_loadout(sel) == []


def test_build_weapon_loadout_catalog_includes_su30():
    """weapon_loadout 根节点含 su30。"""
    root = build_weapon_loadout_catalog_payload()
    assert 'su30' in root
    assert root['su30']['aircraft_id'] == 'Su-30'
    assert len(root['su30']['stations']) == 12


def test_r27t_family_inner_wing_only():
    """R-27T1/ET1/P1/EP1 仅翼内侧 4/9。"""
    payload = build_su30_stores_payload()
    for wid in ('r27t1', 'r27et1', 'r27p1', 'r27ep1'):
        allowed = [
            st['id'] for st in payload['stations']
            if station_weapon_max_qty(payload, st['id'], wid) > 0
        ]
        assert allowed == [4, 9], wid
