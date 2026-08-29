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
    ios = (ROOT / 'ios' / 'CarrierTakeOff' / 'CombatRadiusView.swift').read_text(encoding='utf-8')
    assert '飞机作战半径估算终端' in ios
    assert '估算可用军推' in ios
    assert 'runThrust' in (ROOT / 'ios' / 'CarrierTakeOff' / 'CombatRadiusViewModel.swift').read_text(encoding='utf-8')
    assert 'runCombatRadius' in (ROOT / 'ios' / 'CarrierTakeOff' / 'LocalSimulatorEngine.swift').read_text(encoding='utf-8')
