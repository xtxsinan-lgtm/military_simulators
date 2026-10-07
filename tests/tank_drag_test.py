"""副油箱阻力随油箱增大：挂架缩放、尾翼浸润、钝头形阻。"""
from __future__ import annotations

import pytest

from utils.combat_radius.lift_drag import (
    STORE_CF,
    STORE_FORM_CD,
    StoreSpec,
    _store_specs_from_dict,
    store_spec_front_m2,
    store_spec_wetted_m2,
)
from utils.combat_radius.loadout import (
    _aero_for_mount_style,
    load_munitions,
    pylon_size_scale,
    resolve_loadout,
)


def _spec(mid: str, style: str = 'wing_pylon') -> StoreSpec:
    """按 loadout 的方式由弹药库构造外挂件。"""
    m = load_munitions()[mid]
    a = _aero_for_mount_style(style, 1, m['length_m'], m['diameter_m'])
    return StoreSpec(
        length_m=m['length_m'], diameter_m=m['diameter_m'], count=1, mount='pylon',
        pylon_wetted_m2=a['pylon_wetted_m2'], pylon_front_m2=a['pylon_front_m2'],
        exposed_frac=a['exposed_frac'], interf=a['interf'], front_frac=a['front_frac'],
        tank=m['fuel_kg'] > 0, style=style,
    )


def _cda(spec: StoreSpec) -> float:
    """外挂阻力面积 CdA（m²）。"""
    return STORE_CF * store_spec_wetted_m2(spec) + STORE_FORM_CD * store_spec_front_m2(spec)


def test_pylon_scale_is_one_for_reference_aam_and_grows_with_size():
    """中距弹挂架系数≈1，随外挂长/径增大，有上下限。"""
    assert pylon_size_scale(3.65, 0.178) == pytest.approx(1.0)
    assert pylon_size_scale(5.0, 0.65) > pylon_size_scale(4.2, 0.58) > pylon_size_scale(3.65, 0.178)
    assert pylon_size_scale(30.0, 3.0) == pytest.approx(4.0)
    assert pylon_size_scale(0.5, 0.05) == pytest.approx(0.6)
    assert pylon_size_scale(0.0, 0.0) == pytest.approx(1.0)


def test_pylon_area_scales_with_store_size():
    """大外挂的挂架浸润/迎风比小外挂大。"""
    small = _aero_for_mount_style('wing_pylon', 1, 3.65, 0.178)
    big = _aero_for_mount_style('wing_pylon', 1, 5.0, 0.65)
    assert big['pylon_wetted_m2'] > 2 * small['pylon_wetted_m2']
    assert big['pylon_front_m2'] > 2 * small['pylon_front_m2']
    legacy = _aero_for_mount_style('wing_pylon', 1)
    assert legacy['pylon_wetted_m2'] == pytest.approx(0.35)


def test_tank_drag_grows_with_tank_size():
    """油箱越大阻力面积越大（含挂架、尾翼、形阻）。"""
    ids = ['tank150', 'tank_1000l', 'tank_1500l', 'drop_tank_480', 'drop_tank_610']
    cda = [_cda(_spec(i)) for i in ids]
    assert cda == sorted(cda)
    assert cda[-1] > 1.5 * cda[0]


def test_tank_has_fins_and_blunt_form_drag():
    """同尺寸下油箱比弹体多尾翼浸润与更大形阻。"""
    base = _spec('tank_1500l')
    plain = StoreSpec(**{**base.__dict__, 'tank': False})
    assert store_spec_wetted_m2(base) > store_spec_wetted_m2(plain)
    assert store_spec_front_m2(base) > store_spec_front_m2(plain)
    assert _cda(base) > 1.1 * _cda(plain)


def test_bigger_tank_has_higher_drag_per_tank_but_lower_per_litre():
    """单个阻力随尺寸增大；同时大油箱单位燃油阻力更小（面容比规律仍成立）。"""
    m = load_munitions()
    small, big = _spec('tank_1000l'), _spec('tank_1500l')
    assert _cda(big) > _cda(small)
    assert _cda(big) / m['tank_1500l']['fuel_kg'] < _cda(small) / m['tank_1000l']['fuel_kg']


def test_resolve_loadout_marks_tanks_and_scales_pylon():
    """挂载解析：油箱带 tank 标记且挂架更大；导弹不带。"""
    s = resolve_loadout('J-10C', {'3': 'tank_1500l@1', '1': 'pl10@1'})
    by_id = {x.station_id: x for x in s.store_specs}
    assert by_id['3'].tank is True and by_id['1'].tank is False
    assert by_id['3'].pylon_wetted_m2 > 2 * by_id['1'].pylon_wetted_m2


def test_store_specs_dict_roundtrip_keeps_tank_flag():
    """store_specs 字典解析保留 tank 标记。"""
    specs = _store_specs_from_dict([
        {'length_m': 5.0, 'diameter_m': 0.65, 'tank': True},
        {'length_m': 3.65, 'diameter_m': 0.178},
    ])
    assert specs[0].tank is True and specs[1].tank is False


def test_tank_drag_dims_match_fuel_volume():
    """油箱阻力外形容积≈燃油体积（长细比不变，整体缩放）。"""
    import math
    from utils.combat_radius.loadout import FUEL_DENSITY_KG_L, TANK_SHAPE_FILL, tank_drag_dims

    for mid in ('FUEL-TANK-370', 'FUEL-TANK-600', 'drop_tank_600', 'tank_1500l'):
        m = load_munitions()[mid]
        length, dia = tank_drag_dims(m)
        vol = math.pi / 4 * dia ** 2 * length * TANK_SHAPE_FILL
        assert vol == pytest.approx(m['fuel_kg'] / FUEL_DENSITY_KG_L / 1000.0, rel=0.02)
        assert length / dia == pytest.approx(m['length_m'] / m['diameter_m'], rel=1e-6)


def test_undersized_f16_tanks_are_enlarged_and_munitions_untouched():
    """F-16 库内偏小的油箱外形被放大；非油箱外挂尺寸不变。"""
    from utils.combat_radius.loadout import tank_drag_dims

    m = load_munitions()
    for mid in ('FUEL-TANK-370', 'FUEL-TANK-600', 'FUEL-TANK-300'):
        length, dia = tank_drag_dims(m[mid])
        assert length > 1.2 * m[mid]['length_m'] and dia > 1.2 * m[mid]['diameter_m']
    assert tank_drag_dims(m['pl12']) == (m['pl12']['length_m'], m['pl12']['diameter_m'])


def test_resolve_loadout_uses_corrected_tank_dims():
    """F-16 挂 600 加仑油箱：StoreSpec 用校正后的外形，阻力不再偏小。"""
    s = resolve_loadout('F-16', {'4': 'FUEL-TANK-600@1'})
    spec = s.store_specs[0]
    m = load_munitions()['FUEL-TANK-600']
    assert spec.length_m > m['length_m'] and spec.diameter_m > m['diameter_m']
    assert spec.tank is True
