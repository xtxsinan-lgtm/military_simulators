"""作战半径升阻比估算端到端测试。"""
from __future__ import annotations

import json

import pytest

from apps.combat_radius_web import run_combat_radius_json
from apps.miniprogram_api import handle_request
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.lift_drag import J20_SUPERCRUISE_MACH
from utils.paths import ROOT


def _params_from_csv() -> dict:
    presets = load_presets()
    a1 = get_preset_by_id(presets, 'F-35C')
    a2 = get_preset_by_id(presets, 'F-22')
    tgt = get_preset_by_id(presets, 'J-20')
    return {
        'anchor1': a1,
        'ld1_target': a1['ld_known'],
        'anchor2': a2,
        'ld2_target': a2['ld_known'],
        'target': tgt,
    }


@pytest.mark.e2e
def test_e2e_combat_radius_csv_anchors_predict_j20():
    """CSV 预设锚点标定后，歼-20 升阻比应落在合理巡航区间。"""
    presets = load_presets()
    a1 = get_preset_by_id(presets, 'F-35C')
    a2 = get_preset_by_id(presets, 'F-22')
    r = run_combat_radius_json({'action': 'predict_ld', 'params': _params_from_csv()})
    assert r['success'] is True
    assert r['anchors'][0]['ld'] == pytest.approx(a1['ld_known'], abs=1e-8)
    assert r['anchors'][1]['ld'] == pytest.approx(a2['ld_known'], abs=1e-8)
    assert 7.0 < r['target']['ld'] < 10.0


def _thrust_params() -> dict:
    return {
        'bpr': 0.30, 'opr': 26.0, 't4_K': 1922, 'tsl_kN': 116.0,
        'alt_m': 11000, 'mach': 1.5,
    }


@pytest.mark.e2e
def test_e2e_combat_radius_f119_military_thrust():
    """F119 在 11000 m / Ma 1.5 下可用军推应低于海平面静止值且为正。"""
    r = run_combat_radius_json({'action': 'estimate_thrust', 'params': _thrust_params()})
    assert r['success'] is True
    assert 10.0 < r['thrust_kN'] < 116.0
    assert 0.1 < r['alpha'] < 0.6
    assert r['T0'] == pytest.approx(216.65, abs=1e-6)


@pytest.mark.e2e
def test_e2e_combat_radius_thrust_http_api():
    payload = {'action': 'estimate_thrust', 'params': _thrust_params()}
    status, _, body = handle_request(
        'POST', '/api/combat_radius/simulate', json.dumps(payload).encode(),
    )
    assert status == 200
    result = json.loads(body.decode())
    assert result['success'] is True
    assert 'thrust_kN' in result
    assert result['fan_pr'] > 1.0


def _efficiency_params() -> dict:
    presets = load_presets()
    f22 = get_preset_by_id(presets, 'F-22')
    p = _params_from_csv()
    p['target'] = f22
    p.update({
        'empty_kg': f22['empty_kg'],
        'internal_fuel_kg': f22['internal_fuel_kg'],
        'n_pilots': f22['n_pilots'],
        'missile_mass_kg': f22['missile_mass_kg'],
        'n_engines': f22['n_engines'],
        'bpr': 0.30, 'opr': 26.0, 't4_K': 1922, 'tsl_kN': 116.0,
        'alt_m': f22['alt_m'], 'mach': f22['mach'],
    })
    return p


@pytest.mark.e2e
def test_e2e_combat_radius_f22_efficiency_tsfc():
    """F-22 巡航点负载应低于 1，并给出正的总效率与 TSFC。"""
    presets = load_presets()
    a2 = get_preset_by_id(presets, 'F-22')
    r = run_combat_radius_json({'action': 'estimate_efficiency', 'params': _efficiency_params()})
    assert r['success'] is True
    assert r['ld'] == pytest.approx(a2['ld_known'], abs=1e-6)
    assert 0 < r['load'] < 1
    assert r['eta_o'] > 0.05
    assert r['tsfc_mg_n_s'] > 0


