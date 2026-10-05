"""歼-15 / 歼-15T 挂载模型单元测试。"""
import pytest

from utils.aircraft_mount.j15_mount import (
    build_j15_mount_catalog_payload,
    build_j15_mount_model,
    station_store_allowed,
    stores_for_station,
)
from utils.combat_radius.combat_radius_loadout_images import loadout_image_filename
from utils.combat_radius.loadout import build_loadout_catalog_payload, resolve_loadout


def test_j15t_station_rules():
    """歼-15T 12 挂点兼容规则与需求一致，且左右对称。"""
    model = build_j15_mount_model('J-15T')
    assert [s['station_id'] for s in model['stations']] == [str(i) for i in range(1, 13)]
    ids = lambda sid: {x['id'] for x in stores_for_station(model, sid)}
    assert ids('1') == ids('12') == ids('2') == ids('11') == {'pl10', 'pl8'}
    assert ids('3') == ids('10')
    assert ids('4') == ids('9')
    assert ids('5') == ids('8')
    assert ids('6') == ids('7') == {'pl15', 'pl12'}
    assert station_store_allowed(model, '4', 'yj15')
    assert station_store_allowed(model, '4', 'gb_1500')
    assert not station_store_allowed(model, '3', 'yj62')
    assert station_store_allowed(model, '5', 'kd88_pod')


def test_j15_has_no_pl15_pl10_yj15():
    """歼-15 参照歼-15T，但无 PL-10 / PL-15 / 鹰击-15。"""
    model = build_j15_mount_model('J-15')
    every = {x['id'] for items in model['stores_by_station'].values() for x in items}
    assert not every & {'pl10', 'pl15', 'yj15'}
    assert {'pl8', 'pl12', 'yj62'} <= every
    assert {x['id'] for x in stores_for_station(model, '1')} == {'pl8'}


def test_j15_catalog_payload_and_image():
    payload = build_j15_mount_catalog_payload()
    assert payload['aircraft_ids'] == ['J-15', 'J-15T']
    assert len(payload['models']['J-15T']['stations']) == 12
    assert loadout_image_filename('J-15T') == 'j15.jpg'


def test_j15_in_unified_loadout_catalog():
    """统一 catalog 含两型，默认挂载与多联挂架数量可解算。"""
    cat = build_loadout_catalog_payload()
    t = cat['aircraft']['J-15T']
    assert len(t['stations']) == 12
    summary = resolve_loadout('J-15T', t['default_selection'])
    assert summary.weapons_mass_kg == pytest.approx(4 * 89 + 4 * 210)
    st3 = next(s for s in t['stations'] if s['id'] == '3')
    assert any(o['munition_id'] == 'gb_250' and o['qty'] == 4 for o in st3['options'])
    j = cat['aircraft']['J-15']
    assert not any(
        o['munition_id'] in ('pl15', 'pl10', 'yj15')
        for s in j['stations'] for o in s['options']
    )
    resolve_loadout('J-15', j['default_selection'])
