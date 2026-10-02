"""导弹射程估算端到端：API、目录与三端页面契约。"""
from __future__ import annotations

import json
from itertools import groupby

import pytest

from apps.miniprogram_api import handle_request
from scripts.frontend_catalog import SIMULATORS, build_catalog_payload
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.missile_range.dataset import MISSILE_DATASET, all_missile_cases, evaluate_case
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV, ROOT


def _assert_bays_sorted_by_size_then_range(cases: list[dict]) -> None:
    """同一载机连续成组：先按尺寸从大到小，同尺寸内射程从高到低。"""
    bays = [case['bay'] for case in cases]
    seen: set[str] = set()
    previous = None
    for bay in bays:
        if bay == previous:
            continue
        assert bay not in seen
        seen.add(bay)
        previous = bay
    h6 = [case for case in cases if case['bay'] == '轰-6机腹']
    largest = [case for case in cases if case['bay'] == '轰-6机腹最大']
    assert h6 and largest
    assert {(round(case['length_m'], 2), round(case['diameter_m'], 3)) for case in h6} == {(11.3, 0.86)}
    assert len({(case['length_m'], case['diameter_m']) for case in largest}) >= 2
    for _, bay_rows in groupby(cases, key=lambda case: case['bay']):
        rows = list(bay_rows)
        sizes = [(float(row['length_m']), float(row['diameter_m'])) for row in rows]
        assert sizes == sorted(sizes, key=lambda size: (-size[0], -size[1]))
        for _, size_rows in groupby(rows, key=lambda row: (float(row['length_m']), float(row['diameter_m']))):
            ranges = [float(row['range_km']) for row in size_rows]
            assert ranges == sorted(ranges, reverse=True)


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
    assert payload['missile_range']['cases'][0]['bay'] == '轰-6机腹最大'
    assert payload['missile_range']['cases'][0]['range_km'] >= payload['missile_range']['cases'][1]['range_km']
    _assert_bays_sorted_by_size_then_range(payload['missile_range']['cases'])
    assert 'type_labels' not in payload['missile_range']
    assert 'hgv_type' not in payload['missile_range']['defaults']
    assert payload['missile_range']['defaults']['ballistic_single_stage'] is False
    assert (ROOT / 'data' / 'missile_range_preset_database.csv').is_file()

    status, _, body = handle_request('GET', '/api/data', None)
    api = json.loads(body.decode())
    assert status == 200
    assert any(s['id'] == 'missile_range' for s in api['simulators'])
    assert len(api['missile_range']['cases']) == len(all_missile_cases())
    assert api['missile_range']['cases'][0]['bay'] == '轰-6机腹最大'
    assert api['missile_range']['cases'][0]['range_km'] >= api['missile_range']['cases'][1]['range_km']
    _assert_bays_sorted_by_size_then_range(api['missile_range']['cases'])
    class_ids = {item['id'] for item in api['missile_range']['classes']}
    assert {'hgv_biconic', 'hgv_waverider', 'scramjet', 'ramjet', 'turbofan_stealth', 'turbojet_subsonic', 'turbofan_rocket', 'ballistic'} <= class_ids
    assert 'hgv' not in class_ids

    html = (ROOT / 'docs' / 'missile-range.html').read_text(encoding='utf-8')
    js = (ROOT / 'docs' / 'js' / 'missile_range.js').read_text(encoding='utf-8')
    assert 'missile_range.js' in html
    assert 'missileClass' in html
    assert 'hgvType' not in html
    assert '构型' not in html
    assert '仅单级' in html
    assert '助推分级' in js
    assert 'optimizeGeometry' in html
    assert '寻优滑翔体尺寸' in html
    assert 'optimize_geometry' in js
    assert 'run_missile_range_json' in js
    assert 'utils/database_csv.py' in js
    assert 'data/missile_range_preset_database.csv' in js
    assert 'py_data_files' in (ROOT / 'ios' / 'CarrierTakeOff' / 'Resources' / 'engine.js').read_text(encoding='utf-8')
    assert '全高空' in js
    assert '全掠海' in js
    assert '混合弹道' in js
    assert '末端射程' not in js
    assert '吸气比冲' in html
    assert 'isp_air_s' in js
    assert '吸气比冲' in js
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
    assert '混合弹道' in view
    assert '载机' in view
    assert '折叠弹翼' in view
    assert '吸气比冲' in view
    assert '仅单级' in view
    assert '寻优滑翔体尺寸' in view
    mini_js = (ROOT / 'miniprogram' / 'pages' / 'missile_range' / 'missile_range.js').read_text(encoding='utf-8')
    assert 'missile_class' in mini_js
    mini_wxml = (ROOT / 'miniprogram' / 'pages' / 'missile_range' / 'missile_range.wxml').read_text(encoding='utf-8')
    assert '载机' in mini_wxml
    assert '混合弹道' in mini_wxml
    assert '折叠弹翼' in mini_wxml
    assert '末端射程' not in mini_wxml
    assert '末端冲刺' not in view
    assert '吸气比冲' in mini_wxml
    assert '仅单级' in mini_wxml
    assert '寻优滑翔体' in mini_wxml
    assert 'optimize_geometry' in mini_js


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
            assert data['result']['range_high_km'] > data['result']['range_mixed_km'] > data['result']['range_sea_km'] > 0
            assert '混合弹道' in data['result']['note']
        if missile_class in ('scramjet', 'ballistic'):
            assert data['result']['range_mixed_km'] is None
        if missile_class == 'turbofan_rocket':
            assert data['result']['range_terminal_km'] is None
            assert data['result']['range_high_km'] - data['result']['range_cruise_km'] == pytest.approx(33.6, abs=0.2)
            assert data['result']['isp_cruise_s'] > data['result']['isp_rocket_s']
        if missile_class in ('ramjet', 'scramjet'):
            assert data['result']['isp_cruise_s'] > data['result']['isp_boost_s']
        if missile_class == 'scramjet':
            assert data['result']['isp_cruise_s'] == pytest.approx(1200.0, abs=0.2)
            assert '燃烧室与固体助推分开' in data['result']['note']
            assert '高密度吸热型' in data['result']['note']
            assert '亚燃' not in data['result']['note']
        if missile_class == 'turbojet_subsonic':
            assert data['result']['isp_cruise_s'] == pytest.approx(2800.0, abs=0.2)
        if missile_class == 'ballistic':
            assert data['result']['isp_cruise_s'] is None
            assert data['result']['isp_rocket_s'] == 264.0


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
def test_e2e_russian_ramjet_anchors():
    """API 上鹰击-15 质量约 1.5 t，高空按偏乐观约 1140 km；掠海按 30 m 阻力估算。"""
    yj15 = _estimate_via_api('ramjet', 6.5, 0.50, 200, 0.9, 12.0)
    assert 1050 <= yj15['range_high_km'] <= 1250
    assert yj15['range_high_km'] > yj15['range_sea_km'] > 0
    assert yj15['cruise_alt_km'] == 10.0
    assert abs(yj15['m_0_t'] - 1.50) <= 0.05
    assert '30 m' in yj15['note']
    kalibr = _estimate_via_api('turbofan_rocket', 8.22, 0.533, 200, 0.0, 0.0)
    assert kalibr['range_high_km'] == 965.4
    assert kalibr['range_sea_km'] == 464.1
    assert kalibr['cruise_alt_km'] == 10.0
    assert kalibr['range_terminal_km'] is None
    jet = _estimate_via_api('turbojet_subsonic', 6.2, 0.55, 450, 0.85, 6.0)
    jet_low = _estimate_via_api('turbojet_subsonic', 6.2, 0.55, 450, 0.85, 0.2)
    assert jet['cruise_alt_km'] == 10.0
    assert jet['range_high_km'] > jet['range_sea_km'] > 0
    assert jet_low['range_sea_km'] == pytest.approx(jet['range_sea_km'], abs=0.5)
    assert jet_low['range_high_km'] < jet['range_high_km']
    # 只给最大外廓时按 LRASM 高宽比收成扁五边形。高空航程不因掠海阻力模型改动。
    lrasm = _estimate_via_api('turbofan_stealth', 4.26, 0.635, 450, 0.85, 10.0)
    assert lrasm['range_high_km'] == 967.6
    assert lrasm['range_sea_km'] == 451.5
    assert lrasm['cruise_alt_km'] == 10.0
    low = _estimate_via_api('turbofan_stealth', 4.26, 0.635, 450, 0.85, 0.2)
    assert low['range_sea_km'] == lrasm['range_sea_km']
    assert low['range_high_km'] < lrasm['range_high_km']