@pytest.mark.e2e
def test_e2e_combat_radius_efficiency_http_api():
    status, _, body = handle_request(
        'POST', '/api/combat_radius/simulate',
        json.dumps({'action': 'estimate_efficiency', 'params': _efficiency_params()}).encode(),
    )
    assert status == 200
    result = json.loads(body.decode())
    assert result['success'] is True
    assert 'eta_o' in result
    assert 'tsfc_lb_lbf_h' in result


def _radius_params() -> dict:
    p = _efficiency_params()
    return p


@pytest.mark.e2e
def test_e2e_combat_radius_f22_breguet_radius():
    """F-22 + F119 在 Ma 0.8/1.5/1.76 应可行，最大巡航锚定超巡 Ma 1.76。"""
    r = run_combat_radius_json({
        'action': 'estimate_radius',
        'params': {**_radius_params(), 'max_tsl_kN': 156.0},
    })
    assert r['success'] is True
    assert len(r['points']) == 5
    m08 = next(p for p in r['points'] if p['id'] == 'mach_0_8')
    m15 = next(p for p in r['points'] if p['id'] == 'mach_1_5')
    m176 = next(p for p in r['points'] if p['id'] == 'mach_1_76')
    m20 = next(p for p in r['points'] if p['id'] == 'mach_2_0')
    assert m08['feasible'] is True
    assert m08['radius_km'] > 200
    assert m08['fuel_kg_per_km'] > 0
    assert m15['feasible'] is True
    assert m176['feasible'] is True
    assert m20['feasible'] is False
    assert m20['max_ld'] is not None and m20['max_ld'] > 0
    assert m20['max_ld_thrust_mode'] == 'afterburner'
    assert m15['radius_km'] < m08['radius_km']
    assert 11000.0 <= m08['alt_m'] <= 12500.0
    assert m15['alt_m'] > m08['alt_m']
    assert r['mach_cone_limit'] > 1
    assert r['max_cruise_mach'] == pytest.approx(1.76, abs=0.02)
    assert r['carrier'] is False
    mf = r['mission_fuel']
    assert mf['reserve_min'] == 30
    assert mf['climb_extra_kg'] > 0
    assert mf['descent_save_kg'] > 0
    assert r['fuel_usable_kg'] < r['fuel_kg']
    assert r['mass_initial_kg'] == pytest.approx(
        r['mass_takeoff_kg'] - mf['climb_extra_kg'],
    )
    assert r['mass_final_kg'] == pytest.approx(r['mass_dry_kg'] + mf['held_fuel_kg'])
    assert mf['held_fuel_kg'] == pytest.approx(mf['reserve_fuel_kg'] - mf['descent_save_kg'])
    assert mf['takeoff_kg_per_km'] > mf['landing_kg_per_km']
    assert '亚音速油耗' in r['note']
    from utils.combat_radius.breguet import combat_radius_m
    assert m08['radius_m'] == pytest.approx(combat_radius_m(
        m08['V0'], m08['tsfc_kg_n_s'], m08['ld'],
        r['mass_initial_kg'], r['mass_final_kg'],
    ))


@pytest.mark.e2e
def test_e2e_combat_radius_j20_supercruise_and_radius_order():
    """歼-20 最大巡航约 Ma 1.63；Ma 1.5 作战半径须小于亚音速。"""
    presets = load_presets()
    engines = load_engine_presets()
    j20 = get_preset_by_id(presets, 'J-20')
    a1 = get_preset_by_id(presets, 'F-35C')
    a2 = get_preset_by_id(presets, 'F-22')
    eng = get_preset_by_id(engines, 'ws15')
    r = run_combat_radius_json({
        'action': 'estimate_radius',
        'params': {
            'anchor1': a1, 'ld1_target': a1['ld_known'],
            'anchor2': a2, 'ld2_target': a2['ld_known'],
            'target': j20,
            'empty_kg': j20['empty_kg'],
            'internal_fuel_kg': j20['internal_fuel_kg'],
            'n_pilots': j20['n_pilots'],
            'missile_mass_kg': j20['missile_mass_kg'],
            'n_engines': j20['n_engines'],
            'bpr': eng['bpr'], 'opr': eng['opr'], 't4_K': eng['t4_K'],
            'tsl_kN': eng['tsl_kN'],
        },
    })
    assert r['success'] is True
    assert r['max_cruise_mach'] == pytest.approx(J20_SUPERCRUISE_MACH, abs=0.02)
    m08 = next(p for p in r['points'] if p['id'] == 'mach_0_8')
    m15 = next(p for p in r['points'] if p['id'] == 'mach_1_5')
    m176 = next(p for p in r['points'] if p['id'] == 'mach_1_76')
    assert m08['feasible'] is True
    assert m15['feasible'] is True
    assert m176['feasible'] is False
    assert m15['radius_km'] < m08['radius_km']


