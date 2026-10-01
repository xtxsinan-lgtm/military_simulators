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
            'missile_class': 'hgv_biconic',
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
    assert len(data['rows']) == len(all_missile_cases())

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
    assert 'type_labels' not in payload['missile_range']
    assert 'hgv_type' not in payload['missile_range']['defaults']
    assert (ROOT / 'data' / 'missile_range_preset_database.csv').is_file()

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
    assert 'utils/database_csv.py' in js
    assert 'data/missile_range_preset_database.csv' in js
    assert 'py_data_files' in (ROOT / 'ios' / 'CarrierTakeOff' / 'Resources' / 'engine.js').read_text(encoding='utf-8')
    assert '全高空' in js
    assert '全掠海' in js
    assert '载机' in js
    assert '折叠弹翼' in js
    assert 'missile-range.html' in (ROOT / 'docs' / 'takeoff.html').read_text(encoding='utf-8')
    assert 'missile-range.html' in (ROOT / 'docs' / 'combat-radius.html').read_text(encoding='utf-8')
    mini = json.loads((ROOT / 'miniprogram' / 'app.json').read_text(encoding='utf-8'))
    assert 'pages/missile_range/missile_range' in mini['pages']
    hub = (ROOT / 'ios' / 'CarrierTakeOff' / 'HubView.swift').read_text(encoding='utf-8')
    assert 'MissileRangeView' in hub
    view = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileRangeView.swift').read_text(encoding='utf-8')
    assert '全掠海' in view
    assert '载机' in view
    assert '折叠弹翼' in view
    mini_js = (ROOT / 'miniprogram' / 'pages' / 'missile_range' / 'missile_range.js').read_text(encoding='utf-8')
    assert 'missile_class' in mini_js
    mini_wxml = (ROOT / 'miniprogram' / 'pages' / 'missile_range' / 'missile_range.wxml').read_text(encoding='utf-8')
    assert '载机' in mini_wxml
    assert '折叠弹翼' in mini_wxml


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
        if missile_class in ('turbofan_stealth', 'turbojet_subsonic', 'turbofan_rocket', 'ramjet'):
            assert data['result']['range_high_km'] > data['result']['range_sea_km'] > 0
        if missile_class == 'turbofan_rocket':
            assert data['result']['range_terminal_km'] > 0


def _estimate_via_api(missile_class, length, diameter, warhead, mach, height):
    """走小程序 API 估算一发导弹。"""
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
    return data['result']


@pytest.mark.e2e
def test_e2e_russian_ramjet_and_dual_mode_anchors():
    """API 上鹰击-15 高空约 800 km、约 1.5 t，3M54K 掠海约 550–660 km。"""
    yj15 = _estimate_via_api('ramjet', 6.5, 0.50, 200, 0.9, 12.0)
    assert 770 <= yj15['range_high_km'] <= 830
    assert abs(yj15['m_0_t'] - 1.50) <= 0.05
    kalibr = _estimate_via_api('turbofan_rocket', 8.22, 0.533, 200, 0.0, 0.0)
    assert 550 <= kalibr['range_sea_km'] <= 680
    assert 18 <= kalibr['range_terminal_km'] <= 26
    # 只给最大外廓时按 LRASM 高宽比收成扁五边形。掠海/全高空取 400/950，高空航程不因这次标定改动。
    lrasm = _estimate_via_api('turbofan_stealth', 4.26, 0.635, 450, 0.85, 10.0)
    assert lrasm['range_high_km'] == 967.6
    assert lrasm['range_sea_km'] / lrasm['range_high_km'] == pytest.approx(400 / 950, abs=0.001)
    low = _estimate_via_api('turbofan_stealth', 4.26, 0.635, 450, 0.85, 0.2)
    assert low['range_sea_km'] == lrasm['range_sea_km']
    assert low['range_high_km'] < lrasm['range_high_km']


@pytest.mark.e2e
def test_e2e_airbreathing_presets_differ_from_glide_and_ballistic():
    """同一套几何下，吸气式射程不沿用助推滑翔或弹道结果。"""
    from utils.missile_range.dataset import evaluate_dataset

    rows = evaluate_dataset()
    shared = [
        row for row in rows
        if row['length_m'] == 10.5 and row['diameter_m'] == 1.1 and row['warhead_kg'] == 200
    ]
    by_class = {row['missile_class']: row for row in shared}
    assert by_class['hgv_biconic']['range_km'] - by_class['ballistic']['range_km'] > 1000
    assert by_class['hgv_biconic']['range_km'] != by_class['scramjet']['range_km']
    assert by_class['scramjet']['range_km'] != by_class['ramjet']['range_km']
    assert by_class['ramjet']['range_km'] != by_class['ballistic']['range_km']
    assert by_class['scramjet']['range_sea_km'] is None
    assert by_class['ballistic']['range_sea_km'] is None
    subsonic = next(row for row in rows if row['missile_class'] == 'turbofan_stealth')
    assert subsonic['m_wing_kg'] > 0
    assert subsonic['range_high_km'] > subsonic['range_sea_km']
    assert '折叠弹翼' in subsonic['note']
    payload = {
        'action': 'estimate',
        'params': {
            'missile_class': 'turbofan_stealth',
            'length_m': subsonic['length_m'],
            'diameter_m': subsonic['diameter_m'],
            'warhead_kg': subsonic['warhead_kg'],
            'v_launch_mach': subsonic['v_mach'],
            'h_launch_km': subsonic['h_km'],
        },
    }
    status, _, body = handle_request(
        'POST', '/api/missile_range/simulate', json.dumps(payload).encode(),
    )
    assert status == 200
    data = json.loads(body.decode())
    assert data['result']['range_km'] == subsonic['range_km']
    assert data['result']['m_wing_kg'] == subsonic['m_wing_kg']
    assert data['result']['missile_class'] == 'turbofan_stealth'
