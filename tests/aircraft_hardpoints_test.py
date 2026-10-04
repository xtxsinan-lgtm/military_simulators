"""战斗机挂点与外挂弹药 CSV / catalog 单元测试。"""
from __future__ import annotations

import pytest

from utils.aircraft_hardpoints import (
    build_aircraft_hardpoints_catalog_payload,
    hardpoints_for_aircraft,
)
from utils.database_csv import (
    load_aircraft_fixed_equipment_csv,
    load_aircraft_hardpoints_csv,
    load_aircraft_stores_csv,
)
from utils.paths import (
    AIRCRAFT_FIXED_EQUIPMENT_CSV,
    AIRCRAFT_STORES_CSV,
    TEJAS_HARDPOINTS_CSV,
)


def test_load_aircraft_stores_csv_has_tejas_weapons():
    """外挂库含光辉常用弹药。"""
    stores = load_aircraft_stores_csv(AIRCRAFT_STORES_CSV)
    assert stores['astra']['typical_mass_kg'] == pytest.approx(154)
    assert stores['aspj']['category'] == 'ecm'
    assert stores['dt_1200']['category'] == 'fuel_tank'


def test_load_aircraft_hardpoints_csv_tejas_station_limits():
    """光辉各挂点限重与允许外挂符合公开挂点表。"""
    rows = {r['station_id']: r for r in load_aircraft_hardpoints_csv(TEJAS_HARDPOINTS_CSV)
            if r['aircraft_id'] == 'Tejas'}
    assert rows['wtip_r']['max_mass_kg'] == pytest.approx(310)
    assert rows['wtip_r']['allowed_stores'] == ['aspj']
    assert rows['mid_l']['max_mass_kg'] == pytest.approx(800)
    assert rows['in_l']['max_mass_kg'] == pytest.approx(1200)
    assert rows['centre']['max_mass_kg'] == pytest.approx(740)
    assert 'derby' in rows['mid_l']['allowed_stores']
    assert 'derby' not in rows['centre']['allowed_stores']
    assert 'dt_1200' in rows['in_l']['allowed_stores']
    assert 'dt_1200' not in rows['mid_l']['allowed_stores']


def test_load_aircraft_fixed_equipment_csv_tejas_cmds():
    """光辉固定设备含 CMDS。"""
    rows = load_aircraft_fixed_equipment_csv(AIRCRAFT_FIXED_EQUIPMENT_CSV)
    tejas = [r for r in rows if r['aircraft_id'] == 'Tejas']
    assert len(tejas) == 1
    assert tejas[0]['equipment_id'] == 'cmds'


def test_hardpoints_for_aircraft_tejas_payload_shape():
    """单机型挂点目录含 stores / stations / fixed_equipment。"""
    hp = hardpoints_for_aircraft('Tejas')
    assert hp is not None
    assert len(hp['stations']) == 8
    assert hp['stores']['astra']['name_zh'] == 'ASTRA 中距空空导弹'
    assert hp['fixed_equipment'][0]['name_zh'].startswith('CMDS')


def test_build_aircraft_hardpoints_catalog_payload():
    """catalog 挂点字段含标签与 Tejas 条目。"""
    payload = build_aircraft_hardpoints_catalog_payload()
    assert payload['position_labels']['outboard'] == '外侧挂点'
    assert 'Tejas' in payload['by_aircraft']
    assert payload['category_labels']['bvr'] == '中距空空导弹'