@pytest.mark.e2e
def test_e2e_combat_radius_radius_http_api():
    status, _, body = handle_request(
        'POST', '/api/combat_radius/simulate',
        json.dumps({'action': 'estimate_radius', 'params': _radius_params()}).encode(),
    )
    assert status == 200
    result = json.loads(body.decode())
    assert result['success'] is True
    assert 'points' in result
    assert result['points'][0]['id'] == 'mach_0_8'


@pytest.mark.e2e
def test_e2e_combat_radius_http_api():
    payload = {'action': 'predict_ld', 'params': _params_from_csv()}
    status, _, body = handle_request(
        'POST', '/api/combat_radius/simulate', json.dumps(payload).encode(),
    )
    assert status == 200
    result = json.loads(body.decode())
    assert result['success'] is True
    assert 'Cf0' in result


@pytest.mark.e2e
def test_e2e_combat_radius_expanded_fleet_predict_ld():
    """扩充机型（兰姆达翼、无人机、三发双座）须能完成升阻比标定。"""
    presets = load_presets()
    a1 = get_preset_by_id(presets, 'F-35C')
    a2 = get_preset_by_id(presets, 'F-22')
    for aid in ('J-50', 'J-36', '53636', '53536', 'J-15', 'F-35B'):
        tgt = get_preset_by_id(presets, aid)
        r = run_combat_radius_json({
            'action': 'predict_ld',
            'params': {
                'anchor1': a1,
                'ld1_target': a1['ld_known'],
                'anchor2': a2,
                'ld2_target': a2['ld_known'],
                'target': tgt,
            },
        })
        assert r['success'] is True, aid
        assert 6.0 < r['target']['ld'] < 12.0


@pytest.mark.e2e
def test_e2e_combat_radius_uav_and_j36_weight_fields():
    """无人机零飞行员、歼-36 三发双座须进入空战重量。"""
    presets = load_presets()
    uav = get_preset_by_id(presets, '53636')
    assert uav['n_pilots'] == 0
    assert uav['length_m'] == pytest.approx(14.6)
    uav535 = get_preset_by_id(presets, '53536')
    assert uav535['length_m'] == pytest.approx(16.7)
    j35 = get_preset_by_id(presets, 'J-35')
    j35a = get_preset_by_id(presets, 'J-35A')
    assert j35['length_m'] == pytest.approx(17.7)
    assert j35a['length_m'] == pytest.approx(17.7)
    j36 = get_preset_by_id(presets, 'J-36')
    assert j36['n_engines'] == 3
    assert j36['n_pilots'] == 2
    f22 = get_preset_by_id(presets, 'F-22')
    p = _params_from_csv()
    p['target'] = uav
    p.update({
        'empty_kg': uav['empty_kg'],
        'internal_fuel_kg': uav['internal_fuel_kg'],
        'n_pilots': 0,
        'missile_mass_kg': uav['missile_mass_kg'],
        'n_engines': 1,
        'bpr': 0.30, 'opr': 26.0, 't4_K': 1922, 'tsl_kN': 116.0,
        'alt_m': uav['alt_m'], 'mach': uav['mach'],
    })
    r = run_combat_radius_json({'action': 'estimate_efficiency', 'params': p})
    assert r['success'] is True
    assert r['mass_kg'] == pytest.approx(
        uav['empty_kg'] + 0.5 * uav['internal_fuel_kg'] + 4 * uav['missile_mass_kg']
    )
    p36 = _params_from_csv()
    p36['target'] = j36
    p36.update({
        'empty_kg': j36['empty_kg'],
        'internal_fuel_kg': j36['internal_fuel_kg'],
        'n_pilots': 2,
        'missile_mass_kg': j36['missile_mass_kg'],
        'n_engines': 3,
        'bpr': 0.30, 'opr': 26.0, 't4_K': 1922, 'tsl_kN': 116.0,
        'alt_m': j36['alt_m'], 'mach': j36['mach'],
    })
    r36 = run_combat_radius_json({'action': 'estimate_efficiency', 'params': p36})
    assert r36['success'] is True
    assert r36['n_engines'] == 3


