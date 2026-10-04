"""MiG-29 外挂挂点模型端到端测试。"""
import pytest

from scripts.frontend_catalog import build_catalog_payload
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV
from utils.stores.stores_config import validate_loadout


@pytest.mark.e2e
def test_catalog_includes_mig29_stores_model():
    """三端 catalog 须含 MiG-29K 九挂点外挂模型。"""
    payload = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    stores = payload['aircraft_stores']
    assert 'MiG-29K' in stores['aircraft']
    mig = stores['aircraft']['MiG-29K']
    assert mig['station_count'] == 9

    # 典型空战挂载经校验链路
    loadout = {
        'wing_inner_l': 'rvv_ae',
        'wing_inner_r': 'rvv_ae',
        'wing_outer_l': 'r73e',
        'wing_outer_r': 'r73e',
    }
    assert validate_loadout('MiG-29K', loadout) == []

    # 对地挂载：最内侧 Kh-29 + 中央副油箱
    strike = {
        'centerline': 'tank_1900l',
        'wing_inner_l': 'kh29t',
        'wing_inner_r': 'kh29t',
    }
    assert validate_loadout('MiG-29K', strike) == []


@pytest.mark.e2e
def test_mig29_stores_inner_vs_outer_capability():
    """最内侧与最外侧挂点能力差异须与 MRCA 示意图一致。"""
    payload = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    stations = {
        s['station_id']: s
        for s in payload['aircraft_stores']['aircraft']['MiG-29K']['stations']
    }
    inner = set(stations['wing_inner_l']['allowed_stores'])
    outer = set(stations['wing_outer_l']['allowed_stores'])
    assert 'r27er1' in inner
    assert 'r27er1' not in outer
    assert 'active_jammer' in outer
    assert 'active_jammer' not in inner
    assert 'kh29t' in inner
    assert 'kh29t' not in outer
