"""作战半径预计算快照单元测试。"""
from __future__ import annotations

import json

import pytest

from utils.combat_radius.combat_radius_results import (
    RESULTS_VERSION,
    build_combat_radius_results_catalog_payload,
    build_combat_radius_results_payload,
    dashboard_params_from_preset,
    combat_weapon_load,
    load_combat_radius_results,
    run_preset_dashboard,
    sanitize_cruise_point,
    sanitize_dashboard,
    sanitize_max_speed,
    write_combat_radius_results,
    _round,
)
from simulators.combat_radius.combat_radius import cruise_machs_differ
from utils.combat_radius.lift_drag import J20_SUPERCRUISE_MACH
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.paths import COMBAT_RADIUS_RESULTS_JSON


def test_round_none_and_digits():
    assert _round(None, 2) is None
    assert _round(1.23456, 2) == 1.23


def test_dashboard_params_from_preset_f22():
    ac = get_preset_by_id(load_presets(), 'F-22')
    eng = get_preset_by_id(load_engine_presets(), 'f119')
    p = dashboard_params_from_preset(ac, eng)
    assert 'anchor1' not in p
    assert p['tsl_kN'] == 116.0
    assert p['n_engines'] == 2
    assert p['carrier'] is False
    assert p['target']['inlet'] == 'caret'


def test_combat_weapon_load_bomber_is_payload_once():
    """轰炸机载弹按最大载弹量一件，不乘 4 枚中距弹。"""
    kg, n = combat_weapon_load({
        'aircraft_role': 'bomber', 'max_payload_kg': 17600, 'missile_mass_kg': 200,
    })
    assert kg == pytest.approx(17600)
    assert n == pytest.approx(1)
    kg_f, n_f = combat_weapon_load({'missile_mass_kg': 161})
    assert kg_f == pytest.approx(161)
    assert n_f == pytest.approx(4)


def test_xgb_dashboard_uses_j36_thickness_and_sweep_mach_angles():
    """西工大三态厚弦比同歼-36；前掠/中间/后掠马赫角为 39.7°/30.2°/21.1°。"""
    expected_phi = {'XGB-1': 39.7, 'XGB-2': 30.2, 'XGB-3': 21.1}
    j36 = get_preset_by_id(load_presets(), 'J-36')
    for aid, phi in expected_phi.items():
        ac = get_preset_by_id(load_presets(), aid)
        assert ac['tc'] == pytest.approx(j36['tc'])
        assert ac['tc'] == pytest.approx(0.043)
        assert ac['mach_angle_deg'] == pytest.approx(phi)
    ac = get_preset_by_id(load_presets(), 'XGB-1')
    eng = get_preset_by_id(load_engine_presets(), ac['engine_id'])
    assert eng['bpr'] == pytest.approx(0.475)
    assert eng['tsl_kN'] == pytest.approx(175)
    assert eng['max_tsl_kN'] == pytest.approx(265)
    p = dashboard_params_from_preset(ac, eng)
    assert p['missile_mass_kg'] == pytest.approx(17600)
    assert p['n_missiles'] == pytest.approx(1)
    assert p['target']['n_stores'] == 0
    dash = run_preset_dashboard('XGB-1')
    assert dash['success'] is True
    mil = next(item for item in dash['points'] if item['id'] == 'mach_0_8')
    assert mil['feasible'] is True
    assert mil['radius_km'] > 0
    ab = next(item for item in dash['afterburner_best_altitude'] if item['mach'] == pytest.approx(0.8))
    assert ab['feasible'] is True
    assert ab['reheat'] is False
    assert ab['radius_km'] == pytest.approx(mil['radius_km'], rel=0.02)
    assert p['tsfc_install_mult'] == pytest.approx(1.0)


def test_dashboard_params_from_preset_f35c_install():
    """F-35C 仪表盘须带上 F135 循环外 TSFC 乘数（低压轴榨功，非安装惩罚）。"""
    ac = get_preset_by_id(load_presets(), 'F-35C')
    eng = get_preset_by_id(load_engine_presets(), 'f135')
    p = dashboard_params_from_preset(ac, eng)
    assert p['tsfc_install_mult'] == pytest.approx(1.22)
    assert p['type_label'] == 'conventional'