@pytest.mark.e2e
def test_e2e_combat_radius_three_channels_exist():
    """HTML / 小程序 / iOS 三端须同时存在作战半径入口。"""
    html = ROOT / 'docs' / 'combat-radius.html'
    js = ROOT / 'docs' / 'js' / 'combat_radius.js'
    assert html.is_file()
    assert js.is_file()
    html_text = html.read_text(encoding='utf-8')
    js_text = js.read_text(encoding='utf-8')
    assert 'run_combat_radius_json' in js_text
    assert 'aircraft_dashboard' in js_text
    assert 'combat_radius.js' in html_text
    wxml = (ROOT / 'miniprogram' / 'pages' / 'combat_radius' / 'combat_radius.wxml').read_text(encoding='utf-8')
    assert '飞机作战半径估算终端' in wxml
    assert '搜索最佳升阻比和巡航高度' in wxml
    assert '混合作战半径' in wxml
    assert '最大 L/D' in wxml
    assert '锚点' not in wxml
    assert 'search_best_cruise' in js_text
    assert 'estimate_engine_cycle' in js_text
    ios = (ROOT / 'ios' / 'CarrierTakeOff' / 'CombatRadiusView.swift').read_text(encoding='utf-8')
    assert '飞机作战半径估算终端' in ios
    assert '搜索最佳升阻比和巡航高度' in ios
    assert '混合作战半径' in ios
    assert '最大 L/D' in ios
    assert '锚点' not in ios
    assert 'maxLd' in js_text
    assert 'runCombatRadius' in (ROOT / 'ios' / 'CarrierTakeOff' / 'LocalSimulatorEngine.swift').read_text(encoding='utf-8')
    assert 'engine_id' in js_text
    assert 'resolveTslKN' in js_text
    assert 'engine_id' in (ROOT / 'miniprogram' / 'pages' / 'combat_radius' / 'combat_radius.js').read_text(encoding='utf-8')
    ios_vm = (ROOT / 'ios' / 'CarrierTakeOff' / 'CombatRadiusViewModel.swift').read_text(encoding='utf-8')
    assert 'engine_id' in ios_vm
    assert 'wtCarrier' in ios_vm
    assert '舰载机' in html_text
    assert '舰载机' in wxml
    assert '舰载机' in ios
    assert 'fail_reason' in js_text


