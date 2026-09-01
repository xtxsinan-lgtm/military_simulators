"""作战半径升阻比估算端到端测试。"""
from __future__ import annotations

import json

import pytest

from apps.combat_radius_web import run_combat_radius_json
from apps.miniprogram_api import handle_request
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.lift_drag import (
    F22_MAX_SPEED_MACH,
    F35_MAX_SPEED_MACH,
    J20_SUPERCRUISE_MACH,
    J35A_SUPERCRUISE_MACH,
)
from utils.paths import ROOT


def _params_from_csv() -> dict:
    presets = load_presets()
    tgt = get_preset_by_id(presets, 'J-20')
    return {'target': tgt}


@pytest.mark.e2e
def test_e2e_combat_radius_csv_anchors_predict_j20():
    """统一模型下歼-20 升阻比应落在合理巡航区间。"""
    r = run_combat_radius_json({'action': 'predict_ld', 'params': _params_from_csv()})
    assert r['success'] is True
    assert r['anchors'] == []
    assert 8.0 < r['target']['ld'] < 12.0


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
    r = run_combat_radius_json({'action': 'estimate_efficiency', 'params': _efficiency_params()})
    assert r['success'] is True
    assert 9.0 < r['ld'] < 12.0
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
    """F-22 + F119 在固定评估马赫应可行，实用最大巡航锚定超巡。"""
    r = run_combat_radius_json({
        'action': 'estimate_radius',
        'params': {**_radius_params(), 'max_tsl_kN': 156.0},
    })
    assert r['success'] is True
    assert len(r['points']) == 10
    labels = {p['id']: p['label'] for p in r['points']}
    assert labels['max_cruise'] == '实用最大巡航速度'
    assert labels['max_radius_cruise'] == '最大半径超音速巡航速度'
    assert labels['max_possible_cruise'] == '最大巡航速度'
    m08 = next(p for p in r['points'] if p['id'] == 'mach_0_8')
    m10 = next(p for p in r['points'] if p['id'] == 'mach_1_0')
    m12 = next(p for p in r['points'] if p['id'] == 'mach_1_2')
    m135 = next(p for p in r['points'] if p['id'] == 'mach_1_35')
    m15 = next(p for p in r['points'] if p['id'] == 'mach_1_5')
    m175 = next(p for p in r['points'] if p['id'] == 'mach_1_75')
    m20 = next(p for p in r['points'] if p['id'] == 'mach_2_0')
    assert m08['feasible'] is True
    assert m08['radius_km'] > 200
    assert m08['fuel_kg_per_km'] > 0
    assert m10['feasible'] is True
    assert m12['feasible'] is True
    assert m135['feasible'] is True
    assert m10['radius_km'] < m08['radius_km']
    assert m12['radius_km'] < m08['radius_km']
    assert m12['radius_km'] < m135['radius_km']
    assert m15['feasible'] is True
    assert m175['feasible'] is True
    assert m20['feasible'] is True
    assert m20['max_ld'] is not None and m20['max_ld'] > 0
    assert m20['radius_km'] < m175['radius_km']
    prac = next(p for p in r['points'] if p['id'] == 'max_cruise')
    radius_row = next(p for p in r['points'] if p['id'] == 'max_radius_cruise')
    floor = next(p for p in r['points'] if p['id'] == 'max_possible_cruise')
    for extra in (prac, radius_row, floor):
        assert extra['feasible'] is True
        assert extra['alt_m'] is not None
        assert extra['ld'] is not None
        assert extra['radius_km'] is not None
        assert extra['fuel_kg_per_km'] is not None
    assert m15['radius_km'] < m08['radius_km']
    assert 11000.0 <= m08['alt_m'] <= 12500.0
    assert m15['alt_m'] > m08['alt_m']
    assert r['mach_cone_limit'] > 1
    assert r['max_cruise_mach'] == pytest.approx(1.77, abs=0.005)
    assert r['max_possible_cruise_mach'] > r['max_cruise_mach']
    assert r['max_radius_mach'] is not None
    assert r['max_radius_mach'] == pytest.approx(1.58, abs=0.03)
    assert 'split_cruise_note' not in r
    assert prac['alt_m'] >= m15['alt_m'] - 400.0
    assert m175['alt_m'] >= m15['alt_m'] - 200.0
    assert m175['fuel_kg_per_km'] / m15['fuel_kg_per_km'] < 1.12
    from utils.combat_radius.cruise_search import PEAK_ALT_DROP_M, search_best_altitude
    from tests.cruise_search_test import _csv_ctx
    a176 = search_best_altitude(_csv_ctx('F-22'), 1.76)
    a180 = search_best_altitude(_csv_ctx('F-22'), 1.80)
    assert a176 is not None and a180 is not None
    assert a180.alt_m < a176.alt_m - PEAK_ALT_DROP_M + 1e-6
    assert m175['radius_km'] > 0.6 * m15['radius_km']
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
    """歼-20 实用最大巡航低于 F-22；Ma 0.8 半径约 1350 km，且大于 Ma 1.0 / 1.5。"""
    presets = load_presets()
    engines = load_engine_presets()
    j20 = get_preset_by_id(presets, 'J-20')
    eng = get_preset_by_id(engines, 'ws15')
    r = run_combat_radius_json({
        'action': 'estimate_radius',
        'params': {
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
    m175 = next(p for p in r['points'] if p['id'] == 'mach_1_75')
    m20 = next(p for p in r['points'] if p['id'] == 'mach_2_0')
    assert m08['feasible'] is True
    assert m15['feasible'] is True
    assert m175['feasible'] is True
    assert m20['feasible'] is False
    assert m08['radius_km'] == pytest.approx(1350, abs=50)
    m10 = next(p for p in r['points'] if p['id'] == 'mach_1_0')
    assert m10['feasible'] is True
    assert m10['radius_km'] < m08['radius_km']
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
    """扩充机型（兰姆达翼、无人机、三发双座）须能完成统一模型升阻比估计。"""
    presets = load_presets()
    for aid in ('J-50', 'J-36', '53636', '53536', 'J-15', 'F-35B', 'NG6C', 'NG6B', 'NG6A'):
        tgt = get_preset_by_id(presets, aid)
        r = run_combat_radius_json({
            'action': 'predict_ld',
            'params': {'target': tgt},
        })
        assert r['success'] is True, aid
        assert 6.0 < r['target']['ld'] < 12.0


@pytest.mark.e2e
def test_e2e_combat_radius_inlet_changes_ld():
    """F-22/歼-36/53636 为加莱特；同一几何换成 DSI 后亚音速 L/D 升高、超音速体积波阻升高。"""
    presets = load_presets()
    for aid in ('F-22', 'J-36', '53636', '53636N'):
        tgt = get_preset_by_id(presets, aid)
        assert tgt['inlet'] == 'caret', aid
        caret = run_combat_radius_json({'action': 'predict_ld', 'params': {'target': tgt}})
        dsi_tgt = dict(tgt)
        dsi_tgt['inlet'] = 'dsi'
        dsi = run_combat_radius_json({'action': 'predict_ld', 'params': {'target': dsi_tgt}})
        assert caret['success'] is True and dsi['success'] is True
        assert caret['target']['CD0'] > dsi['target']['CD0']
        assert caret['target']['ld'] < dsi['target']['ld']
    j20 = get_preset_by_id(presets, 'J-20')
    assert j20['inlet'] == 'dsi'
    f35 = get_preset_by_id(presets, 'F-35C')
    assert f35['inlet'] == 'dsi'


@pytest.mark.e2e
def test_e2e_combat_radius_uav_and_j36_weight_fields():
    """无人机零飞行员、歼-36 三发双座须进入空战重量。"""
    presets = load_presets()
    uav = get_preset_by_id(presets, '53636')
    assert uav['n_pilots'] == 0
    assert uav['length_m'] == pytest.approx(14.6)
    uav535 = get_preset_by_id(presets, '53536')
    assert uav535['length_m'] == pytest.approx(16.7)
    assert uav535['bwb'] is True
    assert uav535['planform'] == 'diamond'
    j35 = get_preset_by_id(presets, 'J-35')
    j35a = get_preset_by_id(presets, 'J-35A')
    assert j35['length_m'] == pytest.approx(17.7)
    assert j35a['length_m'] == pytest.approx(17.7)
    j36 = get_preset_by_id(presets, 'J-36')
    assert j36['n_engines'] == 3
    assert j36['n_pilots'] == 2
    assert j36['sweep_inner_deg'] == pytest.approx(67.8)
    assert j36['sweep_outer_deg'] == pytest.approx(55.3)
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
def test_e2e_combat_radius_j36_two_segment_sweep_dashboard():
    """歼-36 双三角两段后掠须进入仪表盘，且超音速波阻高于单段 65.1°。"""
    from utils.combat_radius.lift_drag import (
        aircraft_from_dict,
        cd_wave_supersonic,
        has_double_delta_sweep,
    )

    presets = load_presets()
    j36 = get_preset_by_id(presets, 'J-36')
    ac = aircraft_from_dict(j36)
    assert has_double_delta_sweep(ac) is True
    one = aircraft_from_dict({**j36, 'sweep_inner_deg': 0, 'sweep_outer_deg': 0})
    assert has_double_delta_sweep(one) is False
    two_hi = aircraft_from_dict({**j36, 'mach': 1.90, 'alt_m': 11000})
    one_hi = aircraft_from_dict({**j36, 'mach': 1.90, 'alt_m': 11000, 'sweep_inner_deg': 0, 'sweep_outer_deg': 0})
    assert cd_wave_supersonic(1.90, two_hi, 0.0) > cd_wave_supersonic(1.90, one_hi, 0.0)
    r = run_combat_radius_json({'action': 'predict_ld', 'params': {'target': j36}})
    assert r['success'] is True
    assert 6.0 < r['target']['ld'] < 12.0
    dash = run_combat_radius_json({
        'action': 'aircraft_dashboard',
        'params': {
            'target': j36,
            'empty_kg': j36['empty_kg'],
            'internal_fuel_kg': j36['internal_fuel_kg'],
            'n_pilots': j36['n_pilots'],
            'missile_mass_kg': j36['missile_mass_kg'],
            'n_engines': j36['n_engines'],
            'bpr': 0.25, 'opr': 29.0, 't4_K': 1975, 'tsl_kN': 132.4,
            'max_tsl_kN': 185.0,
        },
    })
    assert dash['success'] is True
    assert dash.get('points')


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
    assert 'Ma 0.8 / 1.0 / 1.2 / 1.35 / 1.5 / 1.75 / 2.0' in html_text
    wxml = (ROOT / 'miniprogram' / 'pages' / 'combat_radius' / 'combat_radius.wxml').read_text(encoding='utf-8')
    assert '飞机作战半径估算终端' in wxml
    assert '搜索最佳升阻比和巡航高度' in wxml
    assert '计算作战半径' in wxml
    assert 'function requestLiveDash' in js_text
    assert 'onRunDash' in (ROOT / 'miniprogram' / 'pages' / 'combat_radius' / 'combat_radius.js').read_text(encoding='utf-8')
    assert '混合作战半径' in wxml
    assert '最大 L/D' in wxml
    assert '速度/马赫' in wxml
    assert '实用最大巡航速度' in wxml
    assert '最大巡航速度' in wxml
    assert 'Ma 1.2 以上' in wxml
    assert '达到最大值时的速度' in wxml
    assert 'dashSplitNote' not in wxml
    assert '作战半径最大' in wxml
    assert '最大半径超音速巡航速度' in wxml
    assert '表下会并排' not in wxml
    assert '>点</text>' not in wxml
    assert '>Ma</text>' not in wxml
    assert '热效率' in js_text
    assert '推进效率' in js_text
    assert '总效率' in js_text
    assert '<th>速度/马赫</th>' in js_text
    assert '实用最大巡航速度' in js_text
    assert 'Ma 1.2 以上' in js_text
    assert '达到最大值时的速度' in js_text
    assert 'split_cruise_note' not in js_text
    assert '作战半径最大' in js_text
    assert '最大半径超音速巡航速度' in js_text
    assert '表下会并排' not in js_text
    assert 'cruiseSpeedLabel' in js_text
    assert '<th>平均油耗 kg/km</th>' in js_text
    assert '<th>点</th>' not in js_text
    assert '<th>Ma</th>' not in js_text
    assert '<th>η_th</th>' not in js_text
    cr_mp = (ROOT / 'miniprogram' / 'pages' / 'combat_radius' / 'combat_radius.js').read_text(encoding='utf-8')
    assert '热效率' in cr_mp
    assert '推进效率' in cr_mp
    assert '总效率' in cr_mp
    assert 'η_th' not in cr_mp
    assert '锚点' not in wxml
    assert 'search_best_cruise' in js_text
    assert 'estimate_engine_cycle' in js_text
    ios = (ROOT / 'ios' / 'CarrierTakeOff' / 'CombatRadiusView.swift').read_text(encoding='utf-8')
    assert '飞机作战半径估算终端' in ios
    assert '搜索最佳升阻比和巡航高度' in ios
    assert '计算作战半径' in ios
    assert '混合作战半径' in ios
    assert '实用最大巡航速度' in ios
    assert 'Ma 1.2 以上' in ios
    assert '达到最大值时的速度' in ios
    assert 'split_cruise_note' not in ios
    assert '作战半径最大' in ios
    assert '最大半径超音速巡航速度' in ios
    assert '表下会并排' not in ios
    assert 'func cruiseSpeedLabel' in ios
    assert '最大 L/D' in ios
    assert '热效率' in ios
    assert '推进效率' in ios
    assert '总效率' in ios
    assert 'η_th' not in ios
    assert 'p.label' in ios
    assert 'max_possible_cruise' in ios
    assert '锚点' not in ios
    assert 'maxLd' in js_text
    assert 'runCombatRadius' in (ROOT / 'ios' / 'CarrierTakeOff' / 'LocalSimulatorEngine.swift').read_text(encoding='utf-8')
    assert 'engine_id' in js_text
    assert 'resolveTslKN' in js_text
    assert 'engine_id' in (ROOT / 'miniprogram' / 'pages' / 'combat_radius' / 'combat_radius.js').read_text(encoding='utf-8')
    ios_vm = (ROOT / 'ios' / 'CarrierTakeOff' / 'CombatRadiusViewModel.swift').read_text(encoding='utf-8')
    assert 'engine_id' in ios_vm
    assert 'wtCarrier' in ios_vm
    assert 'func requestLiveDash' in ios_vm
    assert '舰载机' in html_text
    assert '舰载机' in wxml
    assert '舰载机' in ios
    assert '内段前缘后掠' in js_text
    assert '外段前缘后掠' in js_text
    assert 'tgt_sweep_inner' in js_text
    assert '内段前缘后掠' in wxml
    assert '外段前缘后掠' in wxml
    assert 'sweep_inner_deg' in cr_mp
    assert '内段前缘后掠' in ios
    assert '外段前缘后掠' in ios
    assert 'sweepInnerDeg' in ios_vm
    assert 'fail_reason' in js_text


@pytest.mark.e2e
def test_e2e_combat_radius_j15_radius_uses_csv_engine():
    """合并库中的歼-15 须能带 CSV 发动机走完布雷盖作战半径。"""
    from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets

    presets = load_presets()
    engines = load_engine_presets()
    tgt = get_preset_by_id(presets, 'J-15')
    eng = get_preset_by_id(engines, tgt['engine_id'])
    assert eng is not None
    assert tgt['carrier'] is True
    r = run_combat_radius_json({
        'action': 'estimate_radius',
        'params': {
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
    assert r['mission_fuel']['reserve_min'] == 45
    assert r['fuel_usable_kg'] < r['fuel_kg']


@pytest.mark.e2e
def test_e2e_combat_radius_f22_max_speed_uses_ab_thrust():
    """F-22 + F119 加力最大速度须可走通 estimate_max_speed。"""
    presets = load_presets()
    engines = load_engine_presets()
    tgt = get_preset_by_id(presets, 'F-22')
    eng = get_preset_by_id(engines, 'f119')
    assert eng['max_tsl_kN'] == 156.0
    base = {
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
    }
    r = run_combat_radius_json({'action': 'estimate_max_speed', 'params': base})
    assert r['success'] is True
    assert r['feasible'] is True
    assert r['max_speed_mach'] > 1.0
    assert r['max_speed_kmh'] > 1200
    assert r['ld'] > 0
    assert 'profile' in r
    assert r['thrust_margin'] == pytest.approx(1.0)
    assert r['load'] <= 1.0 + 1e-6
    r92 = run_combat_radius_json({
        'action': 'estimate_max_speed',
        'params': {**base, 'thrust_margin': 0.92},
    })
    assert r92['feasible'] is True
    assert r['max_speed_mach'] > r92['max_speed_mach']


@pytest.mark.e2e
def test_e2e_combat_radius_f35_max_speed_near_mach_16():
    """F-35A/C 加力极速须贴近公开 Ma 1.6，且 F-22 贴近公开 Ma 2.25。"""
    presets = load_presets()
    engines = load_engine_presets()
    for ac_id in ('F-35A', 'F-35C'):
        tgt = get_preset_by_id(presets, ac_id)
        eng = get_preset_by_id(engines, tgt['engine_id'])
        r = run_combat_radius_json({
            'action': 'estimate_max_speed',
            'params': {
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
        assert r['success'] is True and r['feasible'] is True, ac_id
        assert r['max_speed_mach'] == pytest.approx(F35_MAX_SPEED_MACH, abs=0.12), ac_id
    f22 = get_preset_by_id(presets, 'F-22')
    f119 = get_preset_by_id(engines, 'f119')
    r22 = run_combat_radius_json({
        'action': 'estimate_max_speed',
        'params': {
            'target': f22,
            'empty_kg': f22['empty_kg'],
            'internal_fuel_kg': f22['internal_fuel_kg'],
            'n_pilots': f22['n_pilots'],
            'missile_mass_kg': f22['missile_mass_kg'],
            'n_engines': f22['n_engines'],
            'bpr': f119['bpr'],
            'opr': f119['opr'],
            't4_K': f119['t4_K'],
            'max_tsl_kN': f119['max_tsl_kN'],
        },
    })
    assert r22['max_speed_mach'] == pytest.approx(F22_MAX_SPEED_MACH, abs=0.08)


@pytest.mark.e2e
def test_e2e_combat_radius_f35c_engine_install_applied():
    """F135 安装惩罚须进入仪表盘，F-35C Ma0.8 半径约 1318 km；F-22 不受影响。"""
    from utils.combat_radius.combat_radius_results import run_preset_dashboard
    from utils.combat_radius.engine_efficiency import F135_TSFC_INSTALL_MULT

    engines = load_engine_presets()
    f135 = get_preset_by_id(engines, 'f135')
    f119 = get_preset_by_id(engines, 'f119')
    assert f135['tsfc_install_mult'] == pytest.approx(F135_TSFC_INSTALL_MULT)
    assert f119['tsfc_install_mult'] == pytest.approx(1.0)
    f35c = run_preset_dashboard('F-35C')
    f22 = run_preset_dashboard('F-22')
    m08 = next(p for p in f35c['points'] if p['id'] == 'mach_0_8')
    m08_22 = next(p for p in f22['points'] if p['id'] == 'mach_0_8')
    assert m08['feasible'] is True
    assert m08['radius_km'] == pytest.approx(1318, abs=50)
    assert m08_22['radius_km'] == pytest.approx(1034, abs=50)


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
    assert len(f22['points']) == 10
    assert f22['points'][-2]['label'] == '最大半径超音速巡航速度'
    assert f22['points'][-1]['label'] == '最大巡航速度'
    assert f22.get('max_radius_mach') is not None
    assert f22['max_radius_mach'] == pytest.approx(1.58, abs=0.03)
    assert f22['max_speed']['max_speed_mach'] == pytest.approx(F22_MAX_SPEED_MACH, abs=0.08)
    assert 'split_cruise_note' not in f22
    live = run_preset_dashboard('F-22')
    assert live['success'] is True
    live_m08 = next(p for p in live['points'] if p['id'] == 'mach_0_8')
    stored_m08 = next(p for p in f22['points'] if p['id'] == 'mach_0_8')
    assert live_m08['radius_km'] == pytest.approx(stored_m08['radius_km'], rel=1e-4, abs=0.05)
    assert     live['max_cruise_mach'] == pytest.approx(f22['max_cruise_mach'], rel=1e-4, abs=1e-4)
    j20 = stored['aircraft']['J-20']
    assert j20['success'] is True
    assert j20['max_cruise_mach'] == pytest.approx(J20_SUPERCRUISE_MACH, abs=0.02)
    assert j20['max_speed']['max_speed_mach'] > 2.0
    j50 = stored['aircraft']['J-50']
    assert j50['success'] is True
    assert j50['max_possible_cruise_mach'] > f22['max_possible_cruise_mach']
    assert j50['max_cruise_mach'] == pytest.approx(1.76, abs=0.005)
    j50_m08 = next(p for p in j50['points'] if p['id'] == 'mach_0_8')
    f22_m08 = next(p for p in f22['points'] if p['id'] == 'mach_0_8')
    assert j50_m08['alt_m'] >= f22_m08['alt_m']
    f35c = stored['aircraft']['F-35C']
    assert f35c['success'] is True
    assert f35c['max_speed']['max_speed_mach'] == pytest.approx(F35_MAX_SPEED_MACH, abs=0.12)
    f35c_m15 = next(p for p in f35c['points'] if p['id'] == 'mach_1_5')
    assert f35c_m15['max_ld'] is not None and f35c_m15['max_ld'] > 0
    j15 = stored['aircraft']['J-15']
    assert j15['success'] is True
    assert j15['max_speed']['feasible'] is True
    assert j15['max_speed']['max_speed_mach'] > 1.0
    av8 = stored['aircraft']['AV-8B']
    assert av8['max_speed']['feasible'] is False
    f35a = stored['aircraft']['F-35A']
    assert f35a['success'] is True
    assert f35a['max_speed']['max_speed_mach'] == pytest.approx(F35_MAX_SPEED_MACH, abs=0.12)
    j35 = stored['aircraft']['J-35']
    j35a = stored['aircraft']['J-35A']
    assert j35['max_cruise_mach'] is None
    assert j35a['max_cruise_mach'] == pytest.approx(J35A_SUPERCRUISE_MACH, abs=0.03)
    for aid in ('53636', '53536', '53636N'):
        assert stored['aircraft'][aid]['max_cruise_mach'] is None, aid
    for aid, row in stored['aircraft'].items():
        mach = row.get('max_cruise_mach')
        floor = row.get('max_possible_cruise_mach')
        if mach is not None:
            assert mach + 1e-9 >= 1.2, aid
            assert floor is not None, aid
            assert floor + 1e-9 >= mach, aid
    fa18c = stored['aircraft']['FA-18C']
    assert fa18c['max_cruise_mach'] is not None
    assert fa18c['max_possible_cruise_mach'] > fa18c['max_cruise_mach']
    fa18c_m12 = next(p for p in fa18c['points'] if p['id'] == 'mach_1_2')
    assert fa18c_m12['feasible'] is False


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
    p['mach'] = 2.2
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


@pytest.mark.e2e
def test_e2e_combat_radius_modified_params_recompute_dashboard():
    """改机型/发动机参数后，aircraft_dashboard 须重算各速度结果（对应「计算作战半径」）。"""
    p = _radius_params()
    p['max_tsl_kN'] = 156.0
    base = run_combat_radius_json({'action': 'aircraft_dashboard', 'params': p})
    assert base['success'] is True
    q = dict(p)
    q['empty_kg'] = p['empty_kg'] * 1.2
    q['tsl_kN'] = p['tsl_kN'] * 0.8
    q['opr'] = p['opr'] + 4.0
    live = run_combat_radius_json({'action': 'aircraft_dashboard', 'params': q})
    assert live['success'] is True
    base_ids = {pt['id'] for pt in base['points']}
    live_ids = {pt['id'] for pt in live['points']}
    for mid in ('mach_0_8', 'mach_1_0', 'mach_1_2', 'mach_1_5', 'mach_2_0'):
        assert mid in base_ids and mid in live_ids
    b08 = next(pt for pt in base['points'] if pt['id'] == 'mach_0_8')
    l08 = next(pt for pt in live['points'] if pt['id'] == 'mach_0_8')
    assert b08['feasible'] is True and l08['feasible'] is True
    assert l08['radius_km'] != b08['radius_km']
    status, _, body = handle_request(
        'POST', '/api/combat_radius/simulate',
        json.dumps({'action': 'aircraft_dashboard', 'params': q}).encode(),
    )
    assert status == 200
    http = json.loads(body.decode())
    assert http['success'] is True
    assert http['points'][0]['id'] == live['points'][0]['id']
