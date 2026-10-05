"""歼-10C 挂载模型单元测试。"""
import pytest

from utils.aircraft_mount.j10c_mount import (
    build_j10c_mount_catalog_payload,
    build_j10c_mount_model,
    station_store_allowed,
    stores_for_station,
)
from utils.combat_radius.combat_radius_loadout_images import loadout_image_filename
from utils.combat_radius.loadout import build_loadout_catalog_payload, resolve_loadout


def test_j10c_has_eleven_stations():
    """歼-10C 应有 1–11 号共 11 个挂点，6 号为机腹。"""
    model = build_j10c_mount_model()
    ids = [s['station_id'] for s in model['stations']]
    assert ids == [str(i) for i in range(1, 12)]
    by_id = {s['station_id']: s for s in model['stations']}
    assert by_id['6']['side'] == 'center'
    assert by_id['1']['position'] == by_id['11']['position'] == 'wing_tip'


def test_j10c_station_rules():
    """各挂点的武器兼容规则符合挂载图。"""
    model = build_j10c_mount_model()
    tip = {x['id'] for x in stores_for_station(model, '1')}
    assert tip == {'pl10', 'pl8', 'r73e'}
    assert tip == {x['id'] for x in stores_for_station(model, '11')}
    assert station_store_allowed(model, '2', 'pl15_x2')
    assert station_store_allowed(model, '10', 'cm400akg')
    assert station_store_allowed(model, '3', 'tank_1500l')
    assert not station_store_allowed(model, '3', 'pl15_x2')
    assert station_store_allowed(model, '4', 'yingsun3')
    assert not station_store_allowed(model, '5', 'kg600')
    assert {x['id'] for x in stores_for_station(model, '6')} == {
        'tank_1000l', 'pl15_x2', 'pl12_x2', 'r77_x2',
    }


def test_j10c_catalog_payload_and_image():
    """前端 payload 含歼-10C 模型与挂载图映射。"""
    payload = build_j10c_mount_catalog_payload()
    assert payload['aircraft_ids'] == ['J-10C']
    assert len(payload['stations']) == 11
    assert loadout_image_filename('J-10C') == 'j10c.jpg'


def test_j10c_in_unified_loadout_catalog():
    """作战半径统一 catalog 含歼-10C，默认挂载可解算。"""
    cat = build_loadout_catalog_payload()
    ac = cat['aircraft']['J-10C']
    assert len(ac['stations']) == 11
    assert ac['default_selection']['1'] == 'pl10@1'
    summary = resolve_loadout('J-10C', ac['default_selection'])
    assert summary.weapons_mass_kg == pytest.approx(2 * 89 + 2 * 210 + 2 * 199)
    tank = {
        '3': 'tank_1500l@1', '9': 'tank_1500l@1', '6': 'tank_1000l@1',
    }
    with_tanks = resolve_loadout('J-10C', tank)
    assert with_tanks.tank_dry_mass_kg > 0
