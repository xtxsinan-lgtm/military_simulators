"""飞机挂点挂载模型单元测试。"""
from __future__ import annotations

import pytest

from utils.aircraft_pylon import (
    build_aircraft_pylon_payload,
    get_pylon_model,
    physical_station_count,
    station_allows_store,
)
from utils.database_csv import load_aircraft_pylon_csv
from utils.paths import AIRCRAFT_PYLON_CSV


def test_load_gripen_ef_pylon_csv_has_seven_stations():
    """鹰狮 E/F 应有 7 个逻辑挂点（1–4、5R、5C、5L）。"""
    rows = load_aircraft_pylon_csv(AIRCRAFT_PYLON_CSV)
    gripen = [row for row in rows if row['aircraft_id'] == 'Gripen-EF']
    assert len(gripen) == 7
    assert [row['station_id'] for row in gripen] == ['1', '2', '3', '4', '5R', '5C', '5L']


def test_gripen_station1_allows_ir_and_aacmi():
    """挂点 1（翼尖）仅允许红外弹与 AACMI 吊舱。"""
    stations = get_pylon_model('Gripen-EF')
    assert stations is not None
    wingtip = next(s for s in stations if s['station_id'] == '1')
    assert wingtip['symmetric'] is True
    assert wingtip['position'] == 'wingtip'
    assert set(wingtip['allowed_stores']) == {'a2a_ir', 'aacmi_pod'}


def test_gripen_station3_allows_fuel_tank_and_sdb():
    """挂点 3（内侧翼下）允许副油箱与小直径炸弹。"""
    stations = get_pylon_model('Gripen-EF')
    assert stations is not None
    inner = next(s for s in stations if s['station_id'] == '3')
    assert 'fuel_tank' in inner['allowed_stores']
    assert 'sdb' in inner['allowed_stores']
    assert 'sdb_alt' in inner['allowed_stores']


def test_gripen_station4_intake_right_not_symmetric():
    """挂点 4 为进气道右侧，非对称。"""
    stations = get_pylon_model('Gripen-EF')
    assert stations is not None
    intake = next(s for s in stations if s['station_id'] == '4')
    assert intake['symmetric'] is False
    assert set(intake['allowed_stores']) == {'recce_pod', 'flir_ldp', 'ecm_pod'}


def test_gripen_belly_stations_differ():
    """机腹三挂点（5R/5C/5L）允许挂载类型不同。"""
    stations = get_pylon_model('Gripen-EF')
    assert stations is not None
    by_id = {s['station_id']: s for s in stations}
    assert 'smart_bomb' in by_id['5R']['allowed_stores']
    assert 'smart_bomb' in by_id['5C']['allowed_stores']
    assert 'smart_bomb' not in by_id['5L']['allowed_stores']
    assert 'fuel_tank' in by_id['5C']['allowed_stores']
    assert 'anti_ship' in by_id['5L']['allowed_stores']


def test_physical_station_count_for_gripen():
    """鹰狮 E/F 物理挂点：对称 1/2/3 各 2 个 + 4/5R/5C/5L 各 1 个 = 10。"""
    stations = get_pylon_model('Gripen-EF')
    assert stations is not None
    assert physical_station_count(stations) == 10


def test_station_allows_store():
    """station_allows_store 按 allowed_stores 判断。"""
    station = {'allowed_stores': ['a2a_ir', 'ecm_pod']}
    assert station_allows_store(station, 'a2a_ir') is True
    assert station_allows_store(station, 'a2a_radar') is False


def test_build_payload_includes_store_type_labels():
    """catalog 载荷应含 store 类型中文标签与 Gripen-EF 模型。"""
    payload = build_aircraft_pylon_payload()
    assert payload['store_types']['a2a_ir'] == '红外制导空空导弹'
    assert payload['store_types']['sdb_alt'] == '替代型小直径炸弹'
    assert 'Gripen-EF' in payload['models']
    model = payload['models']['Gripen-EF']
    assert model['station_count'] == 7
    assert model['physical_station_count'] == 10


def test_unknown_store_type_rejected(tmp_path):
    """CSV 中未知 store 类型应报错。"""
    bad_csv = tmp_path / 'bad_pylon.csv'
    bad_csv.write_text(
        'aircraft_id,station_id,label,position,symmetric,allowed_stores,notes\n'
        'Gripen-EF,1,翼尖,wingtip,1,unknown_type,\n',
        encoding='utf-8-sig',
    )
    with pytest.raises(ValueError, match='未知 store 类型'):
        load_aircraft_pylon_csv(bad_csv)