def test_dashboard_params_from_preset_airframe_tsfc_mult():
    """机体侧 airframe_tsfc_mult 与发动机乘数相乘；未填的机型不受影响。"""
    ac = get_preset_by_id(load_presets(), 'F-16')
    eng = get_preset_by_id(load_engine_presets(), 'f110ge129')
    p = dashboard_params_from_preset(ac, eng)
    assert ac['airframe_tsfc_mult'] > 1.0
    assert p['tsfc_install_mult'] == pytest.approx(
        float(eng.get('tsfc_install_mult', 1.0)) * ac['airframe_tsfc_mult']
    )
    kaan = get_preset_by_id(load_presets(), 'KAAN')
    assert 'airframe_tsfc_mult' not in kaan
    assert dashboard_params_from_preset(kaan, eng)['tsfc_install_mult'] == pytest.approx(1.0)


@pytest.mark.parametrize('aircraft_id, ref_km', [
    ('F-16', 817), ('Mirage-2000', 758), ('FA-50', 584), ('Rafale', 987), ('F-15E', 885),
    ('F-2', 812), ('J-10C', 932), ('J-15', 1270), ('FA-18C', 985), ('Gripen-CD', 812),
])
def test_calibrated_hihihi_internal_fuel_radius(aircraft_id, ref_km):
    """按 4 中距弹、内油、hi-hi-hi、不计空战消耗的参考半径标定，Ma 0.8 半径落在 ±2% 内。"""
    from simulators.combat_radius.combat_radius import run_aircraft_dashboard_from_params

    ac = get_preset_by_id(load_presets(), aircraft_id)
    eng = get_preset_by_id(load_engine_presets(), ac['engine_id'])
    params = dashboard_params_from_preset(ac, eng)
    params['combat_allowance_min'] = 0
    point = run_aircraft_dashboard_from_params(params)['points'][0]
    assert point['id'] == 'mach_0_8'
    assert point['radius_km'] == pytest.approx(ref_km, rel=0.02)


def test_sanitize_helpers_round_and_drop_blackbox():
    point = sanitize_cruise_point({
        'id': 'mach_1_5', 'label': 'Ma 1.5', 'mach': 1.50001, 'feasible': True,
        'alt_m': 12000.44, 'ld': 7.12345, 'thrust_avail_kN': 40.1234,
        'load': 0.45678, 'eta_th': 0.1111111, 'eta_p': 0.2222222,
        'eta_o': 0.3333333, 'score': 2.1, 'radius_km': 800.129,
        'fuel_kg_per_km': 4.5555, 'mixed_radius_km': 900.129,
        'mixed_fuel_kg_per_km': 3.3333, 'tsfc_mg_n_s': 30.1234,
        'Cf0': 0.9, 'max_ld': 8.98765, 'max_ld_alt_m': 15000.4,
        'max_ld_thrust_mode': 'afterburner',
    })
    assert 'Cf0' not in point
    assert point['radius_km'] == 800.13
    assert point['max_ld'] == 8.9877
    assert point['max_ld_thrust_mode'] == 'afterburner'
    ms = sanitize_max_speed({
        'success': True, 'feasible': True, 'max_speed_mach': 2.12345,
        'max_speed_kmh': 2200.19, 'profile': [1],
    })
    assert 'profile' not in ms
    assert ms['max_speed_mach'] == 2.1235
    failed = sanitize_dashboard({'success': False, 'error': 'x'})
    assert failed['success'] is False
    ok = sanitize_dashboard({
        'success': True, 'name': 'F-22', 'carrier': False,
        'max_cruise_mach': 1.23456, 'max_possible_cruise_mach': 1.89,
        'max_radius_mach': 1.5, 'max_radius_km': 800.12,
        'fuel_kg': 8200, 'fuel_usable_kg': 5000.12,
        'n_engines': 2, 'points': [{'id': 'mach_0_8', 'feasible': True, 'mach': 0.8}],
        'max_speed': {'feasible': True, 'max_speed_mach': 2.0},
        'mission_fuel': {'reserve_min': 30},
    })
    assert ok['mission_fuel']['reserve_min'] == 30
    assert ok['success'] is True
    assert 'Cf0' not in ok
    assert ok['max_possible_cruise_mach'] == 1.89
    assert 'max_cruise_floor_mach' not in ok
    assert ok['max_radius_mach'] == 1.5
    assert ok['max_radius_km'] == 800.12
    assert 'split_cruise_note' not in ok


def test_run_preset_dashboard_missing_engine():
    r = run_preset_dashboard('NOPE')
    assert r['success'] is False
    mv = run_preset_dashboard('MV-22')
    assert mv['success'] is False
    assert '找不到机型' in mv['error']


def test_run_preset_dashboard_j50_uses_engine_thrust():
    """歼-50 绑定涡扇15改进，须用发动机表推力算出仪表盘，不能报缺军推。"""
    r = run_preset_dashboard('J-50')
    assert r['success'] is True
    assert r.get('points')


