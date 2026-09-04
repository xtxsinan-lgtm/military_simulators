"""作战半径机型预设单元测试。"""
from __future__ import annotations

import pytest

from utils.combat_radius.combat_radius_presets import (
    _preset_sort_key,
    build_combat_radius_engine_presets_payload,
    build_combat_radius_presets_payload,
    clear_injected_combat_radius_presets,
    get_preset_by_id,
    inject_combat_radius_presets,
    load_engine_presets,
    load_presets,
    preset_select_label,
    preset_to_aircraft,
    preset_to_aircraft_dict,
    sort_presets_by_nation_then_name,
)
from utils.paths import COMBAT_RADIUS_AIRCRAFT_CSV, COMBAT_RADIUS_ENGINE_CSV

# 作战半径仅含分段浸润几何机型（起飞专用的歼-15 等不入选）
EXPECTED_COMBAT_RADIUS_AIRCRAFT_IDS = [
    'F-35C', 'F-22', 'F-35A', 'J-20', 'J-10C', 'J-50', 'J-50N', 'J-36',
    'J-35', 'J-35A', '53636', '53636N', '53536',
    'F-35B',
    'NG6C', 'NG6B', 'NG6A',
]


def test_load_presets_contains_anchors_and_j20():
    presets = load_presets()
    ids = [p['id'] for p in presets]
    assert ids == EXPECTED_COMBAT_RADIUS_AIRCRAFT_IDS
    f35 = get_preset_by_id(presets, 'F-35C')
    assert f35 is not None
    assert f35['rough'] is True
    assert 'ld_known' not in f35
    assert f35['n_engines'] == 1
    assert f35['engine_id'] == 'f135'
    f35b = get_preset_by_id(presets, 'F-35B')
    assert f35b is not None
    assert f35b['engine_id'] == 'f135b'
    j20 = get_preset_by_id(presets, 'J-20')
    assert j20 is not None
    assert j20['planform'] == 'trapezoidal'
    assert j20['layout'] == 'canard'
    assert 'ld_known' not in j20
    j50 = get_preset_by_id(presets, 'J-50')
    assert j50 is not None
    assert j50['planform'] == 'lambda'
    j50n = get_preset_by_id(presets, 'J-50N')
    assert j50n is not None
    assert j50['empty_kg'] == pytest.approx(19300)
    assert j50n['empty_kg'] == pytest.approx(19900)
    assert j50['internal_fuel_kg'] == j50n['internal_fuel_kg'] == 13000
    assert j50['missile_mass_kg'] == j50n['missile_mass_kg'] == 210
    assert j50['n_pilots'] == j50n['n_pilots'] == 1
    uav = get_preset_by_id(presets, '53636')
    assert uav is not None
    assert uav['n_pilots'] == 0
    assert uav['length_m'] == pytest.approx(14.7)
    assert uav['wingspan_m'] == pytest.approx(10.2)
    assert uav['wing_area_m2'] == pytest.approx(47.8)
    assert uav['sweep_deg'] == pytest.approx(56.1)
    assert uav['empty_kg'] == pytest.approx(7700)
    assert uav['internal_fuel_kg'] == pytest.approx(4870)
    from utils.combat_radius.cruise_load import wing_loading_t_m2
    assert uav['AR'] == pytest.approx(10.2 ** 2 / 47.8, abs=0.005)
    assert uav['wing_loading'] == pytest.approx(wing_loading_t_m2(
        7700, 4870, 47.8, 0, 210,
    ), abs=1e-6)
    assert uav['fuse_width_m'] == pytest.approx(2.26)
    assert uav['fuse_height_m'] == pytest.approx(1.62)
    assert uav['engine_id'] == 'ws10c'
    ac_uav = preset_to_aircraft(uav)
    assert ac_uav.canopy is False
    assert ac_uav.mach_angle_deg == pytest.approx(23.1)
    j36 = get_preset_by_id(presets, 'J-36')
    assert j36 is not None
    assert j36['n_engines'] == 3
    assert j36['n_pilots'] == 2
    assert j36['planform'] == 'double_delta'
    assert j36['bwb'] is True
    assert j36['empty_kg'] == pytest.approx(26000)
    assert j36['internal_fuel_kg'] == pytest.approx(26800)
    uav535 = get_preset_by_id(presets, '53536')
    assert uav535 is not None
    assert uav535['planform'] == 'diamond'
    assert uav535['bwb'] is True
    assert uav535['engine_id'] == 'ws10c'
    assert uav535['length_m'] == pytest.approx(16.7)
    assert uav535['wingspan_m'] == pytest.approx(9.11)
    assert uav535['wing_area_m2'] == pytest.approx(51.56)
    assert uav535['sweep_deg'] == pytest.approx(52.3)
    assert uav535['mach_angle_deg'] == pytest.approx(21.6)
    assert uav535['empty_kg'] == pytest.approx(8400)
    assert uav535['internal_fuel_kg'] == pytest.approx(5690)
    assert uav535['AR'] == pytest.approx(9.11 ** 2 / 51.56, abs=0.005)
    assert uav535['wing_loading'] == pytest.approx(wing_loading_t_m2(
        8400, 5690, 51.56, 0, 210,
    ), abs=1e-6)
    assert j36['sweep_inner_deg'] == pytest.approx(67.8)
    assert j36['sweep_outer_deg'] == pytest.approx(55.3)
    ac36 = preset_to_aircraft(j36)
    assert ac36.sweep_inner_deg == pytest.approx(67.8)
    assert ac36.sweep_outer_deg == pytest.approx(55.3)
    assert get_preset_by_id(presets, 'J-15') is None
    f22 = get_preset_by_id(presets, 'F-22')
    assert f22['carrier'] is False
    assert f22['inlet'] == 'caret'
    assert j36['inlet'] == 'caret'
    assert uav['inlet'] == 'caret'
    uav_n = get_preset_by_id(presets, '53636N')
    assert uav_n is not None
    assert uav_n['engine_id'] == 'ws10c'
    assert uav_n['inlet'] == 'caret'
    assert uav_n['length_m'] == pytest.approx(uav['length_m'])
    assert uav_n['wingspan_m'] == pytest.approx(uav['wingspan_m'])
    assert uav_n['wing_area_m2'] == pytest.approx(uav['wing_area_m2'])
    assert uav_n['sweep_deg'] == pytest.approx(uav['sweep_deg'])
    assert uav_n['mach_angle_deg'] == pytest.approx(uav['mach_angle_deg'])
    assert uav_n['empty_kg'] == pytest.approx(8000)
    assert uav_n['internal_fuel_kg'] == pytest.approx(4870)
    assert uav_n['AR'] == pytest.approx(uav['AR'])
    assert uav_n['wing_loading'] == pytest.approx(wing_loading_t_m2(
        8000, 4870, 47.8, 0, 210,
    ), abs=1e-6)
    assert j20['inlet'] == 'dsi'
    assert f35['inlet'] == 'dsi'


