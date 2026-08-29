"""饱和打击端到端测试：全链路仿真与估算。"""
from __future__ import annotations

import json

import pytest

from apps.miniprogram_api import handle_request
from apps.missile_interception_strike_web import run_missile_interception_json
from simulators.missile_interception.missile_interception_strike import run_missile_interception_strike
from utils.missile_interception.missile_interception_presets import (
    build_missile_interception_presets_payload,
    filter_presets_by_nation,
    nations_union,
)


@pytest.mark.e2e
def test_e2e_missile_interception_default_params():
    """默认参数全链路：窗口、最优方案、期望突防与策略表。"""
    result = run_missile_interception_strike(
        nm=24, vm_ma=2.6, discovery_km=120, ni=16, vi_ma=3.8,
        pk=0.7, t_lock_s=6, min_range_km=3,
    )
    assert result['success'] is True
    assert result['n_rounds'] == 4
    assert result['windows'][0]['dist_start_km'] == pytest.approx(120.0)
    assert result['best']['plan']
    assert sum(result['best']['plan']) == 16
    assert 0 < result['expected_leak'] < 24
    assert len(result['all_candidates']) >= 4
    assert result['plan_rows']
    assert result['plan_rows'][0]['kill_prob'] > 0
    assert any(c.get('relative_label') == '最优' for c in result['all_candidates'])
    assert result['final_trials'] == 6000
    assert '期望突防' in result['note'] or '突防' in result['note']


@pytest.mark.e2e
def test_e2e_missile_interception_zero_windows():
    """边界：无窗口时突防等于来袭。"""
    result = run_missile_interception_json({
        'action': 'simulate',
        'params': {
            'nm': 8, 'vm': 3, 'D': 4, 'ni': 10, 'vi': 3,
            'pk': 0.7, 'tlock': 8, 'minr': 3, 'fast': True,
        },
    })
    assert result['success'] is True
    assert result['n_rounds'] == 0
    assert result['expected_leak'] == 8


@pytest.mark.e2e
def test_e2e_missile_interception_estimate_paths():
    """合并估算按钮依赖的交战距离 + 拦截率（Pk）路径均可用。"""
    params = {
        'rcs': 0.5, 'traj': 'high', 'awacs_area': 8, 'awacs_type': 'aesa',
        'standoff': 150, 'ship_area': 12, 'ship_type': 'aesa', 'sam_range': 40,
        'vm': 2.6, 'vi': 3.8, 'interceptor_dia': 0.35,
        'seeker_type': 'active_aesa',
    }
    # 与三端 onEstimateDistanceAndPk / estimateDistanceAndPk 调用顺序一致
    dist = run_missile_interception_json({'action': 'estimate_distance', 'params': params})
    assert dist['success'] is True
    assert dist['engage_dist'] == pytest.approx(40.0)
    assert dist['engage_dist'] == pytest.approx(
        min(max(dist['awacs_total'], dist['ship_search']), dist['sam_range'])
    )
    assert dist['binding']

    pk = run_missile_interception_json({'action': 'estimate_pk', 'params': params})
    assert pk['success'] is True
    assert 0.03 <= pk['pk'] <= 0.97
    assert 'ecm_factor' not in pk
    # 遗留抗干扰档数不得影响拦截率估算
    pk_hi = run_missile_interception_json({
        'action': 'estimate_pk',
        'params': {**params, 'ecm': 5},
    })
    assert pk_hi['pk'] == pk['pk']


@pytest.mark.e2e
def test_e2e_missile_interception_estimate_distance_no_awacs():
    """无预警机（has_awacs=False）交战距离估算全链路可用。"""
    params = {
        'rcs': 0.5, 'traj': 'sea', 'awacs_area': 8, 'awacs_type': 'aesa',
        'standoff': 150, 'ship_area': 12, 'ship_type': 'aesa', 'sam_range': 200,
        'vm': 2.6, 'vi': 3.8, 'interceptor_dia': 0.35,
        'seeker_type': 'active_aesa', 'has_awacs': False,
    }
    dist = run_missile_interception_json({'action': 'estimate_distance', 'params': params})
    assert dist['success'] is True
    assert dist['has_awacs'] is False
    assert dist['awacs_detect_km'] == 0.0
    assert dist['engage_dist'] == pytest.approx(min(dist['ship_search'], dist['sam_range']))
    assert dist['binding'] != '预警机雷达探测距离'


@pytest.mark.e2e
def test_e2e_missile_interception_http_api():
    """小程序 HTTP API 饱和打击路由。"""
    payload = {
        'action': 'simulate',
        'params': {
            'nm': 24, 'vm': 2.6, 'D': 120, 'ni': 16, 'vi': 3.8,
            'pk': 0.7, 'tlock': 6, 'minr': 3, 'fast': True,
        },
    }
    status, headers, body = handle_request(
        'POST', '/api/missile_interception/simulate', json.dumps(payload).encode(),
    )
    assert status == 200
    assert 'application/json' in headers['Content-Type']
    result = json.loads(body.decode())
    assert result['success'] is True
    assert result['n_rounds'] >= 1
    assert 'best' in result


@pytest.mark.e2e
def test_e2e_defender_nation_filters_ship_and_sam_models():
    """防御方国别同时约束驱护舰艇与防空导弹型号（三端共用选择器的数据契约）。"""
    payload = build_missile_interception_presets_payload()
    union = nations_union(payload['ship'], payload['sam'])
    assert '中国' in union
    ships = filter_presets_by_nation(payload['ship'], '中国')
    sams = filter_presets_by_nation(payload['sam'], '中国')
    assert ships and all(x['nation'] == '中国' for x in ships)
    assert sams and all(x['nation'] == '中国' for x in sams)
    # 选仅存在于一侧的国别时，另一侧型号列表可为空，但不得串国别
    only_ship = [n for n in nations_union(payload['ship']) if n not in nations_union(payload['sam'])]
    if only_ship:
        assert filter_presets_by_nation(payload['sam'], only_ship[0]) == []
