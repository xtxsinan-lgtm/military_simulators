"""外挂挂点与挂载方案单元测试。"""
from __future__ import annotations

import pytest

from utils.stores.hardpoints import (
    build_stores_catalog_payload,
    lb_to_kg,
    load_aircraft_hardpoint_stores_csv,
    load_aircraft_hardpoints_csv,
    load_loadout_presets_csv,
    load_stores_csv,
    loadout_mass_kg,
    preset_to_loadout,
    validate_loadout,
)
from utils.paths import (
    AIRCRAFT_HARDPOINT_STORES_CSV,
    AIRCRAFT_HARDPOINTS_CSV,
    LOADOUT_PRESETS_CSV,
    STORES_CSV,
)


def test_lb_to_kg():
    """磅千克换算。"""
    assert lb_to_kg(250) == pytest.approx(113.3980925)
    assert lb_to_kg(1250) == pytest.approx(566.9904625)
    assert lb_to_kg(2250) == pytest.approx(1020.5828625)


def test_fa50_has_seven_hardpoints():
    """FA-50 共 7 个挂点。"""
    hp = load_aircraft_hardpoints_csv()
    stations = hp['FA-50']
    assert len(stations) == 7
    ids = {s['station_id'] for s in stations}
    assert ids == {'tip_l', 'tip_r', 'out_l', 'out_r', 'in_l', 'in_r', 'center'}


def test_fa50_wingtip_only_aim9():
    """翼尖挂点仅允许 AIM-9 × 1。"""
    allowed = load_aircraft_hardpoint_stores_csv()['FA-50']
    for sid in ('tip_l', 'tip_r'):
        items = allowed[sid]
        assert len(items) == 1
        assert items[0]['store_id'] == 'aim9'
        assert items[0]['max_count'] == 1


def test_fa50_inner_station_mk82_triple():
    """内侧翼下挂点允许 MK-82 × 3。"""
    allowed = load_aircraft_hardpoint_stores_csv()['FA-50']['in_l']
    mk82 = next(x for x in allowed if x['store_id'] == 'mk82')
    assert mk82['max_count'] == 3


def test_fa50_center_no_maverick():
    """机腹中心挂点无小牛导弹。"""
    allowed = load_aircraft_hardpoint_stores_csv()['FA-50']['center']
    store_ids = {x['store_id'] for x in allowed}
    assert 'maverick' not in store_ids
    assert store_ids == {'tank150', 'mk82', 'mk20'}


def test_fa50_load_factor_g():
    """结构载荷系数与资料一致。"""
    hp = {s['station_id']: s for s in load_aircraft_hardpoints_csv()['FA-50']}
    assert hp['tip_l']['load_factor_g'] == pytest.approx(8.0)
    assert hp['out_l']['load_factor_g'] == pytest.approx(5.5)
    assert hp['in_l']['load_factor_g'] == pytest.approx(5.5)
    assert hp['center']['load_factor_g'] == pytest.approx(4.5)


def test_fa50_max_mass_limits():
    """各挂点最大允许重量（lb → kg）。"""
    hp = {s['station_id']: s for s in load_aircraft_hardpoints_csv()['FA-50']}
    assert hp['tip_l']['max_mass_lb'] == pytest.approx(250)
    assert hp['tip_l']['max_mass_kg'] == pytest.approx(lb_to_kg(250), abs=0.15)
    assert hp['out_l']['max_mass_lb'] == pytest.approx(1250)
    assert hp['in_l']['max_mass_lb'] == pytest.approx(2250)
    assert hp['center']['max_mass_lb'] == pytest.approx(2250)


def test_validate_loadout_accepts_a2a_preset():
    """空战预设（双 AIM-9）应通过校验。"""
    presets = load_loadout_presets_csv()['FA-50']
    a2a = next(p for p in presets if p['id'] == 'fa50_a2a_tip')
    loadout = preset_to_loadout(a2a)
    errors = validate_loadout('FA-50', loadout)
    assert errors == []


def test_validate_loadout_rejects_overweight_station():
    """单挂点超重应报错。"""
    loadout = {'in_l': [('mk82', 3)]}  # 681 kg > 1020.6，单独 OK
    assert validate_loadout('FA-50', loadout) == []
    loadout_heavy = {'in_l': [('mk82', 3), ('maverick', 2), ('tank150', 1)]}
    errors = validate_loadout('FA-50', loadout_heavy)
    assert any('超过上限' in e for e in errors)


def test_validate_loadout_rejects_disallowed_store():
    """不允许的弹药应报错。"""
    loadout = {'center': [('aim9', 1)]}
    errors = validate_loadout('FA-50', loadout)
    assert any('不允许挂载' in e for e in errors)


def test_validate_loadout_rejects_excess_count():
    """超过允许数量应报错。"""
    loadout = {'tip_l': [('aim9', 2)]}
    errors = validate_loadout('FA-50', loadout)
    assert any('超过上限' in e for e in errors)


def test_loadout_mass_kg_sums_stores():
    """挂载总重为各弹药质量之和。"""
    stores = load_stores_csv()
    loadout = {'tip_l': [('aim9', 1)], 'tip_r': [('aim9', 1)]}
    mass = loadout_mass_kg(loadout, stores)
    assert mass == pytest.approx(2 * stores['aim9']['mass_kg'])


def test_build_stores_catalog_payload_fa50():
    """目录 payload 含 FA-50 七挂点与预设。"""
    payload = build_stores_catalog_payload()
    assert len(payload['stores']) >= 8
    fa50 = next(a for a in payload['aircraft'] if a['aircraft_id'] == 'FA-50')
    assert len(fa50['stations']) == 7
    assert len(fa50['loadout_presets']) >= 3
    tip = next(s for s in fa50['stations'] if s['station_id'] == 'tip_l')
    assert len(tip['allowed_stores']) == 1
    assert tip['allowed_stores'][0]['store_id'] == 'aim9'


def test_csv_files_exist():
    """数据文件存在且可读。"""
    assert STORES_CSV.is_file()
    assert AIRCRAFT_HARDPOINTS_CSV.is_file()
    assert AIRCRAFT_HARDPOINT_STORES_CSV.is_file()
    assert LOADOUT_PRESETS_CSV.is_file()
    load_stores_csv()
    load_aircraft_hardpoints_csv()
    load_aircraft_hardpoint_stores_csv()
    load_loadout_presets_csv()