@pytest.mark.e2e
def test_e2e_combat_radius_j15_radius_uses_csv_engine():
    """合并库中的歼-15 须能带 CSV 发动机走完布雷盖作战半径。"""
    from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets

    presets = load_presets()
    engines = load_engine_presets()
    a1 = get_preset_by_id(presets, 'F-35C')
    a2 = get_preset_by_id(presets, 'F-22')
    tgt = get_preset_by_id(presets, 'J-15')
    eng = get_preset_by_id(engines, tgt['engine_id'])
    assert eng is not None
    assert tgt['carrier'] is True
    r = run_combat_radius_json({
        'action': 'estimate_radius',
        'params': {
            'anchor1': a1,
            'ld1_target': a1['ld_known'],
            'anchor2': a2,
            'ld2_target': a2['ld_known'],
            'target': tgt,
            'empty_kg': tgt['empty_kg'],
            'internal_fuel_kg': tgt['internal_fuel_kg'],
            'n_pilots': tgt['n_pilots'],
            'missile_mass_kg': tgt['missile_mass_kg'],
            'n_engines': tgt['n_engines'],
            'bpr': eng['bpr'],
            'opr': eng['opr'],
            't4_K': eng['t4_K'],
            'tsl_kN': eng['tsl_kN'],
            'alt_m': tgt['alt_m'],
            'mach': tgt['mach'],
        },
    })
    assert r['success'] is True
    m08 = next(p for p in r['points'] if p['id'] == 'mach_0_8')
    assert m08['feasible'] is True
    assert m08['radius_km'] > 200
    assert r['carrier'] is True
    assert r['mission_fuel']['reserve_min'] == 40
    assert r['fuel_usable_kg'] < r['fuel_kg']


@pytest.mark.e2e
def test_e2e_combat_radius_f22_max_speed_uses_ab_thrust():
    """F-22 + F119 加力最大速度须可走通 estimate_max_speed。"""
    presets = load_presets()
    engines = load_engine_presets()
    a1 = get_preset_by_id(presets, 'F-35C')
    a2 = get_preset_by_id(presets, 'F-22')
    tgt = get_preset_by_id(presets, 'F-22')
    eng = get_preset_by_id(engines, 'f119')
    assert eng['max_tsl_kN'] == 156.0
    r = run_combat_radius_json({
        'action': 'estimate_max_speed',
        'params': {
            'anchor1': a1,
            'ld1_target': a1['ld_known'],
            'anchor2': a2,
            'ld2_target': a2['ld_known'],
            'target': tgt,
            'empty_kg': tgt['empty_kg'],
            'internal_fuel_kg': tgt['internal_fuel_kg'],
            'n_pilots': tgt['n_pilots'],
            'missile_mass_kg': tgt['missile_mass_kg'],
            'n_engines': tgt['n_engines'],
            'bpr': eng['bpr'],
            'opr': eng['opr'],
            't4_K': eng['t4_K'],
            'max_tsl_kN': eng['max_tsl_kN'],
        },
    })
    assert r['success'] is True
    assert r['feasible'] is True
    assert r['max_speed_mach'] > 1.0
    assert r['max_speed_kmh'] > 1200
    assert r['ld'] > 0
    assert 'profile' in r


@pytest.mark.e2e
def test_e2e_combat_radius_results_cover_fleet_and_match_f22():
    """预计算快照须覆盖全部机型，且 F-22 与现场计算一致。"""
    from utils.combat_radius.combat_radius_results import (
        load_combat_radius_results,
        run_preset_dashboard,
    )

    stored = load_combat_radius_results()
    assert stored.get('version', 0) >= 1
    fleet_ids = {p['id'] for p in load_presets()}
    assert set(stored.get('aircraft', {})) == fleet_ids
    f22 = stored['aircraft']['F-22']
    assert f22['success'] is True
    live = run_preset_dashboard('F-22')
    assert live['success'] is True
    live_m08 = next(p for p in live['points'] if p['id'] == 'mach_0_8')
    stored_m08 = next(p for p in f22['points'] if p['id'] == 'mach_0_8')
    assert live_m08['radius_km'] == pytest.approx(stored_m08['radius_km'], rel=1e-4, abs=0.05)
    assert     live['max_cruise_mach'] == pytest.approx(f22['max_cruise_mach'], rel=1e-4, abs=1e-4)
    j20 = stored['aircraft']['J-20']
    assert j20['success'] is True
    assert j20['max_cruise_mach'] == pytest.approx(J20_SUPERCRUISE_MACH, abs=0.02)
    j50 = stored['aircraft']['J-50']
    assert j50['success'] is True
    assert j50['max_cruise_mach'] > f22['max_cruise_mach']
    j50_m08 = next(p for p in j50['points'] if p['id'] == 'mach_0_8')
    f22_m08 = next(p for p in f22['points'] if p['id'] == 'mach_0_8')
    assert j50_m08['alt_m'] >= f22_m08['alt_m']
    f35c = stored['aircraft']['F-35C']
    assert f35c['success'] is True
    j35 = stored['aircraft']['J-35']
    j35a = stored['aircraft']['J-35A']
    assert j35['max_cruise_mach'] == pytest.approx(1.12, abs=0.03)
    assert j35a['max_cruise_mach'] == pytest.approx(1.47, abs=0.03)