def test_j10c_preset_canard_delta_ws10b():
    """歼-10C：三角翼鸭式、涡扇10B、陆基；几何来自公开资料。"""
    from utils.combat_radius.cruise_load import wing_loading_t_m2

    j10c = get_preset_by_id(load_presets(), 'J-10C')
    assert j10c is not None
    assert j10c['name'] == '歼-10C'
    assert j10c['carrier'] is False
    assert j10c['planform'] == 'delta'
    assert j10c['layout'] == 'canard'
    assert j10c['inlet'] == 'dsi'
    assert j10c['engine_id'] == 'ws10b'
    assert j10c['n_engines'] == 1
    assert j10c['wing_area_m2'] == pytest.approx(37.0)
    assert j10c['length_m'] == pytest.approx(16.9)
    assert j10c['wingspan_m'] == pytest.approx(9.8)
    assert j10c['empty_kg'] == pytest.approx(9750)
    assert j10c['internal_fuel_kg'] == pytest.approx(3860)
    assert j10c['AR'] == pytest.approx(9.8 ** 2 / 37.0, abs=0.005)
    assert j10c['wing_loading'] == pytest.approx(wing_loading_t_m2(
        9750, 3860, 37.0, 1, 210,
    ), abs=1e-6)
    assert j10c['canard_htail_area_m2'] == pytest.approx(4.9)
    ac = preset_to_aircraft(j10c)
    assert ac.mach_angle_deg == pytest.approx(16.2)