@pytest.mark.e2e
def test_e2e_ballistic_cylinder_warhead_matches_published_rockets():
    """普通弹道用头锥扣制导和战斗部。地面 PrSM 搜索后取单级 410.5 km。"""
    prsm = _estimate_via_api('ballistic', 4.0, 0.43, 91, 0.0, 0.0)
    assert prsm['range_km'] == 410.5
    assert prsm['n_stages'] == 1
    assert prsm['l_head_m'] == pytest.approx(1.35, abs=0.02)
    assert '单级' in prsm['note']
    assert '头锥扣除制导与战斗部' in prsm['note']
    gmlrs = _estimate_via_api('ballistic', 3.96, 0.227, 90, 0.0, 0.0)
    assert 65.0 <= gmlrs['range_km'] <= 92.0
    assert gmlrs['l_head_m'] > 0.5
    df15 = _estimate_via_api('ballistic', 9.1, 1.0, 500, 0.0, 0.0)
    assert df15['range_km'] == 487.2
    assert df15['m_p_total_kg'] == pytest.approx(4857.1, abs=0.2)
    payload = {
        'action': 'estimate',
        'params': {
            'missile_class': 'ballistic',
            'length_m': 11.3,
            'diameter_m': 0.86,
            'warhead_kg': 150,
            'v_launch_mach': 0.85,
            'h_launch_km': 13.0,
            'ballistic_single_stage': True,
        },
    }
    status, _, body = handle_request('POST', '/api/missile_range/simulate', json.dumps(payload).encode())
    assert status == 200
    locked = json.loads(body.decode())
    assert locked['success'] is True
    assert locked['result']['n_stages'] == 1
    assert '已锁定单级' in locked['result']['note']
    searched = _estimate_via_api('ballistic', 11.3, 0.86, 150, 0.85, 13.0)
    assert searched['n_stages'] == 3
    assert searched['stage_split']
    assert searched['range_km'] > locked['result']['range_km']
    glide = _estimate_via_api('hgv_biconic', 10.5, 1.1, 150, 0.85, 13.0)
    assert glide['n_stages'] in (2, 3)
    assert '/' in glide['stage_split']
    legacy_payload = {
        'action': 'estimate',
        'params': {
            'missile_class': 'ballistic',
            'length_m': 4.0,
            'diameter_m': 0.43,
            'warhead_kg': 91,
            'v_launch_mach': 0.0,
            'h_launch_km': 0.0,
            'ballistic_two_stage': False,
        },
    }
    status, _, body = handle_request('POST', '/api/missile_range/simulate', json.dumps(legacy_payload).encode())
    assert status == 200
    legacy = json.loads(body.decode())
    assert legacy['success'] is True
    assert legacy['result']['range_km'] == 410.5
    assert '单级' in legacy['result']['note']