@pytest.mark.e2e
def test_e2e_combat_radius_zero_tsl_uses_engine_max():
    """前端把空军推当成 0 时，须用发动机加力估军推，不能报参数超出有效范围。"""
    from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
    from utils.combat_radius.combat_radius_results import dashboard_params_from_preset

    ac = get_preset_by_id(load_presets(), 'J-50')
    eng = get_preset_by_id(load_engine_presets(), ac['engine_id'])
    params = dashboard_params_from_preset(ac, eng)
    params['tsl_kN'] = 0
    params['max_tsl_kN'] = eng['max_tsl_kN']
    r = run_combat_radius_json({'action': 'aircraft_dashboard', 'params': params})
    assert r['success'] is True
    assert '参数超出有效范围' not in str(r.get('error', ''))
    points_ok = [p for p in (r.get('points') or []) if p.get('feasible')]
    assert points_ok


@pytest.mark.e2e
def test_e2e_combat_radius_dashboard_http_and_mixed():
    """仪表盘 HTTP 与混合作战半径（超音速点）须走通。"""
    p = _radius_params()
    p['max_tsl_kN'] = 156.0
    status, _, body = handle_request(
        'POST', '/api/combat_radius/simulate',
        json.dumps({'action': 'aircraft_dashboard', 'params': p}).encode(),
    )
    assert status == 200
    result = json.loads(body.decode())
    assert result['success'] is True
    assert 'max_speed' in result
    assert any(pt['id'] == 'mach_2_0' for pt in result['points'])
    m20 = next(pt for pt in result['points'] if pt['id'] == 'mach_2_0')
    assert m20.get('max_ld') is not None and m20['max_ld'] > 0
    m08 = next(pt for pt in result['points'] if pt['id'] == 'mach_0_8')
    assert m08.get('mixed_radius_km') in (None, 0) or m08['mixed_radius_km'] is None
    supers = [pt for pt in result['points'] if pt.get('feasible') and (pt.get('mach') or 0) > 1]
    if supers:
        assert any(pt.get('mixed_radius_km') for pt in supers)


@pytest.mark.e2e
def test_e2e_search_best_cruise_and_engine_cycle_http():
    p = _efficiency_params()
    p['mach'] = 0.8
    status, _, body = handle_request(
        'POST', '/api/combat_radius/simulate',
        json.dumps({'action': 'search_best_cruise', 'params': p}).encode(),
    )
    assert status == 200
    result = json.loads(body.decode())
    assert result['success'] is True
    assert result['feasible'] is True
    assert result['ld'] > 0
    assert result['max_ld'] is not None and result['max_ld'] >= result['ld'] - 1e-9
    p['mach'] = 2.0
    p['max_tsl_kN'] = 156.0
    status, _, body = handle_request(
        'POST', '/api/combat_radius/simulate',
        json.dumps({'action': 'search_best_cruise', 'params': p}).encode(),
    )
    assert status == 200
    high = json.loads(body.decode())
    assert high['success'] is True
    assert high['feasible'] is False
    assert high.get('max_ld') is not None and high['max_ld'] > 0
    status, _, body = handle_request(
        'POST', '/api/combat_radius/simulate',
        json.dumps({
            'action': 'estimate_engine_cycle',
            'params': {
                'bpr': 0.30, 'opr': 26.0, 't4_K': 1922,
                'mach': 0.8, 'alt_m': 12000, 'load': 0.45,
            },
        }).encode(),
    )
    assert status == 200
    cycle = json.loads(body.decode())
    assert cycle['success'] is True
    assert cycle['eta_o'] > 0