def test_run_preset_dashboard_f22_compact():
    r = run_preset_dashboard('F-22')
    assert r['success'] is True
    assert 'Cf0' not in r
    ids = [p['id'] for p in r['points']]
    assert ids[0] == 'mach_0_8'
    assert 'mach_1_0' in ids
    assert 'mach_1_2' in ids
    assert 'mach_1_35' in ids
    assert 'mach_1_75' in ids
    assert 'mach_2_0' in ids
    assert 'max_cruise' in ids
    assert 'max_radius_cruise' in ids
    assert 'max_possible_cruise' in ids
    assert 'floor_max_cruise' not in ids
    assert 'max_cruise_floor_mach' not in r
    assert next(p for p in r['points'] if p['id'] == 'max_cruise')['label'] == '实用最大巡航速度'
    radius_row = next(p for p in r['points'] if p['id'] == 'max_radius_cruise')
    assert radius_row['label'] == '最大半径超音速巡航速度'
    assert radius_row['mach'] == pytest.approx(1.56, abs=0.03)
    assert next(p for p in r['points'] if p['id'] == 'max_possible_cruise')['label'] == '最大巡航速度'
    assert 'max_speed' in r
    assert r['max_cruise_mach'] == pytest.approx(1.76, abs=0.005)
    assert r['max_possible_cruise_mach'] > r['max_cruise_mach']
    assert r['max_radius_mach'] is not None
    assert r['max_radius_mach'] == pytest.approx(1.56, abs=0.03)
    assert cruise_machs_differ(r['max_cruise_mach'], r['max_radius_mach'])
    assert 'split_cruise_note' not in r
    ms = r['max_speed']
    assert ms['feasible'] is True
    assert ms['load'] == pytest.approx(1.0, abs=0.08)
    m15 = next(p for p in r['points'] if p['id'] == 'mach_1_5')
    m175 = next(p for p in r['points'] if p['id'] == 'mach_1_75')
    m20 = next(p for p in r['points'] if p['id'] == 'mach_2_0')
    assert m175['alt_m'] >= m15['alt_m'] - 200.0
    assert m175['fuel_kg_per_km'] / m15['fuel_kg_per_km'] < 1.12
    assert m175['radius_km'] > 0.6 * m15['radius_km']
    assert m15['feasible'] is True
    assert m175['feasible'] is True
    assert m20['feasible'] is False
    assert m20['max_ld'] is not None and m20['max_ld'] > 0
    assert m15['radius_km'] < next(p for p in r['points'] if p['id'] == 'mach_0_8')['radius_km']
    m08 = next(p for p in r['points'] if p['id'] == 'mach_0_8')
    assert 11000.0 <= m08['alt_m'] <= 13000.0
    m10 = next(p for p in r['points'] if p['id'] == 'mach_1_0')
    m12 = next(p for p in r['points'] if p['id'] == 'mach_1_2')
    m135 = next(p for p in r['points'] if p['id'] == 'mach_1_35')
    assert m10['feasible'] is True and m12['feasible'] is True and m135['feasible'] is True
    assert m10['radius_km'] < m08['radius_km']
    assert m12['radius_km'] < m08['radius_km']
    assert m12['radius_km'] < m135['radius_km']


def test_run_preset_dashboard_j50_supercruise_above_f22():
    """无尾兰姆达翼体积波阻更低，歼-50 掉高度后上限应高于 F-22。"""
    f22 = run_preset_dashboard('F-22')
    j50 = run_preset_dashboard('J-50')
    assert f22['success'] is True and j50['success'] is True
    assert j50['max_possible_cruise_mach'] > f22['max_possible_cruise_mach']
    m08 = next(p for p in j50['points'] if p['id'] == 'mach_0_8')
    m15 = next(p for p in j50['points'] if p['id'] == 'mach_1_5')
    f22_m08 = next(p for p in f22['points'] if p['id'] == 'mach_0_8')
    assert m08['alt_m'] >= f22_m08['alt_m']
    assert m15['alt_m'] > m08['alt_m']


def test_run_preset_dashboard_j20_supercruise_below_f22():
    """歼-20 实用最大巡航与 F-22 同落在超巡带上沿附近；Ma 0.8 半径约 1360 km（快照默认不计空战消耗）。"""
    r = run_preset_dashboard('J-20')
    assert r['success'] is True
    assert r['max_cruise_mach'] == pytest.approx(J20_SUPERCRUISE_MACH, abs=0.02)
    m08 = next(p for p in r['points'] if p['id'] == 'mach_0_8')
    m15 = next(p for p in r['points'] if p['id'] == 'mach_1_5')
    m175 = next(p for p in r['points'] if p['id'] == 'mach_1_75')
    m20 = next(p for p in r['points'] if p['id'] == 'mach_2_0')
    assert m08['feasible'] is True
    assert m15['feasible'] is True
    assert m175['feasible'] is True
    assert m20['feasible'] is False
    assert m08['radius_km'] == pytest.approx(1360, abs=50)
    m10 = next(p for p in r['points'] if p['id'] == 'mach_1_0')
    assert m10['feasible'] is True
    assert m10['radius_km'] < m08['radius_km']
    assert m15['radius_km'] < m08['radius_km']