def test_ng6_medium_sixth_gen_presets():
    """中型六代机三型：兰姆达翼、中等 Pelican/中等平尾/小平尾、对应发动机。"""
    presets = load_presets()
    c = get_preset_by_id(presets, 'NG6C')
    b = get_preset_by_id(presets, 'NG6B')
    a = get_preset_by_id(presets, 'NG6A')
    assert c is not None and b is not None and a is not None
    assert c['name'] == '中型六代机弹射型'
    assert b['name'] == '中型六代机垂起型'
    assert a['name'] == '中型六代机空军型'
    assert c['planform'] == b['planform'] == a['planform'] == 'lambda'
    assert c['layout'] == 'pelican'
    assert b['layout'] == 'medium_htail'
    assert a['layout'] == 'small_htail'
    assert '5.6 m²' in c['notes'] and 'Pelican' in c['notes']
    assert '5.6 m²' in b['notes'] and '中等平尾' in b['notes']
    assert '5.6 m²' in a['notes'] and '小平尾' in a['notes']
    assert c['engine_id'] == a['engine_id'] == 'ws15i'
    assert b['engine_id'] == 'f135b'
    assert c['n_engines'] == b['n_engines'] == a['n_engines'] == 1
    assert c['carrier'] is True
    assert b['carrier'] is True
    assert a['carrier'] is False
    assert c['length_m'] == b['length_m'] == a['length_m'] == pytest.approx(17.7)
    assert c['wingspan_m'] == pytest.approx(13.3)
    assert b['wingspan_m'] == a['wingspan_m'] == pytest.approx(12.1)
    assert c['AR'] == pytest.approx(13.3 ** 2 / 66.7, abs=0.005)
    assert b['AR'] == a['AR'] == pytest.approx(12.1 ** 2 / 55.0, abs=0.005)
    assert c['fuse_width_m'] == b['fuse_width_m'] == a['fuse_width_m'] == pytest.approx(3.40)
    assert c['fuse_height_m'] == b['fuse_height_m'] == a['fuse_height_m'] == pytest.approx(1.97)
    assert c['main_wing_area_m2'] == pytest.approx(34.9)
    assert b['main_wing_area_m2'] == a['main_wing_area_m2'] == pytest.approx(27.0)
    assert c['canard_htail_area_m2'] == pytest.approx(5.6 * 2)
    assert b['canard_htail_area_m2'] == a['canard_htail_area_m2'] == pytest.approx(5.6 * 2)
    assert c['wing_area_m2'] == pytest.approx(66.7)
    assert b['wing_area_m2'] == a['wing_area_m2'] == pytest.approx(55.0)
    assert c['empty_kg'] == pytest.approx(13700)
    assert b['empty_kg'] == pytest.approx(13900)
    assert a['empty_kg'] == pytest.approx(12500)
    assert c['internal_fuel_kg'] == pytest.approx(8400)
    assert b['internal_fuel_kg'] == pytest.approx(6530)
    assert a['internal_fuel_kg'] == pytest.approx(8260)
    assert c['sweep_deg'] == b['sweep_deg'] == a['sweep_deg'] == pytest.approx(49.0)
    assert c['mach_angle_deg'] == pytest.approx(28.6)
    assert c['type_label'] == 'conventional'
    assert b['type_label'] == 'v/stol'
    assert c['tc'] == pytest.approx(0.043)
    assert b['tc'] == a['tc'] == pytest.approx(0.047)
    from utils.combat_radius.cruise_load import wing_loading_t_m2
    assert c['wing_loading'] == pytest.approx(wing_loading_t_m2(
        13700, 8400, 66.7, 1, 210,
    ), abs=1e-6)
    assert b['wing_loading'] == pytest.approx(wing_loading_t_m2(
        13900, 6530, 55.0, 1, 210,
    ), abs=1e-6)
    assert a['wing_loading'] == pytest.approx(wing_loading_t_m2(
        12500, 8260, 55.0, 1, 210,
    ), abs=1e-6)


def test_vtail_area_single_side_times_two():
    """垂尾按单侧单面×2 入库（歼-35A 为两侧合计 12 m²），与平尾/腹鳍同一约定。"""
    presets = load_presets()
    expected = {
        'F-35A': 4.23 * 2, 'F-35B': 4.23 * 2, 'F-35C': 5.18 * 2,
        'F-22': 9.94 * 2, 'J-35A': 12.0, 'J-35': 6.62 * 2, 'J-20': 9.07 * 2,
    }
    for aid, area in expected.items():
        row = get_preset_by_id(presets, aid)
        assert row is not None, aid
        assert row['vtail_area_m2'] == pytest.approx(area), aid
    tailless = get_preset_by_id(presets, 'J-50')
    assert tailless.get('vtail_area_m2') in (None, 0)


