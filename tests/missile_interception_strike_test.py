"""饱和打击仿真核心单元测试。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from simulators.missile_interception.missile_interception_strike import (
    MACH_MPS,
    run_estimate_distance_from_params,
    run_estimate_pk_from_params,
    run_missile_interception_strike,
)

_ROOT = Path(__file__).resolve().parent.parent



def test_mach_constant():
    """声速常量与 HTML 一致。"""
    assert MACH_MPS == 340.0


def test_run_missile_interception_strike_fast():
    """快速模式返回完整结构。"""
    r = run_missile_interception_strike(
        nm=24, vm_ma=2.6, discovery_km=120, ni=16, vi_ma=3.8,
        pk=0.7, t_lock_s=6, min_range_km=3,
        search_trials=100, final_trials=200,
    )
    assert r['success'] is True
    assert r['n_rounds'] >= 1
    assert 'expected_leak' in r
    assert 'best' in r
    assert 'windows' in r
    assert len(r['avg_survivors']) == r['n_rounds'] + 1
    assert r['plan_rows']
    assert all(row['kill_prob'] > 0 for row in r['plan_rows'])
    assert r['all_candidates']
    assert any(c.get('relative_label') == '最优' for c in r['all_candidates'])


def test_run_missile_interception_strike_no_windows():
    """无法形成窗口时突防等于来袭数。"""
    r = run_missile_interception_strike(
        nm=10, vm_ma=3, discovery_km=5, ni=16, vi_ma=3,
        pk=0.7, t_lock_s=10, min_range_km=3,
        search_trials=50, final_trials=50,
    )
    assert r['n_rounds'] == 0
    assert r['expected_leak'] == 10
    assert r['intercept_rate'] == 0


def test_run_estimate_distance_from_params():
    """距离估算含 binding 标签（默认有预警机）。"""
    r = run_estimate_distance_from_params({
        'rcs': 0.5, 'traj': 'high', 'awacs_area': 8, 'awacs_type': 'aesa',
        'standoff': 150, 'ship_area': 12, 'ship_type': 'aesa', 'sam_range': 40,
    })
    assert r['engage_dist'] == 40
    assert r['binding'] == '拦截弹射程'
    assert r['has_awacs'] is True


def test_run_estimate_distance_from_params_no_awacs():
    """params 传 has_awacs=False（各种可解析形式）时不使用预警机总探测。"""
    for raw in (False, 0, '0', 'false', 'no'):
        r = run_estimate_distance_from_params({
            'rcs': 0.5, 'traj': 'sea', 'awacs_area': 8, 'awacs_type': 'aesa',
            'standoff': 150, 'ship_area': 12, 'ship_type': 'aesa', 'sam_range': 200,
            'has_awacs': raw,
        })
        assert r['has_awacs'] is False, raw
        assert r['engage_dist'] == min(r['ship_search'], r['sam_range'])
        assert r['awacs_detect_km'] == 0.0
        assert r['binding'] != '预警机雷达探测距离'


def test_run_estimate_distance_from_params_awacs_type_none_implies_no_awacs():
    """未显式传 has_awacs 但 awacs_type 为 'none' 时视为无预警机。"""
    r = run_estimate_distance_from_params({
        'rcs': 0.5, 'traj': 'high', 'awacs_area': 8, 'awacs_type': 'none',
        'standoff': 150, 'ship_area': 12, 'ship_type': 'aesa', 'sam_range': 200,
    })
    assert r['has_awacs'] is False
    assert r['engage_dist'] == min(r['ship_search'], r['sam_range'])


def test_run_estimate_pk_from_params():
    """Pk 估算返回因子分解（无抗干扰系数）。"""
    r = run_estimate_pk_from_params({
        'vm': 2.6, 'vi': 3.8, 'rcs': 0.5, 'traj': 'high',
        'ship_area': 12, 'ship_type': 'aesa', 'interceptor_dia': 0.35,
        'seeker_type': 'active_aesa',
    })
    assert 0.03 <= r['pk'] <= 0.97
    assert 'ecm_factor' not in r


def test_missile_interception_strike_script_runs_as_file():
    """直接执行 simulators/missile_interception/missile_interception_strike.py 不应因缺 utils 而失败。"""
    script = _ROOT / 'simulators' / 'missile_interception' / 'missile_interception_strike.py'
    proc = subprocess.run(
        [sys.executable, str(script), '--fast', '--nm', '8', '--ni', '6'],
        cwd=str(_ROOT / 'simulators' / 'missile_interception'),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert '拦截窗口数' in proc.stdout
