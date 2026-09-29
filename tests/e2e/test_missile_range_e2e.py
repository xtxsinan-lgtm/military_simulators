"""导弹射程估算端到端：API、目录与三端页面契约。"""
from __future__ import annotations

import json

import pytest

from apps.miniprogram_api import handle_request
from scripts.frontend_catalog import SIMULATORS, build_catalog_payload
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.missile_range.dataset import MISSILE_DATASET, evaluate_case
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV, ROOT


@pytest.mark.e2e
def test_e2e_missile_range_api_matches_dataset():
    """小程序 API 估算结果须与预设样本逐条一致。"""
    case = MISSILE_DATASET[0]
    payload = {
        'action': 'estimate',
        'params': {
            'length_m': case['length'],
            'diameter_m': case['diameter'],
            'warhead_kg': case['warhead'],
            'hgv_type': case['type'],
            'v_launch_mach': case['v_mach'],
            'h_launch_km': case['h_km'],
        },
    }
    status, _, body = handle_request(
        'POST', '/api/missile_range/simulate', json.dumps(payload).encode(),
    )
    assert status == 200
    data = json.loads(body.decode())
    assert data['success'] is True
    assert data['result'] == {
        k: evaluate_case(case)[k]
        for k in (
            'm_0_t', 'l_head_m', 'l_booster_m', 'm_p_total_kg',
            'v_burnout_mach', 'ld_ratio', 'range_km',
        )
    }
    assert len(data['rows']) == len(MISSILE_DATASET)

    empty_status, _, empty_body = handle_request('POST', '/api/missile_range/simulate', b'')
    assert empty_status == 400
    assert json.loads(empty_body.decode())['success'] is False


@pytest.mark.e2e
def test_e2e_missile_range_catalog_and_pages():
    """目录、启动页与各端页面都登记导弹射程。"""
    payload = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    assert any(s['id'] == 'missile_range' for s in SIMULATORS)
    assert payload['missile_range']['cases'][0]['range_km'] == evaluate_case(MISSILE_DATASET[0])['range_km']

    status, _, body = handle_request('GET', '/api/data', None)
    api = json.loads(body.decode())
    assert status == 200
    assert any(s['id'] == 'missile_range' for s in api['simulators'])
    assert len(api['missile_range']['cases']) == 16

    html = (ROOT / 'docs' / 'missile-range.html').read_text(encoding='utf-8')
    js = (ROOT / 'docs' / 'js' / 'missile_range.js').read_text(encoding='utf-8')
    assert 'missile_range.js' in html
    assert 'run_missile_range_json' in js
    assert 'missile-range.html' in (ROOT / 'docs' / 'takeoff.html').read_text(encoding='utf-8')
    assert 'missile-range.html' in (ROOT / 'docs' / 'combat-radius.html').read_text(encoding='utf-8')
    mini = json.loads((ROOT / 'miniprogram' / 'app.json').read_text(encoding='utf-8'))
    assert 'pages/missile_range/missile_range' in mini['pages']
    hub = (ROOT / 'ios' / 'CarrierTakeOff' / 'HubView.swift').read_text(encoding='utf-8')
    assert 'MissileRangeView' in hub