@pytest.mark.e2e
def test_e2e_airbreathing_presets_differ_from_glide_and_ballistic():
    """同一套几何下，吸气式射程不沿用助推滑翔或弹道结果。"""
    from utils.missile_range.dataset import evaluate_dataset

    rows = evaluate_dataset()
    shared = []
    for missile_class in ('hgv_biconic', 'scramjet', 'ramjet', 'ballistic'):
        payload = {
            'action': 'estimate',
            'params': {
                'missile_class': missile_class,
                'length_m': 10.5,
                'diameter_m': 1.1,
                'warhead_kg': 150,
                'v_launch_mach': 0.85,
                'h_launch_km': 13.0,
            },
        }
        status, _, body = handle_request(
            'POST', '/api/missile_range/simulate', json.dumps(payload).encode(),
        )
        assert status == 200
        result = json.loads(body.decode())['result']
        result['missile_class'] = missile_class
        shared.append(result)
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


@pytest.mark.e2e
def test_e2e_bomber_small_warhead_presets_150kg():
    """轰-6机腹与隐身超音速轰炸机较小战斗部预设均为 150kg。"""
    payload = {'action': 'presets'}
    status, _, body = handle_request(
        'POST', '/api/missile_range/simulate', json.dumps(payload).encode(),
    )
    assert status == 200
    data = json.loads(body.decode())
    assert data['success'] is True

    cases = data['cases']
    h6_warheads = sorted({int(c['warhead_kg']) for c in cases if c['bay'] == '轰-6机腹'})
    assert h6_warheads == [150, 500]
    assert min(h6_warheads) == 150
    max_warheads = sorted({int(c['warhead_kg']) for c in cases if c['bay'] == '轰-6机腹最大'})
    assert max_warheads == [150, 600]

    stealth_warheads = sorted({int(c['warhead_kg']) for c in cases if c['bay'] == '隐身超音速轰炸机弹仓'})
    assert stealth_warheads == [150, 500]