def test_run_preset_dashboard_j35_and_j35a_max_cruise():
    """歼-35 军推穿不过跨声速空洞；歼-35A 涡扇19 军推 70 kN 后可超巡。"""
    j35 = run_preset_dashboard('J-35')
    j35a = run_preset_dashboard('J-35A')
    assert j35['success'] is True and j35a['success'] is True
    m12 = next(p for p in j35['points'] if p['id'] == 'mach_1_2')
    assert m12['feasible'] is False
    assert j35['max_cruise_mach'] is None
    assert j35a['max_cruise_mach'] == pytest.approx(1.47, abs=0.02)
    m12a = next(p for p in j35a['points'] if p['id'] == 'mach_1_2')
    assert m12a['feasible'] is False


def test_run_preset_dashboard_j35_floor_above_practical_when_no_supercruise():
    """歼-35 穿不过跨声速空洞：无实用超巡，最大可能巡航停在空洞前。"""
    r = run_preset_dashboard('J-35')
    assert r['success'] is True
    assert r['max_cruise_mach'] is None
    assert r['max_possible_cruise_mach'] == pytest.approx(1.00, abs=0.03)


def test_run_preset_dashboard_ws10c_uav_slim_fuse_supercruise():
    """细机身无人机均可越过跨声速鼓包后超巡。"""
    slim = run_preset_dashboard('53636')
    assert slim['success'] is True
    assert slim['max_cruise_mach'] == pytest.approx(1.56, abs=0.02)
    m12 = next(p for p in slim['points'] if p['id'] == 'mach_1_2')
    assert m12['feasible'] is True
    for aid in ('53536', '53636N'):
        r = run_preset_dashboard(aid)
        assert r['success'] is True, aid
        assert r['max_cruise_mach'] is not None, aid
        assert r['max_cruise_mach'] >= 1.2, aid


def test_run_preset_dashboard_ab_flyable_machs_have_max_ld():
    """有极速的机型：不超过极速的固定马赫须有最大升阻比。"""
    for aid in ('F-35C', '53636N', 'J-35'):
        r = run_preset_dashboard(aid)
        assert r['success'] is True, aid
        vmax = (r.get('max_speed') or {}).get('max_speed_mach')
        assert vmax is not None and vmax > 0, aid
        for p in r['points']:
            mach = p.get('mach')
            if mach is None or float(mach) > float(vmax) + 1e-9:
                continue
            assert p.get('max_ld') is not None and p['max_ld'] > 0, (aid, p['id'], mach, vmax)


def test_run_preset_dashboard_harrier_has_no_afterburner_max_speed():
    """鹞式已退出作战半径机型列表。"""
    r = run_preset_dashboard('AV-8B')
    assert r['success'] is False
    assert '找不到机型' in r['error']


def test_load_combat_radius_results_missing_file(tmp_path):
    empty = load_combat_radius_results(tmp_path / 'no.json')
    assert empty['aircraft'] == {}


def test_write_and_build_payload_use_stub(tmp_path, monkeypatch):
    """write / build_payload 不在单元测试里跑全机队，用桩覆盖组装逻辑。"""
    monkeypatch.setattr(
        'utils.combat_radius.combat_radius_results.run_preset_dashboard',
        lambda aid: {'success': True, 'id': aid},
    )
    payload = build_combat_radius_results_payload()
    assert payload['version'] == RESULTS_VERSION
    assert payload['aircraft']['F-22']['id'] == 'F-22'
    out = tmp_path / 'cr.json'
    write_combat_radius_results(out)
    saved = json.loads(out.read_text(encoding='utf-8'))
    assert saved['aircraft']['J-20']['id'] == 'J-20'


def test_catalog_payload_reads_file_or_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(
        'utils.combat_radius.combat_radius_results.COMBAT_RADIUS_RESULTS_JSON',
        tmp_path / 'missing.json',
    )
    assert build_combat_radius_results_catalog_payload()['aircraft'] == {}


def test_committed_results_path_constant():
    assert COMBAT_RADIUS_RESULTS_JSON.name == 'combat_radius_results.json'