def test_j35a_mass_and_planform_geometry():
    """歼-35A：空重 13.1 t、内油 7.6 t；平尾与垂尾均为两侧合计 12 m²。"""
    from utils.combat_radius.cruise_load import wing_loading_t_m2

    j35a = get_preset_by_id(load_presets(), 'J-35A')
    assert j35a['empty_kg'] == pytest.approx(13100)
    assert j35a['internal_fuel_kg'] == pytest.approx(7600)
    assert j35a['main_wing_area_m2'] == pytest.approx(26.7)
    assert j35a['canard_htail_area_m2'] == pytest.approx(12.0)
    assert j35a['vtail_area_m2'] == pytest.approx(12.0)
    assert j35a['wing_area_m2'] == pytest.approx(49.2)
    assert j35a['sweep_deg'] == pytest.approx(40.5)
    assert j35a['mach_angle_deg'] == pytest.approx(27.2)
    assert j35a['wingspan_m'] == pytest.approx(12.1)
    assert j35a['AR'] == pytest.approx(12.1 ** 2 / 49.2, abs=0.005)
    assert j35a['wing_loading'] == pytest.approx(wing_loading_t_m2(
        13100, 7600, 49.2, 1, 210,
    ), abs=1e-6)


def test_get_preset_by_id_missing_returns_none():
    assert get_preset_by_id(load_presets(), 'NO-SUCH') is None


def test_preset_to_aircraft_and_dict():
    p = get_preset_by_id(load_presets(), 'F-22')
    ac = preset_to_aircraft(p)
    d = preset_to_aircraft_dict(p)
    assert ac.name == 'F-22 Raptor'
    assert d['AR'] == 2.37
    assert 'id' not in d
    assert 'ld_known' not in d
    assert p['mach_angle_deg'] == pytest.approx(28.5)
    assert ac.mach_angle_deg == pytest.approx(28.5)
    assert ac.fuse_width_m == pytest.approx(4.0)
    assert ac.fuse_height_m == pytest.approx(1.8)
    assert ac.canard_htail_area_m2 == pytest.approx(15.2)
    assert ac.vtail_area_m2 == pytest.approx(9.94 * 2)
    assert ac.main_wing_area_m2 == pytest.approx(41.4)
    assert p['empty_kg'] == 19800
    assert p['bvr_missile'] == 'AIM-120D'


def test_build_combat_radius_presets_payload():
    payload = build_combat_radius_presets_payload()
    assert payload == sort_presets_by_nation_then_name(load_presets())
    assert COMBAT_RADIUS_AIRCRAFT_CSV.is_file()


def test_preset_sort_key():
    """排序键为（国别, 名称, id）且大小写不敏感。"""
    assert _preset_sort_key({'nation': '美国', 'name': 'F-22', 'id': 'F-22'}) == (
        '美国', 'f-22', 'f-22',
    )
    assert _preset_sort_key({'nation': ' 中国 ', 'name': '歼-20', 'id': 'J-20'})[0] == '中国'
    assert _preset_sort_key({}) == ('', '', '')


def test_sort_presets_by_nation_then_name():
    """先按国别（中 < 美），同国别再按名称字母序；不修改入参。"""
    raw = [
        {'id': 'F-35C', 'name': 'F-35C Lightning II', 'nation': '美国'},
        {'id': 'J-20', 'name': '歼-20', 'nation': '中国'},
        {'id': 'F-22', 'name': 'F-22 Raptor', 'nation': '美国'},
        {'id': '53536', 'name': '53536无人战机', 'nation': '中国'},
    ]
    snapshot = [dict(item) for item in raw]
    ids = [p['id'] for p in sort_presets_by_nation_then_name(raw)]
    assert ids == ['53536', 'J-20', 'F-22', 'F-35C']
    assert raw == snapshot


def test_preset_select_label():
    """有国别时显示「国别 · 名称」，缺国别则仅名称。"""
    assert preset_select_label({'name': '歼-20', 'nation': '中国'}) == '中国 · 歼-20'
    assert preset_select_label({'name': 'F-22', 'nation': '  '}) == 'F-22'
    assert preset_select_label({'name': '自定义'}) == '自定义'


def test_load_presets_missing_file_returns_empty(tmp_path):
    missing = tmp_path / 'no.csv'
    assert load_presets(missing) == []