@pytest.mark.e2e
def test_e2e_h6_stealth_bomber_matching_presets():
    """端到端验证：隐身超音速轰炸机全部导弹均有轰-6机腹同尺寸、调整高度与速度的对应版本。"""
    payload = {'action': 'presets'}
    status, _, body = handle_request(
        'POST', '/api/missile_range/simulate', json.dumps(payload).encode(),
    )
    assert status == 200
    data = json.loads(body.decode())
    assert data['success'] is True

    cases = data['cases']
    stealth_cases = [c for c in cases if c['bay'] == '隐身超音速轰炸机弹仓']
    assert len(stealth_cases) == 10  # 5 个超音速弹种 × 2 种战斗部 (150kg, 500kg)

    for sc in stealth_cases:
        # 对应同尺寸、同弹种、同战斗部的轰-6机腹版本
        matched_h6 = [
            c for c in cases
            if c['bay'] == '轰-6机腹'
            and c['missile_class'] == sc['missile_class']
            and float(c['length_m']) == float(sc['length_m']) == 11.30
            and float(c['diameter_m']) == float(sc['diameter_m']) == 0.860
            and int(c['warhead_kg']) == int(sc['warhead_kg'])
        ]
        assert len(matched_h6) == 1
        hc = matched_h6[0]

        # 发射条件：轰-6机腹为 Ma 0.85 @ 13.0km，隐轰为 Ma 1.75 @ 18.0km
        assert hc['v_mach'] == 0.85
        assert hc['h_km'] == 13.0
        assert sc['v_mach'] == 1.75
        assert sc['h_km'] == 18.0

        # 端到端 API 计算射程
        est_payload_h6 = {
            'action': 'estimate',
            'params': {
                'missile_class': hc['missile_class'],
                'length_m': hc['length_m'],
                'diameter_m': hc['diameter_m'],
                'warhead_kg': hc['warhead_kg'],
                'v_launch_mach': hc['v_mach'],
                'h_launch_km': hc['h_km'],
            },
        }
        status_h, _, body_h = handle_request(
            'POST', '/api/missile_range/simulate', json.dumps(est_payload_h6).encode(),
        )
        assert status_h == 200
        res_h = json.loads(body_h.decode())['result']

        est_payload_sc = {
            'action': 'estimate',
            'params': {
                'missile_class': sc['missile_class'],
                'length_m': sc['length_m'],
                'diameter_m': sc['diameter_m'],
                'warhead_kg': sc['warhead_kg'],
                'v_launch_mach': sc['v_mach'],
                'h_launch_km': sc['h_km'],
            },
        }
        status_s, _, body_s = handle_request(
            'POST', '/api/missile_range/simulate', json.dumps(est_payload_sc).encode(),
        )
        assert status_s == 200
        res_s = json.loads(body_s.decode())['result']

        assert res_h['range_km'] > 0
        assert res_s['range_km'] > res_h['range_km']


