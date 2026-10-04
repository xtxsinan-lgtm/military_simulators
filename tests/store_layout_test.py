"""飞机外挂/挂点模型单元测试。"""
from __future__ import annotations

import pytest

from utils.stores.loadout import (
    effective_n_stores,
    loadout_drag_weight,
    loadout_total_mass_kg,
    parse_loadout_string,
    validate_loadout,
)
from utils.stores.store_catalog import (
    build_store_catalog_payload,
    load_aircraft_loadout_presets_csv,
    load_aircraft_store_layouts_csv,
    load_store_types_csv,
)


def test_load_store_types_has_f14_weapons():
    """弹种目录包含 F-14 典型外挂。"""
    types = load_store_types_csv()
    assert set(types) >= {'aim-9', 'aim-7', 'aim-54', 'tank-280', 'tarps', 'stub-pylon'}
    assert types['aim-54'].mass_kg == pytest.approx(463)
    assert types['aim-9'].store_mount == 'pylon'


def test_f14_store_layout_has_ten_stations():
    """F-14 挂点布局含 1/1b…8/8b 共 10 个挂点。"""
    layouts = load_aircraft_store_layouts_csv()
    f14 = layouts['F-14']
    ids = [s.station_id for s in f14]
    assert ids == ['1', '1b', '2', '3', '4', '5', '6', '7', '8', '8b']


def test_f14_station_allowed_stores():
    """各挂点允许弹种与挂载图表一致。"""
    layouts = load_aircraft_store_layouts_csv()
    by_id = {s.station_id: s for s in layouts['F-14']}
    assert set(by_id['1'].allowed_store_ids) == {'aim-9', 'stub-pylon'}
    assert set(by_id['1b'].allowed_store_ids) == {'aim-7', 'aim-54', 'stub-pylon'}
    assert by_id['2'].allowed_store_ids == ('tank-280',)
    assert set(by_id['5'].allowed_store_ids) == {'aim-7', 'aim-54', 'tarps'}
    assert set(by_id['8b'].allowed_store_ids) == {'aim-7', 'aim-54', 'stub-pylon'}


def test_f14_cap_preset_validates():
    """舰队防空预设通过挂点/弹种校验。"""
    presets = load_aircraft_loadout_presets_csv()['F-14']
    cap = next(p for p in presets if p.preset_id == 'cap')
    items = parse_loadout_string(cap.loadout)
    validate_loadout('F-14', items)
    assert loadout_total_mass_kg(items) == pytest.approx(2 * 85 + 4 * 463 + 2 * 231)


def test_tarps_only_on_station_5():
    """TARPS 仅允许 Station 5。"""
    layouts = load_aircraft_store_layouts_csv()['F-14']
    tarps_stations = [s.station_id for s in layouts if 'tarps' in s.allowed_store_ids]
    assert tarps_stations == ['5']
    items = parse_loadout_string('5:tarps')
    validate_loadout('F-14', items)
    with pytest.raises(ValueError, match='不允许挂载'):
        validate_loadout('F-14', parse_loadout_string('3:tarps'))


def test_tank_only_on_stations_2_and_7():
    """280 加仑副油箱仅 Station 2/7。"""
    layouts = load_aircraft_store_layouts_csv()['F-14']
    tank_stations = [s.station_id for s in layouts if 'tank-280' in s.allowed_store_ids]
    assert tank_stations == ['2', '7']


def test_parse_loadout_rejects_duplicate_station():
    """同一挂点不可重复挂载。"""
    with pytest.raises(ValueError, match='重复挂载'):
        parse_loadout_string('1:aim-9;1:aim-7')


def test_effective_n_stores_cap_loadout():
    """CAP 挂载折算等效阻力权重。"""
    presets = load_aircraft_loadout_presets_csv()['F-14']
    cap = next(p for p in presets if p.preset_id == 'cap')
    items = parse_loadout_string(cap.loadout)
    # 2×0.4 + 4×2.5 + 2×1.0 = 12.8
    assert effective_n_stores(items) == pytest.approx(12.8)
    assert loadout_drag_weight(items) == pytest.approx(12.8)


def test_build_store_catalog_payload_structure():
    """catalog 载荷含 store_types / layouts / presets。"""
    payload = build_store_catalog_payload()
    assert 'store_types' in payload
    assert 'aircraft_store_layouts' in payload
    assert 'aircraft_loadout_presets' in payload
    assert 'F-14' in payload['aircraft_store_layouts']
    assert len(payload['aircraft_store_layouts']['F-14']) == 10
    assert len(payload['aircraft_loadout_presets']['F-14']) == 3