def test_load_engine_presets_contains_f119_and_optional_tsl():
    engines = load_engine_presets()
    ids = [p['id'] for p in engines]
    assert 'f119' in ids
    assert 'ws15' in ids
    f119 = get_preset_by_id(engines, 'f119')
    assert f119 is not None
    assert f119['bpr'] == 0.30
    assert f119['tsl_kN'] == 116.0
    ws15 = get_preset_by_id(engines, 'ws15')
    assert ws15 is not None
    assert ws15['tsl_kN'] == 105.0
    assert ws15['max_tsl_kN'] == 156.0
    ws19 = get_preset_by_id(engines, 'ws19')
    assert ws19 is not None
    assert ws19['tsl_kN'] == pytest.approx(70.0)
    assert ws19['max_tsl_kN'] == pytest.approx(110.0)
    ws15i = get_preset_by_id(engines, 'ws15i')
    assert ws15i is not None
    assert ws15i['tsl_kN'] == pytest.approx(13.5 * 9.80665, abs=0.05)
    expected = {
        'ws15': (0.25, 25.5, 1841.0),
        'ws15i': (0.25, 29.0, 1975.0),
        'ws19': (0.50, 35.0, 1850.0),
        'ws10c': (0.60, 30.0, 1800.0),
        'ws10b': (0.60, 30.0, 1800.0),
        'ws21': (0.68, 26.0, 1650.0),
        'f119': (0.30, 26.0, 1922.0),
        'f135': (0.57, 28.0, 2260.0),
        'f135b': (0.57, 28.0, 2260.0),
        'ws10h': (0.60, 30.0, 1800.0),
        'f414': (0.40, 30.0, 1850.0),
        'f404': (0.34, 26.0, 1700.0),
        'f110': (0.76, 30.7, 1700.0),
        'rd33mk': (0.49, 21.0, 1680.0),
        'm88': (0.30, 24.5, 1850.0),
        'f402': (1.20, 16.0, 1400.0),
        'j52': (0.00, 14.6, 1400.0),
        'tf41': (0.77, 20.0, 1450.0),
        'tf34': (6.20, 21.0, 1500.0),
        'j57': (0.00, 12.5, 1400.0),
        'j79': (0.00, 13.5, 1450.0),
        'f100': (0.36, 25.0, 1700.0),
        'f110ge129': (0.76, 30.7, 1700.0),
        'ej200': (0.40, 26.0, 1800.0),
        'rm12': (0.34, 26.0, 1700.0),
        'f125': (0.49, 19.0, 1450.0),
        'rd93': (0.49, 21.0, 1680.0),
        'f404in20': (0.34, 26.0, 1700.0),
    }
    for eid, (bpr, opr, t4) in expected.items():
        row = get_preset_by_id(engines, eid)
        assert row is not None
        assert row['bpr'] == pytest.approx(bpr)
        assert row['opr'] == pytest.approx(opr)
        assert row['t4_K'] == pytest.approx(t4)
    f135 = get_preset_by_id(engines, 'f135')
    assert f135 is not None
    assert f135['name'] == 'F135-PW-100'
    assert f135['tsl_kN'] == pytest.approx(125.0)
    assert f135['max_tsl_kN'] == pytest.approx(191.0)
    assert f135['tsfc_install_mult'] == pytest.approx(1.22)
    f135b = get_preset_by_id(engines, 'f135b')
    assert f135b is not None
    assert f135b['name'] == 'F135-PW-600'
    assert f135b['bpr'] == pytest.approx(f135['bpr'])
    assert f135b['opr'] == pytest.approx(f135['opr'])
    assert f135b['t4_K'] == pytest.approx(f135['t4_K'])
    assert f135b['tsfc_install_mult'] == pytest.approx(1.22)
    assert f135b['tsl_kN'] == pytest.approx(120.0)
    assert f135b['max_tsl_kN'] == pytest.approx(182.0)


def test_build_combat_radius_engine_presets_payload():
    payload = build_combat_radius_engine_presets_payload()
    assert payload[0]['id'] == 'ws15'
    assert COMBAT_RADIUS_ENGINE_CSV.is_file()
    assert COMBAT_RADIUS_ENGINE_CSV.name == 'aircraft_engine_database.csv'


def test_load_engine_presets_missing_file_returns_empty(tmp_path):
    missing = tmp_path / 'no_eng.csv'
    assert load_engine_presets(missing) == []


def test_inject_combat_radius_presets_overrides_csv():
    inject_combat_radius_presets(
        aircraft=[{'id': 'X', 'name': '注入机'}],
        engines=[{'id': 'e', 'name': '注入发'}],
    )
    try:
        assert load_presets()[0]['id'] == 'X'
        assert load_engine_presets()[0]['id'] == 'e'
    finally:
        clear_injected_combat_radius_presets()
    assert get_preset_by_id(load_presets(), 'F-22') is not None
