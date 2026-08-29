"""miniprogram_api 单元测试。"""
from __future__ import annotations

import json

from apps.miniprogram_api import build_data_payload, handle_request


def test_get_api_data_returns_aircraft_and_carriers():
    status, headers, body = handle_request('GET', '/api/data', None)
    assert status == 200
    assert 'application/json' in headers['Content-Type']
    data = json.loads(body.decode())
    assert 'aircraft' in data and len(data['aircraft']) >= 1
    assert 'carriers' in data and len(data['carriers']) >= 1
    assert data['modes']['ski_jump'] == '滑跃起飞'
    assert 'missile_interception_presets' in data
    assert 'asm' in data['missile_interception_presets']
    assert 'combat_radius_presets' in data
    assert 'combat_radius_engine_presets' in data
    assert any(p['id'] == 'J-20' for p in data['combat_radius_presets'])
    assert any(p['id'] == 'f119' for p in data['combat_radius_engine_presets'])


def test_post_missile_interception_simulate_success():
    """饱和打击 API 返回窗口与最优方案。"""
    payload = {
        'action': 'simulate',
        'params': {
            'nm': 24, 'vm': 2.6, 'D': 120, 'ni': 16, 'vi': 3.8,
            'pk': 0.7, 'tlock': 6, 'minr': 3, 'fast': True,
        },
    }
    status, _, body = handle_request(
        'POST', '/api/missile_interception/simulate', json.dumps(payload).encode(),
    )
    assert status == 200
    result = json.loads(body.decode())
    assert result['success'] is True
    assert result['n_rounds'] >= 1
    assert 'best' in result


def test_post_combat_radius_simulate_success():
    """作战半径 API 返回标定系数与待估 L/D。"""
    from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_presets

    presets = load_presets()
    payload = {
        'action': 'predict_ld',
        'params': {
            'anchor1': get_preset_by_id(presets, 'F-35C'),
            'ld1_target': 8.8,
            'anchor2': get_preset_by_id(presets, 'F-22'),
            'ld2_target': 8.0,
            'target': get_preset_by_id(presets, 'J-20'),
        },
    }
    status, _, body = handle_request(
        'POST', '/api/combat_radius/simulate', json.dumps(payload).encode(),
    )
    assert status == 200
    result = json.loads(body.decode())
    assert result['success'] is True
    assert result['Cf0'] > 0
    assert 7.0 < result['target']['ld'] < 10.0


def test_post_combat_radius_estimate_thrust_success():
    """作战半径 API 按发动机参数返回可用军推。"""
    payload = {
        'action': 'estimate_thrust',
        'params': {
            'bpr': 0.30, 'opr': 26.0, 't4_K': 1922, 'tsl_kN': 116.0,
            'alt_m': 11000, 'mach': 1.5,
        },
    }
    status, _, body = handle_request(
        'POST', '/api/combat_radius/simulate', json.dumps(payload).encode(),
    )
    assert status == 200
    result = json.loads(body.decode())
    assert result['success'] is True
    assert 10.0 < result['thrust_kN'] < 116.0
    assert result['alpha'] < 1.0


def test_post_combat_radius_estimate_efficiency_success():
    """作战半径 API 返回巡航负载、总效率与 TSFC。"""
    from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_presets

    presets = load_presets()
    f22 = get_preset_by_id(presets, 'F-22')
    payload = {
        'action': 'estimate_efficiency',
        'params': {
            'anchor1': get_preset_by_id(presets, 'F-35C'),
            'ld1_target': 8.8,
            'anchor2': f22,
            'ld2_target': 8.0,
            'target': f22,
            'empty_kg': f22['empty_kg'],
            'internal_fuel_kg': f22['internal_fuel_kg'],
            'n_pilots': f22['n_pilots'],
            'missile_mass_kg': f22['missile_mass_kg'],
            'n_engines': f22['n_engines'],
            'bpr': 0.30, 'opr': 26.0, 't4_K': 1922, 'tsl_kN': 116.0,
            'alt_m': f22['alt_m'], 'mach': f22['mach'],
        },
    }
    status, _, body = handle_request(
        'POST', '/api/combat_radius/simulate', json.dumps(payload).encode(),
    )
    assert status == 200
    result = json.loads(body.decode())
    assert result['success'] is True
    assert result['eta_o'] > 0
    assert result['tsfc_mg_n_s'] > 0


def test_options_returns_cors():
    status, headers, body = handle_request('OPTIONS', '/api/simulate', None)
    assert status == 204
    assert headers['Access-Control-Allow-Origin'] == '*'
    assert body == b''


def test_post_simulate_ski_jump_success():
    data = build_data_payload()
    carrier = next(c for c in data['carriers'] if c['id'] == 'SHANDONG')
    aircraft = next(a for a in data['aircraft'] if a['id'] == 'J-15')
    payload = {
        'mode': 'ski_jump',
        'aircraft': aircraft,
        'carrier': carrier,
        'mass_kg': 28000,
        'temp_c': 30,
        'wind_kt': carrier['max_speed_kt'],
        'total_deck_length_m': carrier['total_deck_length_m'],
        'ski_jump_angle_deg': carrier['ski_jump_angle_deg'],
    }
    status, _, body = handle_request('POST', '/api/simulate', json.dumps(payload).encode())
    assert status == 200
    result = json.loads(body.decode())
    assert 'success' in result
    assert 'output' in result


def test_unknown_route_404():
    status, _, body = handle_request('GET', '/unknown', None)
    assert status == 404
    assert json.loads(body.decode())['error'] == 'Not Found'


def test_post_simulate_invalid_payload_returns_json_not_500():
    """缺字段时不应抛未捕获异常（真机侧会显示 HTTP 500）。"""
    status, _, body = handle_request('POST', '/api/simulate', b'{}')
    assert status == 200
    result = json.loads(body.decode())
    assert result['success'] is False
    assert 'error' in result
