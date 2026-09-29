"""导弹射程估算端到端：API、目录与三端页面契约。"""
from __future__ import annotations

import json

import pytest

from apps.miniprogram_api import handle_request
from scripts.frontend_catalog import SIMULATORS, build_catalog_payload
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.missile_range.dataset import MISSILE_DATASET, all_missile_cases, evaluate_case
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
    expected = evaluate_case(case)
    numeric = (
        'm_0_t', 'l_head_m', 'l_booster_m', 'm_p_total_kg',
        'v_burnout_mach', 'ld_ratio', 'range_km',
    )
    assert {k: data['result'][k] for k in numeric} == {k: expected[k] for k in numeric}
    assert data['result']['missile_class'] == 'hgv_biconic'
    assert len(data['rows']) == len(MISSILE_DATASET) + 12

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
    assert len(api['missile_range']['cases']) == len(all_missile_cases())
    class_ids = {item['id'] for item in api['missile_range']['classes']}
    assert {'hgv_biconic', 'hgv_waverider', 'scramjet', 'ramjet', 'turbofan_stealth', 'turbojet_subsonic', 'turbofan_rocket', 'ballistic'} <= class_ids
    assert 'hgv' not in class_ids

    html = (ROOT / 'docs' / 'missile-range.html').read_text(encoding='utf-8')
    js = (ROOT / 'docs' / 'js' / 'missile_range.js').read_text(encoding='utf-8')
    assert 'missile_range.js' in html
    assert 'missileClass' in html
    assert 'hgvType' not in html
    assert '构型' not in html
    assert 'run_missile_range_json' in js
    assert 'utils/missile_range/classes.py' in js
    assert '全高空' in js
    assert '全掠海' in js
    assert 'missile-range.html' in (ROOT / 'docs' / 'takeoff.html').read_text(encoding='utf-8')
    assert 'missile-range.html' in (ROOT / 'docs' / 'combat-radius.html').read_text(encoding='utf-8')
    mini = json.loads((ROOT / 'miniprogram' / 'app.json').read_text(encoding='utf-8'))
    assert 'pages/missile_range/missile_range' in mini['pages']
    hub = (ROOT / 'ios' / 'CarrierTakeOff' / 'HubView.swift').read_text(encoding='utf-8')
    assert 'MissileRangeView' in hub
    view = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileRangeView.swift').read_text(encoding='utf-8')
    assert '全掠海' in view
    mini_js = (ROOT / 'miniprogram' / 'pages' / 'missile_range' / 'missile_range.js').read_text(encoding='utf-8')
    assert 'missile_class' in mini_js


@pytest.mark.e2e
def test_e2e_missile_range_six_classes():
    """六类弹种都能从 API 算出正射程，巡航弹的全高空大于全掠海。"""
    samples = [
        ('scramjet', 9.2, 0.7, 180, 0.85, 12),
        ('ramjet', 8.9, 0.7, 250, 0.85, 12),
        ('turbofan_stealth', 6.2, 0.55, 450, 0.7, 0.2),
        ('turbojet_subsonic', 6.2, 0.55, 450, 0.7, 0.2),
        ('turbofan_rocket', 8.2, 0.53, 300, 0.7, 0.05),
        ('ballistic', 11.2, 0.88, 980, 0, 0),
    ]
    for missile_class, length, diameter, warhead, mach, height in samples:
        payload = {
            'action': 'estimate',
            'params': {
                'missile_class': missile_class,
                'length_m': length,
                'diameter_m': diameter,
                'warhead_kg': warhead,
                'v_launch_mach': mach,
                'h_launch_km': height,
            },
        }
        status, _, body = handle_request(
            'POST', '/api/missile_range/simulate', json.dumps(payload).encode(),
        )
        assert status == 200
        data = json.loads(body.decode())
        assert data['success'] is True, data
        assert data['result']['missile_class'] == missile_class
        assert data['result']['range_km'] > 0
        if missile_class in ('turbofan_stealth', 'turbojet_subsonic', 'turbofan_rocket'):
            assert data['result']['range_high_km'] > data['result']['range_sea_km'] > 0
        if missile_class == 'turbofan_rocket':
            assert data['result']['range_terminal_km'] > 0
