"""作战半径升阻比估算端到端测试。"""
from __future__ import annotations

import json

import pytest

from apps.combat_radius_web import run_combat_radius_json
from apps.miniprogram_api import handle_request
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_presets
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
    r = run_combat_radius_json({'action': 'predict_ld', 'params': _params_from_csv()})
    assert r['success'] is True
    assert r['anchors'][0]['ld'] == pytest.approx(8.8, abs=1e-8)
    assert r['anchors'][1]['ld'] == pytest.approx(8.0, abs=1e-8)
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
    r = run_combat_radius_json({'action': 'estimate_efficiency', 'params': _efficiency_params()})
    assert r['success'] is True
    assert r['ld'] == pytest.approx(8.0, abs=1e-6)
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
    """F-22 + F119 在 Ma 0.8 应给出正的作战半径；Ma 1.5 军推下可以不可行。"""
    r = run_combat_radius_json({'action': 'estimate_radius', 'params': _radius_params()})
    assert r['success'] is True
    assert len(r['points']) == 4
    m08 = next(p for p in r['points'] if p['id'] == 'mach_0_8')
    assert m08['feasible'] is True
    assert m08['radius_km'] > 200
    assert m08['fuel_kg_per_km'] > 0
    assert r['mach_cone_limit'] > 1
    assert r['max_cruise_mach'] is not None
    assert r['carrier'] is False
    mf = r['mission_fuel']
    assert mf['reserve_min'] == 30
    assert mf['climb_extra_kg'] > 0
    assert mf['descent_save_kg'] > 0
    assert r['fuel_usable_kg'] < r['fuel_kg']
    assert '亚音速油耗' in r['note']


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
    assert 'estimate_thrust' in js_text
    assert 'combat_radius.js' in html_text
    wxml = (ROOT / 'miniprogram' / 'pages' / 'combat_radius' / 'combat_radius.wxml').read_text(encoding='utf-8')
    assert '飞机作战半径估算终端' in wxml
    assert '估算可用军推' in wxml
    assert '估算负载与 TSFC' in wxml
    assert '估算作战半径' in wxml
    assert 'estimate_efficiency' in js_text
    assert 'estimate_radius' in js_text
    ios = (ROOT / 'ios' / 'CarrierTakeOff' / 'CombatRadiusView.swift').read_text(encoding='utf-8')
    assert '飞机作战半径估算终端' in ios
    assert '估算可用军推' in ios
    assert '估算负载与 TSFC' in ios
    assert '估算作战半径' in ios
    assert '马赫角' in html_text
    assert '马赫角' in wxml
    assert '马赫角' in ios
    assert 'runThrust' in (ROOT / 'ios' / 'CarrierTakeOff' / 'CombatRadiusViewModel.swift').read_text(encoding='utf-8')
    assert 'runEfficiency' in (ROOT / 'ios' / 'CarrierTakeOff' / 'CombatRadiusViewModel.swift').read_text(encoding='utf-8')
    assert 'runRadius' in (ROOT / 'ios' / 'CarrierTakeOff' / 'CombatRadiusViewModel.swift').read_text(encoding='utf-8')
    assert 'runCombatRadius' in (ROOT / 'ios' / 'CarrierTakeOff' / 'LocalSimulatorEngine.swift').read_text(encoding='utf-8')
    assert 'engine_id' in js_text
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
    assert 'profile' in r