@pytest.mark.e2e
def test_e2e_missile_range_hgv_geometry_optimization():
    """助推滑翔弹滑翔体几何长宽寻优端到端接口测试。"""
    # 1. 测试 action='optimize_geometry' 接口
    payload = {
        'action': 'optimize_geometry',
        'params': {
            'length_m': 10.5,
            'diameter_m': 1.0,
            'warhead_kg': 200,
            'missile_class': 'hgv_biconic',
            'v_launch_mach': 0.85,
            'h_launch_km': 13.0,
        },
    }
    status, _, body = handle_request(
        'POST', '/api/missile_range/simulate', json.dumps(payload).encode(),
    )
    assert status == 200
    data = json.loads(body.decode())
    assert data['success'] is True
    opt = data['optimization']
    assert opt['range_gain_km'] > 500.0
    assert opt['best_l_head_m'] > opt['baseline_l_head_m']
    assert opt['best_d_head_m'] <= 1.0
    assert opt['best_ld_ratio'] > opt['baseline_ld_ratio']
    assert opt['best_fineness'] >= 2.5

    # 常规 estimate 不传开关时，助推滑翔默认寻优
    default_payload = {
        'action': 'estimate',
        'params': {
            'length_m': 10.5,
            'diameter_m': 1.0,
            'warhead_kg': 200,
            'missile_class': 'hgv_biconic',
            'v_launch_mach': 0.85,
            'h_launch_km': 13.0,
        },
    }
    def_status, _, def_body = handle_request(
        'POST', '/api/missile_range/simulate', json.dumps(default_payload).encode(),
    )
    assert def_status == 200
    def_data = json.loads(def_body.decode())
    assert def_data['success'] is True
    assert def_data['result']['optimal_geometry'] is True
    assert def_data['result']['d_head_m'] <= 1.0
    assert '几何搜索寻优' in def_data['result']['note']

    # 测试通过常规 estimate 接口显式开启 optimize_geometry 寻优
    est_payload = {
        'action': 'estimate',
        'params': {
            'length_m': 10.5,
            'diameter_m': 1.0,
            'warhead_kg': 200,
            'missile_class': 'hgv_biconic',
            'v_launch_mach': 0.85,
            'h_launch_km': 13.0,
            'optimize_geometry': True,
        },
    }
    est_status, _, est_body = handle_request(
        'POST', '/api/missile_range/simulate', json.dumps(est_payload).encode(),
    )
    assert est_status == 200
    est_data = json.loads(est_body.decode())
    assert est_data['success'] is True
    res = est_data['result']
    assert res['optimal_geometry'] is True
    assert res['range_gain_km'] > 500.0
    assert '几何搜索寻优' in res['note']
    assert res['d_head_m'] <= 1.0


