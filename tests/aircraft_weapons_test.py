"""战斗机外挂挂点目录单元测试。"""
import pytest

from utils.aircraft_weapons.catalog import (
    build_aircraft_weapons_payload,
    get_aircraft_weapon_stations,
)
from utils.database_csv import load_aircraft_weapon_stations_csv
from utils.paths import AIRCRAFT_WEAPON_STATIONS_CSV


def test_load_aircraft_weapon_stations_csv_gripen():
    """Gripen-CD 挂点 CSV 应含 5 个外挂挂点与固定机炮。"""
    rows = load_aircraft_weapon_stations_csv(AIRCRAFT_WEAPON_STATIONS_CSV)
    gripen = [r for r in rows if r['aircraft_id'] == 'Gripen-CD']
    assert len(gripen) >= 40
    station_ids = {r['station_id'] for r in gripen}
    assert station_ids == {'1', '2', '3', '4', '5', 'G'}


def test_build_aircraft_weapons_payload_groups_by_station():
    """catalog 载荷应按挂点聚合类别与弹药。"""
    payload = build_aircraft_weapons_payload()
    stations = get_aircraft_weapon_stations(payload, 'Gripen-CD')
    assert stations is not None
    assert [s['id'] for s in stations] == ['1', '2', '3', '4', '5', 'G']
    tip = stations[0]
    assert tip['name'] == '翼尖挂架'
    cat_ids = [c['id'] for c in tip['categories']]
    assert 'ir_aam' in cat_ids
    assert 'training' in cat_ids
    ir = next(c for c in tip['categories'] if c['id'] == 'ir_aam')
    names = {w['name'] for w in ir['weapons']}
    assert 'IRIS-T' in names
    assert any('AIM-9L/M' in n for n in names)


def test_gripen_station3_has_heavy_stores():
    """内侧翼下重载挂架应含反舰弹、防区外武器与副油箱。"""
    payload = build_aircraft_weapons_payload()
    stations = get_aircraft_weapon_stations(payload, 'Gripen-CD')
    inner = next(s for s in stations if s['id'] == '3')
    cat_ids = {c['id'] for c in inner['categories']}
    assert {'anti_ship', 'standoff', 'fuel_tank', 'pgbb'} <= cat_ids
    anti_ship = next(c for c in inner['categories'] if c['id'] == 'anti_ship')
    assert any('RBS-15' in w['name'] for w in anti_ship['weapons'])


def test_gripen_fixed_gun_bk27():
    """固定机炮挂点应列出 BK-27。"""
    payload = build_aircraft_weapons_payload()
    stations = get_aircraft_weapon_stations(payload, 'Gripen-CD')
    gun = next(s for s in stations if s['id'] == 'G')
    assert '机炮' in gun['name']
    weapons = gun['categories'][0]['weapons']
    assert any('BK-27' in w['name'] for w in weapons)


def test_a_darter_has_south_africa_note():
    """A-Darter 应保留南非空军备注。"""
    payload = build_aircraft_weapons_payload()
    stations = get_aircraft_weapon_stations(payload, 'Gripen-CD')
    tip = stations[0]
    ir = next(c for c in tip['categories'] if c['id'] == 'ir_aam')
    darter = next(w for w in ir['weapons'] if w['id'] == 'a_darter')
    assert darter.get('notes') == '南非空军'
