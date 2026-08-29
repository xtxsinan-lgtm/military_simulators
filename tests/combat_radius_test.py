"""作战半径仿真核心与 Web API 单元测试。"""
from __future__ import annotations

import json

from apps.combat_radius_web import _opt_bool, _opt_float, run_combat_radius, run_combat_radius_json
from simulators.combat_radius.combat_radius import (
    format_ld_row,
    run_predict_ld,
    run_predict_ld_from_params,
    _require_aircraft_params,
)
from utils.combat_radius.lift_drag import Aircraft
import pytest


def _sample_params() -> dict:
    return {
        'anchor1': {
            'name': 'F-35C', 'AR': 2.77, 'sweep_deg': 30.9, 'wing_loading': 0.341,
            'tc': 0.051, 'mach': 0.8, 'alt_m': 11300,
            'planform': 'trapezoidal', 'layout': 'conventional', 'bwb': False, 'rough': True,
        },
        'ld1_target': 8.8,
        'anchor2': {
            'name': 'F-22', 'AR': 2.37, 'sweep_deg': 41.3, 'wing_loading': 0.318,
            'tc': 0.052, 'mach': 0.8, 'alt_m': 11800,
            'planform': 'trapezoidal', 'layout': 'conventional', 'bwb': False, 'rough': False,
        },
        'ld2_target': 8.0,
        'target': {
            'name': 'J-20', 'AR': 2.32, 'sweep_deg': 46.3, 'wing_loading': 0.329,
            'tc': 0.043, 'mach': 0.8, 'alt_m': 12000,
            'planform': 'delta', 'layout': 'canard', 'bwb': False, 'rough': False,
        },
    }


def test_opt_float_and_opt_bool():
    assert _opt_float('', 1.5) == 1.5
    assert _opt_float('2.5', 0) == 2.5
    assert _opt_bool('', False) is False
    assert _opt_bool('是', False) is True
    assert _opt_bool('否', True) is False
    assert _opt_bool(2, False) is True
    assert _opt_bool('maybe', True) is True


def test_require_aircraft_params():
    d = _require_aircraft_params({'anchor1': {'AR': 1}}, 'anchor1')
    assert d['AR'] == 1
    with pytest.raises(ValueError, match='缺少机型参数'):
        _require_aircraft_params({}, 'anchor1')


def test_format_ld_row_with_and_without_target():
    ac = Aircraft(
        'F-22', AR=2.37, sweep_deg=41.3, wing_loading=0.318,
        tc=0.052, mach=0.8, alt_m=11800,
        planform='trapezoidal', layout='conventional', bwb=False, rough=False,
    )
    params = _sample_params()
    r = run_predict_ld_from_params(params)
    row = format_ld_row(ac, r['Cf0'], r['k_e'], 8.0)
    assert row['target_ld'] == 8.0
    assert abs(row['error']) < 1e-9
    bare = format_ld_row(ac, r['Cf0'], r['k_e'])
    assert 'target_ld' not in bare


def test_run_predict_ld_success_structure():
    p = _sample_params()
    a1 = Aircraft(**{k: p['anchor1'][k] for k in p['anchor1']})
    a2 = Aircraft(**{k: p['anchor2'][k] for k in p['anchor2']})
    tgt = Aircraft(**{k: p['target'][k] for k in p['target']})
    r = run_predict_ld(a1, 8.8, a2, 8.0, tgt)
    assert r['success'] is True
    assert len(r['anchors']) == 2
    assert r['target']['name'] == 'J-20'
    assert 7.0 < r['target']['ld'] < 10.0


def test_run_predict_ld_from_params():
    r = run_predict_ld_from_params(_sample_params())
    assert r['success'] is True
    assert r['anchors'][0]['ld'] == pytest.approx(8.8, abs=1e-8)


def test_run_combat_radius_presets_and_unknown_action():
    presets = run_combat_radius('presets')
    assert presets['success'] is True
    assert any(p['id'] == 'J-20' for p in presets['presets'])
    bad = run_combat_radius('nope')
    assert bad['success'] is False
    assert '未知 action' in bad['error']


def test_run_combat_radius_json_predict_and_errors():
    r = run_combat_radius_json({'action': 'predict_ld', 'params': _sample_params()})
    assert r['success'] is True
    flat = run_combat_radius_json({**_sample_params(), 'action': 'predict_ld'})
    assert flat['success'] is True
    assert run_combat_radius_json('not-json')['success'] is False
    assert run_combat_radius_json([1, 2])['success'] is False
    failed = run_combat_radius_json({'action': 'predict_ld', 'params': {}})
    assert failed['success'] is False
    parsed = run_combat_radius_json(json.dumps({'action': 'presets'}))
    assert parsed['success'] is True