@pytest.mark.e2e
def test_e2e_missile_range_takeover_gui_and_api():
    """端到端验证：未达工作速度在 API 返回及三端 GUI 文件中均有对应展示。"""
    # 1. 验证 API 返回未达工作速度情况
    payload_fail = {
        'action': 'estimate',
        'params': {
            'missile_class': 'scramjet',
            'length_m': 6.35,
            'diameter_m': 0.51,
            'warhead_kg': 160.0,
            'v_launch_mach': 0.0,
            'h_launch_km': 0.0,
        },
    }
    status, _, body = handle_request(
        'POST', '/api/missile_range/simulate', json.dumps(payload_fail).encode(),
    )
    assert status == 200
    res = json.loads(body.decode())['result']
    assert res['reached_takeover'] is False
    assert res['mach_takeover'] == 4.2
    assert res['mach_boost'] < 4.2 * 0.98
    assert res['range_cruise_km'] == 0.0

    # 2. 验证 API 返回达到工作速度情况
    payload_ok = {
        'action': 'estimate',
        'params': {
            'missile_class': 'scramjet',
            'length_m': 10.0,
            'diameter_m': 1.05,
            'warhead_kg': 400.0,
            'v_launch_mach': 0.0,
            'h_launch_km': 0.0,
        },
    }
    status_ok, _, body_ok = handle_request(
        'POST', '/api/missile_range/simulate', json.dumps(payload_ok).encode(),
    )
    assert status_ok == 200
    res_ok = json.loads(body_ok.decode())['result']
    assert res_ok['reached_takeover'] is True
    assert res_ok['mach_takeover'] == 4.2
    assert res_ok['mach_boost'] >= 4.2 * 0.98

    # 3. 验证三端 GUI 代码中对未达工作速度的展示支持
    html = (ROOT / 'docs' / 'missile-range.html').read_text(encoding='utf-8')
    js = (ROOT / 'docs' / 'js' / 'missile_range.js').read_text(encoding='utf-8')
    css = (ROOT / 'docs' / 'css' / 'missile_range.css').read_text(encoding='utf-8')
    wxml = (ROOT / 'miniprogram' / 'pages' / 'missile_range' / 'missile_range.wxml').read_text(encoding='utf-8')
    mini_js = (ROOT / 'miniprogram' / 'pages' / 'missile_range' / 'missile_range.js').read_text(encoding='utf-8')
    swift = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileRangeView.swift').read_text(encoding='utf-8')
    vm_swift = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileRangeViewModel.swift').read_text(encoding='utf-8')

    assert 'takeover-alert' in js
    assert '未达工作速度' in js
    assert 'takeoverMeterHtml' in js
    assert 'failOnly' in js
    assert '只看未达工作速度' in html
    assert 'takeover-alert' in css
    assert 'takeover-meter' in css
    assert 'fail-takeover' in css
    assert 'takeover-alert' in wxml
    assert '未达工作速度' in wxml
    assert 'takeover-meter' in wxml
    assert 'failOnly' in mini_js
    assert '未达工作速度' in swift
    assert '只看未达工作速度' in swift
    assert 'setFailOnly' in vm_swift
    assert res['takeover_progress'] < 1.0
    assert res_ok['takeover_progress'] == pytest.approx(1.0)


@pytest.mark.e2e
def test_e2e_h6_belly_max_is_separate_from_shared_bay():
    """轰-6机腹沿用隐轰尺寸；轰-6机腹最大单独成组，且不超过 12 m、10 t。"""
    payload = {'action': 'presets'}
    status, _, body = handle_request(
        'POST', '/api/missile_range/simulate', json.dumps(payload).encode(),
    )
    assert status == 200
    cases = json.loads(body.decode())['cases']
    h6 = [case for case in cases if case['bay'] == '轰-6机腹']
    largest = [case for case in cases if case['bay'] == '轰-6机腹最大']
    assert h6 and largest
    assert all(case['length_m'] == pytest.approx(11.3) and case['diameter_m'] == pytest.approx(0.86) for case in h6)
    assert {int(case['warhead_kg']) for case in h6} == {150, 500}
    bays = [case['bay'] for case in cases]
    assert bays.index('轰-6机腹最大') < bays.index('轰-6机腹')
    # 两段各自连续，不把两种机腹穿插在一起
    assert '轰-6机腹' not in bays[bays.index('轰-6机腹最大'):bays.index('轰-6机腹')]
    sizes = {(case['length_m'], case['diameter_m'], int(case['warhead_kg'])) for case in largest}
    assert len({(case['missile_class']) for case in largest}) == 5
    assert len({(length, diameter) for length, diameter, _warhead in sizes}) > 1
    for case in largest:
        assert case['length_m'] <= 12.0
        assert case['m_0_t'] <= 10.0
        assert case['v_mach'] == pytest.approx(0.85)
        assert case['h_km'] == pytest.approx(13.0)
    sample = largest[0]
    estimate = {
        'action': 'estimate',
        'params': {
            'missile_class': sample['missile_class'],
            'length_m': sample['length_m'],
            'diameter_m': sample['diameter_m'],
            'warhead_kg': sample['warhead_kg'],
            'v_launch_mach': sample['v_mach'],
            'h_launch_km': sample['h_km'],
        },
    }
    status_e, _, body_e = handle_request(
        'POST', '/api/missile_range/simulate', json.dumps(estimate).encode(),
    )
    assert status_e == 200
    result = json.loads(body_e.decode())['result']
    assert result['range_km'] == sample['range_km']
    assert result['m_0_t'] <= 10.0


