"""作战半径仿真核心与 Web API 单元测试。"""
from __future__ import annotations

import json

from apps.combat_radius_web import _opt_bool, _opt_float, run_combat_radius, run_combat_radius_json
from simulators.combat_radius.combat_radius import (
    format_ld_row,
    parse_sea_level_thrust_n,
    run_estimate_efficiency_from_params,
    run_estimate_thrust_from_params,
    run_predict_ld,
    run_predict_ld_from_params,
    _optional_float,
    _optional_int,
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
    assert any(p['id'] == 'f119' for p in presets['engine_presets'])
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
    assert any(p['id'] == 'f119' for p in parsed['engine_presets'])


def test_optional_float_empty_and_numeric():
    assert _optional_float(None) is None
    assert _optional_float('') is None
    assert _optional_float(1.5) == 1.5
    assert _optional_float('2') == 2.0


def test_parse_sea_level_thrust_n_from_n_or_kn():
    assert parse_sea_level_thrust_n({'tsl_N': 116000}) == 116000.0
    assert parse_sea_level_thrust_n({'tsl_kN': 116}) == 116000.0
    assert parse_sea_level_thrust_n({'tsl_N': 5000, 'tsl_kN': 116}) == 5000.0
    with pytest.raises(ValueError, match='海平面军推'):
        parse_sea_level_thrust_n({})


def _f119_thrust_params() -> dict:
    return {
        'name': 'F119',
        'bpr': 0.30,
        'opr': 26.0,
        't4_K': 1922,
        'tsl_kN': 116.0,
        'alt_m': 11000,
        'mach': 1.5,
    }


def test_run_estimate_thrust_from_params_f119():
    r = run_estimate_thrust_from_params(_f119_thrust_params())
    assert r['success'] is True
    assert r['name'] == 'F119'
    assert r['thrust_kN'] == pytest.approx(r['thrust_N'] / 1000.0)
    assert 10.0 < r['thrust_kN'] < 116.0
    alias = run_estimate_thrust_from_params({
        'bpr': 0.30, 'opr': 26.0, 't4': 1922, 'tsl_N': 116000,
        'alt_m': 11000, 'mach': 1.5,
    })
    assert alias['success'] is True
    assert alias['thrust_N'] == pytest.approx(r['thrust_N'])


def test_run_combat_radius_estimate_thrust_and_cycle_error():
    ok = run_combat_radius('estimate_thrust', _f119_thrust_params())
    assert ok['success'] is True
    assert ok['alpha'] < 1.0
    bad = run_combat_radius_json({
        'action': 'estimate_thrust',
        'params': {'bpr': 2.0, 'opr': 40.0, 't4_K': 900, 'tsl_kN': 100, 'alt_m': 0, 'mach': 0},
    })
    assert bad['success'] is False
    assert '无解' in bad['error']


def test_optional_int_default_and_cast():
    assert _optional_int(None, 2) == 2
    assert _optional_int('', 3) == 3
    assert _optional_int('4', 1) == 4
    assert _optional_int(2.0, 1) == 2


def test_run_estimate_efficiency_from_params_f22():
    p = _sample_params()
    r = run_estimate_efficiency_from_params({
        **p,
        'target': p['anchor2'],
        'empty_kg': 19700,
        'internal_fuel_kg': 8200,
        'n_pilots': 1,
        'missile_mass_kg': 152,
        'n_missiles': 4,
        'n_engines': 2,
        'bpr': 0.30,
        'opr': 26.0,
        't4_K': 1922,
        'tsl_kN': 116.0,
        'alt_m': 11800,
        'mach': 0.8,
    })
    assert r['success'] is True
    assert r['ld'] == pytest.approx(8.0, abs=1e-6)
    assert r['n_engines'] == 2
    assert 0 < r['load'] <= 1
    assert r['eta_o'] > 0
    assert r['tsfc_mg_n_s'] > 0
    assert r['drag_kN'] < r['thrust_avail_kN']


def test_run_estimate_efficiency_ld_override_and_overload():
    r = run_estimate_efficiency_from_params({
        'ld': 2.0,
        'empty_kg': 19700,
        'internal_fuel_kg': 8200,
        'n_pilots': 1,
        'missile_mass_kg': 152,
        'n_engines': 1,
        'bpr': 0.30,
        'opr': 26.0,
        't4_K': 1922,
        'tsl_kN': 116.0,
        'alt_m': 11800,
        'mach': 0.8,
    })
    assert r['success'] is True
    assert r['ld'] == pytest.approx(2.0)
    assert r['load_raw'] > 1.0
    assert r['load'] == pytest.approx(1.0)
    assert 'load_exceeds_thrust' in (r['warning'] or '')


def test_run_combat_radius_estimate_efficiency_action():
    p = _sample_params()
    ok = run_combat_radius('estimate_efficiency', {
        **p,
        'target': p['anchor2'],
        'empty_kg': 19700, 'internal_fuel_kg': 8200, 'n_engines': 2,
        'bpr': 0.30, 'opr': 26.0, 't4_K': 1922, 'tsl_kN': 116.0,
        'alt_m': 11800, 'mach': 0.8,
    })
    assert ok['success'] is True
    bad = run_combat_radius_json({'action': 'estimate_efficiency', 'params': {}})
    assert bad['success'] is False


def test_run_estimate_efficiency_rejects_zero_engines():
    with pytest.raises(ValueError, match='发动机台数'):
        run_estimate_efficiency_from_params({
            'ld': 8.0, 'empty_kg': 10000, 'internal_fuel_kg': 4000,
            'n_engines': 0, 'bpr': 0.3, 'opr': 26, 't4_K': 1922, 'tsl_kN': 116,
            'alt_m': 10000, 'mach': 0.8,
        })


