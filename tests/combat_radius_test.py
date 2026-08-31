"""作战半径仿真核心与 Web API 单元测试。"""
from __future__ import annotations

import json

from apps.combat_radius_web import _opt_bool, _opt_float, run_combat_radius, run_combat_radius_json
from simulators.combat_radius.combat_radius import (
    FLOOR_MAX_CRUISE_ID,
    FLOOR_MAX_CRUISE_LABEL,
    PRACTICAL_MAX_CRUISE_ID,
    PRACTICAL_MAX_CRUISE_LABEL,
    compact_max_speed,
    cruise_limit_specs,
    format_cruise_speed_label,
    ensure_default_anchors,
    format_ld_row,
    main,
    parse_sea_level_thrust_n,
    resolve_tsl_kN,
    run_aircraft_dashboard_from_params,
    run_estimate_efficiency_from_params,
    run_estimate_engine_cycle_from_params,
    run_estimate_radius_from_params,
    run_estimate_thrust_from_params,
    run_predict_ld,
    run_predict_ld_from_params,
    run_search_best_cruise_from_params,
    _as_bool,
    _attach_max_ld_to_point,
    _attach_mixed_radius,
    _calibrate_from_params,
    _clear_mixed_radius_fields,
    _cruise_context_from_params,
    _enrich_radius_point,
    _failed_radius_point,
    _infeasible_point,
    _mission_fuel_note,
    _optional_ab_context,
    _optional_float,
    _optional_int,
    _parse_carrier,
    _positive_thrust_value,
    _radius_fail_reason,
    _require_aircraft_params,
    _subsonic_scored_for_burn,
)
from utils.combat_radius.lift_drag import Aircraft
from utils.combat_radius.max_speed_search import MAX_SPEED_THRUST_MARGIN
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
            'planform': 'trapezoidal', 'layout': 'canard', 'bwb': False, 'rough': False,
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
    assert row['error'] == pytest.approx(row['ld'] - 8.0)
    assert 'CDa' in row
    bare = format_ld_row(ac, r['Cf0'], r['k_e'])
    assert 'target_ld' not in bare


def test_run_predict_ld_success_structure():
    p = _sample_params()
    tgt = Aircraft(**{k: p['target'][k] for k in p['target']})
    r = run_predict_ld(tgt)
    assert r['success'] is True
    assert r['anchors'] == []
    assert r['target']['name'] == 'J-20'
    assert 7.0 < r['target']['ld'] < 12.0


def test_run_predict_ld_from_params():
    r = run_predict_ld_from_params(_sample_params())
    assert r['success'] is True
    assert r['Cf0'] > 0
    assert r['target']['ld'] > 0


def test_run_combat_radius_presets_and_unknown_action():
    presets = run_combat_radius('presets')
    assert presets['success'] is True
    assert any(p['id'] == 'J-20' for p in presets['presets'])
    assert any(p['id'] == 'J-15' for p in presets['presets'])
    assert any(p['id'] == 'F-35B' for p in presets['presets'])
    assert any(p['id'] == '53636' for p in presets['presets'])
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


def test_positive_thrust_value_rejects_zero_and_nan():
    assert _positive_thrust_value(None) is None
    assert _positive_thrust_value('') is None
    assert _positive_thrust_value(0) is None
    assert _positive_thrust_value(-10) is None
    assert _positive_thrust_value(float('nan')) is None
    assert _positive_thrust_value(120) == 120.0


def test_parse_sea_level_thrust_n_from_n_or_kn():
    assert parse_sea_level_thrust_n({'tsl_N': 116000}) == 116000.0
    assert parse_sea_level_thrust_n({'tsl_kN': 116}) == 116000.0
    assert parse_sea_level_thrust_n({'tsl_N': 5000, 'tsl_kN': 116}) == 5000.0
    with pytest.raises(ValueError, match='海平面军推'):
        parse_sea_level_thrust_n({})


def test_parse_sea_level_thrust_n_zero_uses_max_tsl():
    """选机后前端常把空军推当成 0 传来，须改用发动机加力按比例估计军推。"""
    from utils.combat_radius.combat_radius_config import dry_to_max_thrust_ratio

    n = parse_sea_level_thrust_n({'tsl_kN': 0, 'max_tsl_kN': 185})
    assert n == pytest.approx(185.0 * dry_to_max_thrust_ratio() * 1000.0)
    assert resolve_tsl_kN({'tsl_kN': 0, 'max_tsl_kN': 185}) == pytest.approx(
        185.0 * dry_to_max_thrust_ratio()
    )
    with pytest.raises(ValueError, match='海平面军推'):
        parse_sea_level_thrust_n({'tsl_kN': 0})


def test_resolve_tsl_kn_prefers_explicit_military_thrust():
    assert resolve_tsl_kN({'tsl_kN': 120, 'max_tsl_kN': 156}) == 120.0
    assert resolve_tsl_kN({}) is None


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
        'empty_kg': 19800,
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
    assert 9.0 < r['ld'] < 12.0
    assert r['n_engines'] == 2
    assert 0 < r['load'] <= 1
    assert r['eta_o'] > 0
    assert r['tsfc_mg_n_s'] > 0
    assert r['drag_kN'] < r['thrust_avail_kN']


def test_run_estimate_efficiency_ld_override_and_overload():
    r = run_estimate_efficiency_from_params({
        'ld': 2.0,
        'empty_kg': 19800,
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
        'empty_kg': 19800, 'internal_fuel_kg': 8200, 'n_engines': 2,
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


def _radius_params() -> dict:
    p = _sample_params()
    p['target'] = {
        **p['anchor2'],
        'mach_angle_deg': 28.5,
        'wingspan_m': 13.59,
    }
    p.update({
        'empty_kg': 19800,
        'internal_fuel_kg': 8200,
        'n_pilots': 1,
        'missile_mass_kg': 152,
        'n_missiles': 4,
        'n_engines': 2,
        'bpr': 0.30,
        'opr': 26.0,
        't4_K': 1922,
        'tsl_kN': 116.0,
        'alt_coarse_m': 3000,
        'alt_refine_m': 1500,
        'mach_search_iters': 4,
        'mach_search_lo': 0.5,
        'mach_search_hi': 1.8,
    })
    return p


def test_calibrate_from_params_returns_target_and_cf0():
    tgt, cf0, k_e = _calibrate_from_params(_sample_params())
    assert tgt.name == 'J-20'
    assert cf0 > 0 and k_e > 0


def test_cruise_limit_specs_order_and_labels():
    """表尾两行须先实用最大巡航、再最大巡航，标签固定。"""
    rows = cruise_limit_specs(1.76, 1.92)
    assert rows == [
        (PRACTICAL_MAX_CRUISE_ID, PRACTICAL_MAX_CRUISE_LABEL, 1.76),
        (FLOOR_MAX_CRUISE_ID, FLOOR_MAX_CRUISE_LABEL, 1.92),
    ]
    empty = cruise_limit_specs(None, None)
    assert empty[0][2] is None and empty[1][2] is None


def test_format_cruise_speed_label_fixed_and_limits():
    """固定马赫只显示数字；表尾两行须带中文名称。"""
    assert format_cruise_speed_label({'id': 'mach_0_8', 'label': 'Ma 0.8', 'mach': 0.8}) == '0.800'
    assert format_cruise_speed_label({
        'id': PRACTICAL_MAX_CRUISE_ID,
        'label': PRACTICAL_MAX_CRUISE_LABEL,
        'mach': 1.76,
    }) == '实用最大巡航速度 1.760'
    assert format_cruise_speed_label({
        'id': FLOOR_MAX_CRUISE_ID,
        'label': FLOOR_MAX_CRUISE_LABEL,
        'mach': 1.92,
    }) == '最大巡航速度 1.920'
    assert format_cruise_speed_label({
        'id': PRACTICAL_MAX_CRUISE_ID,
        'label': PRACTICAL_MAX_CRUISE_LABEL,
        'mach': None,
    }) == PRACTICAL_MAX_CRUISE_LABEL
    assert format_cruise_speed_label({}) == '—'


def test_infeasible_point_shape():
    row = _infeasible_point('mach_1_75', 'Ma 1.75', 1.75)
    assert row['feasible'] is False
    assert row['radius_km'] is None
    assert row['warning'] == 'no_feasible_altitude'
    assert row['fail_reason'] == '无满足 92% 推力裕度的高度'
    none_mach = _infeasible_point(PRACTICAL_MAX_CRUISE_ID, PRACTICAL_MAX_CRUISE_LABEL, None)
    assert none_mach['mach'] is None


def test_enrich_radius_point_and_missing_tsfc():
    from utils.combat_radius.breguet import combat_radius_m
    from utils.combat_radius.cruise_search import CruiseScored

    scored = CruiseScored(
        mach=0.8, alt_m=12000, ld=8.0, drag_N=30000, thrust_avail_N=60000,
        load_raw=0.5, feasible=True, cd_breakdown={'CL': 0.3},
        load=0.5, eta_o=0.18, v0=240.0, tsfc_kg_n_s=3e-5,
        tsfc_mg_n_s=30.0, tsfc_lb_lbf_h=1.1, score=1.44,
    )
    row = _enrich_radius_point('mach_0_8', 'Ma 0.8', scored, 28000, 20000, 8000)
    assert row['feasible'] is True
    assert row['radius_km'] > 0
    assert row['fuel_kg_per_km'] > 0
    assert row['radius_m'] == pytest.approx(combat_radius_m(240.0, 3e-5, 8.0, 28000, 20000))
    bad_mass = _enrich_radius_point('mach_0_8', 'Ma 0.8', scored, 20000, 20000, 0)
    assert bad_mass['feasible'] is False
    assert bad_mass['warning'] == 'insufficient_mission_fuel'
    scored.tsfc_kg_n_s = None
    scored.eta_o = 0.0
    missing = _enrich_radius_point('x', 'x', scored, 28000, 20000, 8000)
    assert missing['feasible'] is False
    assert missing['warning'] == 'tsfc_unavailable'
    assert missing['fail_reason'] == '该点无法得到 TSFC'


def test_run_estimate_radius_from_params_f22():
    r = run_estimate_radius_from_params(_radius_params())
    assert r['success'] is True
    ids = [p['id'] for p in r['points']]
    assert ids == [
        'mach_0_8', 'mach_1_0', 'mach_1_2', 'mach_1_35', 'mach_1_5',
        'mach_1_75', 'mach_2_0',
        PRACTICAL_MAX_CRUISE_ID, FLOOR_MAX_CRUISE_ID,
    ]
    labels = {p['id']: p['label'] for p in r['points']}
    assert labels[PRACTICAL_MAX_CRUISE_ID] == PRACTICAL_MAX_CRUISE_LABEL
    assert labels[FLOOR_MAX_CRUISE_ID] == FLOOR_MAX_CRUISE_LABEL
    assert r['max_cruise_floor_mach'] is not None
    assert r['max_cruise_floor_mach'] + 1e-9 >= r['max_cruise_mach']
    m08 = r['points'][0]
    assert m08['feasible'] is True
    assert m08['radius_km'] > 100
    assert m08['fuel_kg_per_km'] > 0
    assert r['mach_angle_deg'] is not None
    assert r['mach_cone_limit'] > 1
    assert r['max_cruise_mach'] is not None
    assert r['mass_initial_kg'] > r['mass_cruise_kg'] > r['mass_final_kg']
    assert r['mass_initial_kg'] == pytest.approx(
        r['mass_takeoff_kg'] - r['mission_fuel']['climb_extra_kg'],
    )
    assert r['mass_final_kg'] == pytest.approx(
        r['mass_dry_kg'] + r['mission_fuel']['held_fuel_kg'],
    )
    assert r['mission_fuel'] is not None
    assert r['carrier'] is False
    assert r['mission_fuel']['reserve_min'] == 30
    assert r['fuel_usable_kg'] < r['fuel_kg']
    assert r['mission_fuel']['climb_extra_kg'] > 0
    assert r['mission_fuel']['descent_save_kg'] > 0
    assert r['mission_fuel']['takeoff_kg_per_km'] > r['mission_fuel']['landing_kg_per_km']
    assert '亚音速油耗' in r['note']
    from utils.combat_radius.breguet import combat_radius_m
    assert m08['radius_m'] == pytest.approx(combat_radius_m(
        m08['V0'], m08['tsfc_kg_n_s'], m08['ld'],
        r['mass_initial_kg'], r['mass_final_kg'],
    ))


def test_run_combat_radius_estimate_radius_action():
    ok = run_combat_radius('estimate_radius', _radius_params())
    assert ok['success'] is True
    assert len(ok['points']) == 9
    bad = run_combat_radius_json({'action': 'estimate_radius', 'params': {}})
    assert bad['success'] is False


def test_run_estimate_radius_rejects_zero_engines():
    p = _radius_params()
    p['n_engines'] = 0
    with pytest.raises(ValueError, match='发动机台数'):
        run_estimate_radius_from_params(p)


def test_main_prints_table(capsys, monkeypatch):
    fake = {
        'name': 'F-22 / F119',
        'mach_angle_deg': 20.0,
        'mach_cone_limit': 2.9,
        'max_cruise_mach': 1.6,
        'points': [
            {
                'id': 'mach_0_8', 'label': 'Ma 0.8', 'mach': 0.8, 'feasible': True,
                'alt_m': 12000, 'ld': 8.0, 'eta_o': 0.18, 'tsfc_mg_n_s': 30.0,
                'thrust_avail_kN': 60.0, 'load': 0.45, 'radius_km': 900.0,
                'fuel_kg_per_km': 4.5,
            },
            {
                'id': 'max_cruise', 'label': '实用最大巡航速度',
                'mach': 1.6, 'feasible': False,
            },
            {
                'id': 'floor_max_cruise', 'label': '最大巡航速度',
                'mach': 1.9, 'feasible': False,
            },
        ],
        'note': '布雷盖半径已计入陆基降落冗余 30 min（850 km/h 平飞）。',
    }
    monkeypatch.setattr(
        'simulators.combat_radius.combat_radius.run_estimate_radius_from_params',
        lambda _params: fake,
    )
    monkeypatch.setattr('sys.argv', ['combat_radius.py', '--aircraft', 'F-22', '--engine', 'f119'])
    main()
    out = capsys.readouterr().out
    assert 'F-22' in out
    assert '0.800' in out
    assert '实用最大巡航速度' in out
    assert '最大巡航速度' in out
    assert '92%' in out
    assert '布雷盖' in out


def test_main_rejects_missing_preset(monkeypatch):
    monkeypatch.setattr('sys.argv', ['combat_radius.py', '--aircraft', 'NOPE'])
    with pytest.raises(SystemExit, match='机型预设'):
        main()


def test_main_rejects_engine_without_tsl(monkeypatch):
    from utils.combat_radius.combat_radius_presets import get_preset_by_id as real_get

    def fake_get(presets, pid):
        if pid == 'notsl':
            return {'id': 'notsl', 'name': '无推力', 'bpr': 0.3, 'opr': 26.0, 't4_K': 1800.0}
        return real_get(presets, pid)

    monkeypatch.setattr('utils.combat_radius.combat_radius_presets.get_preset_by_id', fake_get)
    monkeypatch.setattr('sys.argv', ['combat_radius.py', '--aircraft', 'J-20', '--engine', 'notsl'])
    with pytest.raises(SystemExit, match='海平面军推'):
        main()


def test_main_rejects_missing_engine(monkeypatch):
    monkeypatch.setattr('sys.argv', ['combat_radius.py', '--engine', 'NOPE'])
    with pytest.raises(SystemExit, match='发动机预设'):
        main()


def test_as_bool_and_parse_carrier():
    """舰载标识：顶层优先于机型预设。"""
    assert _as_bool(True) is True
    assert _as_bool(0) is False
    assert _as_bool('是') is True
    assert _as_bool('否') is False
    assert _as_bool(None, True) is True
    assert _as_bool('maybe') is False
    assert _parse_carrier({'carrier': 1}) is True
    assert _parse_carrier({'target': {'carrier': True}}) is True
    assert _parse_carrier({}) is False
    assert _parse_carrier({'carrier': '0', 'target': {'carrier': True}}) is False


def test_radius_fail_reason_and_mission_note():
    """失败原因与任务油量说明文案。"""
    assert '冗余' in _radius_fail_reason('insufficient_mission_fuel')
    assert '亚音速' in _radius_fail_reason('subsonic_burn_unavailable')
    assert 'TSFC' in _radius_fail_reason('tsfc_unavailable')
    assert '92%' in _radius_fail_reason('no_feasible_altitude')
    note = _mission_fuel_note(
        True, 40,
        {'reserve_cruise_kph': 850, 'climb_extra_km': 120, 'descent_save_km': 87.5},
    )
    assert '舰载' in note and '40' in note and '120' in note


def test_failed_radius_point_keeps_aero():
    from utils.combat_radius.cruise_search import CruiseScored

    scored = CruiseScored(
        mach=0.8, alt_m=12000, ld=8.0, drag_N=30000, thrust_avail_N=60000,
        load_raw=0.5, feasible=True, cd_breakdown={'CL': 0.3},
        load=0.5, eta_o=0.18, v0=240.0, tsfc_kg_n_s=3e-5,
        tsfc_mg_n_s=30.0, tsfc_lb_lbf_h=1.1, score=1.44,
    )
    row = _failed_radius_point('mach_0_8', 'Ma 0.8', scored, 'insufficient_mission_fuel')
    assert row['feasible'] is False
    assert row['ld'] == 8.0
    assert row['radius_km'] is None
    assert '冗余' in row['fail_reason']


def test_infeasible_point_custom_warning():
    row = _infeasible_point('x', 'x', 1.5, 'insufficient_mission_fuel')
    assert row['warning'] == 'insufficient_mission_fuel'
    assert '冗余' in row['fail_reason']


def _radius_ctx():
    """用 F-22 半径参数搭一个巡航搜索上下文。"""
    from utils.combat_radius.cruise_load import combat_mass_breakdown
    from utils.combat_radius.cruise_search import CruiseContext
    from utils.combat_radius.engine_efficiency import (
        ACC_FRAC_DEFAULT, EPS_DEFAULT, ETAN_DEFAULT, T4IDLE_DEFAULT,
    )
    from utils.combat_radius.military_thrust import ETA_C_DEFAULT

    params = _radius_params()
    target, cf0, k_e = _calibrate_from_params(params)
    cruise = combat_mass_breakdown(
        empty_kg=float(params['empty_kg']),
        internal_fuel_kg=float(params['internal_fuel_kg']),
        n_pilots=float(params['n_pilots']),
        missile_mass_kg=float(params['missile_mass_kg']),
        n_missiles=float(params['n_missiles']),
        fuel_fraction=0.5,
    )
    return CruiseContext(
        target=target,
        cf0=cf0,
        k_e=k_e,
        mass_kg=cruise['total_kg'],
        n_engines=int(params['n_engines']),
        bpr=float(params['bpr']),
        opr=float(params['opr']),
        t4_K=float(params['t4_K']),
        tsl_N=float(params['tsl_kN']) * 1000.0,
        eta_c=ETA_C_DEFAULT,
        eps=EPS_DEFAULT,
        etan=ETAN_DEFAULT,
        acc_frac=ACC_FRAC_DEFAULT,
        t4idle=T4IDLE_DEFAULT,
    )


def test_subsonic_scored_for_burn_search_and_fallback(monkeypatch):
    """优先用 Ma 0.8 最佳高度；搜索失败时退到 12 km。"""
    from utils.combat_radius.cruise_search import CruiseScored

    ctx = _radius_ctx()
    scored = _subsonic_scored_for_burn(ctx, 11000, 20000, 3000, 1500)
    assert scored is not None
    assert scored.tsfc_kg_n_s is not None
    assert scored.v0 > 0

    fake = CruiseScored(
        mach=0.8, alt_m=12000, ld=8.0, drag_N=30000, thrust_avail_N=60000,
        load_raw=0.5, feasible=True, cd_breakdown={'CL': 0.3},
        load=0.5, eta_o=0.18, v0=240.0, tsfc_kg_n_s=3e-5,
        tsfc_mg_n_s=30.0, tsfc_lb_lbf_h=1.1, score=1.44,
    )
    monkeypatch.setattr(
        'simulators.combat_radius.combat_radius.search_best_altitude',
        lambda *a, **k: fake,
    )
    assert _subsonic_scored_for_burn(ctx, 11000, 20000, 3000, 1500) is fake

    monkeypatch.setattr(
        'simulators.combat_radius.combat_radius.search_best_altitude',
        lambda *a, **k: None,
    )
    fallback = _subsonic_scored_for_burn(ctx, 11000, 20000, 3000, 1500)
    assert fallback is not None
    assert fallback.tsfc_kg_n_s is not None

    dead = CruiseScored(
        mach=0.8, alt_m=12000, ld=8.0, drag_N=30000, thrust_avail_N=60000,
        load_raw=0.5, feasible=False, cd_breakdown={'CL': 0.3},
        load=1.0, eta_o=0.0, v0=0.0, tsfc_kg_n_s=None,
        tsfc_mg_n_s=None, tsfc_lb_lbf_h=None, score=-1.0,
    )
    monkeypatch.setattr(
        'simulators.combat_radius.combat_radius.score_cruise_point',
        lambda *a, **k: dead,
    )
    assert _subsonic_scored_for_burn(ctx, 11000, 20000, 3000, 1500) is None


def test_subsonic_burn_unavailable_marks_points(monkeypatch):
    monkeypatch.setattr(
        'simulators.combat_radius.combat_radius._subsonic_scored_for_burn',
        lambda *a, **k: None,
    )
    r = run_estimate_radius_from_params(_radius_params())
    m08 = next(p for p in r['points'] if p['id'] == 'mach_0_8')
    assert m08['feasible'] is False
    assert m08['warning'] == 'subsonic_burn_unavailable'
    assert r['mission_fuel'] is None
    assert r['fuel_usable_kg'] is None


def test_carrier_reserve_reduces_radius_vs_land():
    """同样气动下舰载 40 min 冗余比陆基 30 min 更短。"""
    land = run_estimate_radius_from_params({**_radius_params(), 'carrier': False})
    sea = run_estimate_radius_from_params({**_radius_params(), 'carrier': True})
    assert land['mission_fuel']['reserve_min'] == 30
    assert sea['mission_fuel']['reserve_min'] == 45
    r_land = next(p for p in land['points'] if p['id'] == 'mach_0_8')['radius_km']
    r_sea = next(p for p in sea['points'] if p['id'] == 'mach_0_8')['radius_km']
    assert r_sea < r_land
    m15 = next(p for p in sea['points'] if p['id'] == 'mach_1_5')
    m08 = next(p for p in sea['points'] if p['id'] == 'mach_0_8')
    if m15.get('feasible'):
        assert m15['radius_km'] != m08['radius_km']


def test_insufficient_mission_fuel_marks_points_infeasible():
    """内油过少时保留气动点但不给出半径。"""
    p = _radius_params()
    p['internal_fuel_kg'] = 50
    r = run_estimate_radius_from_params(p)
    m08 = next(x for x in r['points'] if x['id'] == 'mach_0_8')
    assert m08['feasible'] is False
    assert m08['warning'] == 'insufficient_mission_fuel'
    assert m08['radius_km'] is None
    assert r['fuel_usable_kg'] is not None and r['fuel_usable_kg'] <= 0


def test_ma08_combat_radius_calibration_targets():
    """Ma 0.8 作战半径：统一模型下 F-35C（F135 安装惩罚）/ F-22 / 歼-20 量级。"""
    from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets

    presets = load_presets()
    engines = load_engine_presets()
    cases = [
        ('F-35C', 'f135', 1400, 50),
        ('F-22', 'f119', 1034, 50),
        ('J-20', 'ws15', 1350, 50),
    ]
    for ac_id, eng_id, target_km, tol_km in cases:
        tgt = get_preset_by_id(presets, ac_id)
        eng = get_preset_by_id(engines, eng_id)
        r = run_estimate_radius_from_params({
            'target': tgt,
            'empty_kg': tgt['empty_kg'],
            'internal_fuel_kg': tgt['internal_fuel_kg'],
            'n_pilots': tgt['n_pilots'],
            'missile_mass_kg': tgt['missile_mass_kg'],
            'n_engines': tgt['n_engines'],
            'bpr': eng['bpr'],
            'opr': eng['opr'],
            't4_K': eng['t4_K'],
            'tsl_kN': eng['tsl_kN'],
            'tsfc_install_mult': eng.get('tsfc_install_mult', 1.0),
        })
        m08 = next(p for p in r['points'] if p['id'] == 'mach_0_8')
        assert m08['feasible'] is True, ac_id
        assert m08['radius_km'] == pytest.approx(target_km, abs=tol_km), (
            f'{ac_id} Ma0.8={m08["radius_km"]:.0f} km, 目标 {target_km}±{tol_km}'
        )


def test_cruise_context_from_params_uses_half_fuel():
    ctx, ac = _cruise_context_from_params(_radius_params())
    assert ctx.n_engines == 2
    assert ac.name == 'F-22 Raptor' or 'F-22' in ac.name
    assert ctx.mass_kg > 0
    assert ctx.tsl_N == pytest.approx(116000.0)
    filled = ensure_default_anchors({'target': {'name': 'X'}})
    assert 'anchor1' not in filled
    already = ensure_default_anchors(_sample_params())
    assert already['target']['name'] == 'J-20'


def test_clear_and_attach_mixed_radius():
    row = {'id': 'mach_1_5'}
    _clear_mixed_radius_fields(row)
    assert row['mixed_radius_km'] is None
    sub = {
        'id': 'mach_0_8', 'feasible': True, 'V0': 240.0, 'tsfc_kg_n_s': 2.5e-5,
        'ld': 8.0, 'mach': 0.8,
    }
    super_pt = {
        'id': 'mach_1_5', 'feasible': True, 'V0': 500.0, 'tsfc_kg_n_s': 5.0e-5,
        'ld': 5.0, 'mach': 1.5,
    }
    subsonic_only = {
        'id': 'mach_0_8b', 'feasible': True, 'V0': 240.0, 'tsfc_kg_n_s': 2.5e-5,
        'ld': 8.0, 'mach': 0.8,
    }
    points = [sub, super_pt, subsonic_only]
    _attach_mixed_radius(points, 28000.0, 20000.0, 8000.0)
    assert super_pt['mixed_radius_km'] > 0
    assert super_pt['mixed_fuel_kg_per_km'] > 0
    assert subsonic_only['mixed_radius_km'] is None
    from utils.combat_radius.breguet import mixed_combat_radius_m
    assert super_pt['mixed_radius_m'] == pytest.approx(
        mixed_combat_radius_m(
            500.0, 5.0e-5, 5.0, 240.0, 2.5e-5, 8.0, 28000.0, 20000.0,
        ),
    )


def test_compact_max_speed_drops_profile():
    compact = compact_max_speed({
        'success': True, 'feasible': True, 'max_speed_mach': 2.1,
        'max_speed_kmh': 2200, 'max_speed_kts': 1188, 'alt_m': 11000,
        'ld': 4.0, 'load': 0.9, 'thrust_avail_kN': 80, 'note': 'x',
        'profile': [{'alt_m': 0}],
    })
    assert 'profile' not in compact
    assert compact['max_speed_mach'] == 2.1


def test_run_search_best_cruise_from_params_ma08():
    r = run_search_best_cruise_from_params({**_radius_params(), 'mach': 0.8})
    assert r['success'] is True
    assert r['feasible'] is True
    assert r['ld'] > 0
    assert r['eta_th'] > 0
    assert r['eta_p'] > 0
    assert r['thrust_avail_kN'] > 0
    assert r['max_ld'] >= r['ld'] - 1e-9
    assert r['max_ld_thrust_mode'] == 'military'
    assert 11000.0 <= r['alt_m'] <= 12500.0


def test_run_search_best_cruise_infeasible_mach():
    r = run_search_best_cruise_from_params({**_radius_params(), 'mach': 3.5})
    assert r['success'] is True
    assert r['feasible'] is False
    assert '92%' in r['fail_reason']
    assert r['max_ld'] is None


def test_run_search_best_cruise_infeasible_has_ab_max_ld():
    """不能军推巡航的马赫仍应给出加力可飞高度上的最大升阻比。"""
    r = run_search_best_cruise_from_params({
        **_radius_params(), 'mach': 2.2, 'max_tsl_kN': 156.0,
        'alt_coarse_m': 1000, 'alt_refine_m': 200,
        'mach_search_hi': 2.5,
    })
    assert r['success'] is True
    assert r['feasible'] is False
    assert r['max_ld'] is not None and r['max_ld'] > 0
    assert r['max_ld_thrust_mode'] == 'afterburner'


def test_optional_ab_context_and_attach_max_ld():
    """有加力则构造加力上下文；马赫非法时最大升阻比为空。"""
    ctx, _tgt = _cruise_context_from_params(_radius_params())
    assert _optional_ab_context(ctx, _radius_params()) is None
    ab = _optional_ab_context(ctx, {**_radius_params(), 'max_tsl_kN': 156.0})
    assert ab is not None
    assert ab.tsl_N == pytest.approx(156000.0)
    assert ab.thrust_margin == pytest.approx(MAX_SPEED_THRUST_MARGIN)
    empty = _attach_max_ld_to_point(
        {}, ctx, None, ab, 11000, 20000, 3000, 1500,
    )
    assert empty['max_ld'] is None
    row = _attach_max_ld_to_point(
        {}, ctx, 0.8, ab, 11000, 20000, 3000, 1500,
    )
    assert row['max_ld'] > 0
    assert row['max_ld_thrust_mode'] == 'military'


def test_run_estimate_engine_cycle_from_params():
    r = run_estimate_engine_cycle_from_params({
        'bpr': 0.30, 'opr': 26.0, 't4_K': 1922,
        'mach': 0.8, 'alt_m': 12000, 'load': 0.5,
    })
    assert r['success'] is True
    assert r['eta_th'] > 0
    assert r['eta_p'] > 0
    assert r['eta_o'] > 0
    pct = run_estimate_engine_cycle_from_params({
        'bpr': 0.30, 'opr': 26.0, 't4_K': 1922,
        'mach': 0.8, 'alt_m': 12000, 'load': 50,
    })
    assert pct['load'] == pytest.approx(0.5)


def test_run_estimate_engine_cycle_applies_install_mult():
    """效率循环 API 须把安装惩罚乘到 TSFC、压到对外 η_o。"""
    base = run_estimate_engine_cycle_from_params({
        'bpr': 0.57, 'opr': 28.0, 't4_K': 2260,
        'mach': 0.8, 'alt_m': 11000, 'load': 0.58,
    })
    penalized = run_estimate_engine_cycle_from_params({
        'bpr': 0.57, 'opr': 28.0, 't4_K': 2260,
        'mach': 0.8, 'alt_m': 11000, 'load': 0.58,
        'tsfc_install_mult': 1.22,
    })
    assert penalized['tsfc_kg_n_s'] == pytest.approx(base['tsfc_kg_n_s'] * 1.22)
    assert penalized['eta_o'] == pytest.approx(base['eta_o'] / 1.22)


def test_run_estimate_engine_cycle_rejects_missing_t4():
    with pytest.raises(ValueError, match='涡轮前温度'):
        run_estimate_engine_cycle_from_params({
            'bpr': 0.3, 'mach': 0.8, 'alt_m': 12000, 'load': 0.4,
        })


def test_run_aircraft_dashboard_from_params_f22():
    p = _radius_params()
    p['max_tsl_kN'] = 156.0
    dash = run_aircraft_dashboard_from_params(p)
    assert dash['success'] is True
    ids = [p['id'] for p in dash['points']]
    assert 'mach_2_0' in ids
    m08 = next(pt for pt in dash['points'] if pt['id'] == 'mach_0_8')
    assert m08['mixed_radius_km'] is None
    assert m08['max_ld'] is not None and m08['max_ld'] > 0
    assert m08['max_ld_thrust_mode'] == 'military'
    m10 = next(pt for pt in dash['points'] if pt['id'] == 'mach_1_0')
    assert m10['feasible'] is True
    assert m10['mixed_radius_km'] is None
    m12 = next(pt for pt in dash['points'] if pt['id'] == 'mach_1_2')
    assert m12['feasible'] is True
    assert m12['mixed_radius_km'] is not None and m12['mixed_radius_km'] > 0
    m135 = next(pt for pt in dash['points'] if pt['id'] == 'mach_1_35')
    assert m135['feasible'] is True
    m175 = next(pt for pt in dash['points'] if pt['id'] == 'mach_1_75')
    assert m175['feasible'] is True
    m20 = next(pt for pt in dash['points'] if pt['id'] == 'mach_2_0')
    assert m20['max_ld'] is not None and m20['max_ld'] > 0
    assert dash['max_speed']['feasible'] is True
    assert dash['max_speed']['ld'] is not None
    supers = [pt for pt in dash['points'] if pt.get('feasible') and (pt.get('mach') or 0) > 1]
    if supers:
        assert any(pt.get('mixed_radius_km') for pt in supers)


def test_run_aircraft_dashboard_f35c_ab_flyable_has_max_ld():
    """F-35C 加力可飞的 Ma 1.5 须有最大升阻比。"""
    from utils.combat_radius.combat_radius_results import dashboard_params_from_preset
    from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets

    ac = get_preset_by_id(load_presets(), 'F-35C')
    eng = get_preset_by_id(load_engine_presets(), ac['engine_id'])
    dash = run_aircraft_dashboard_from_params(dashboard_params_from_preset(ac, eng))
    assert dash['success'] is True
    vmax = dash['max_speed']['max_speed_mach']
    assert vmax is not None and vmax > 1.4
    m15 = next(pt for pt in dash['points'] if pt['id'] == 'mach_1_5')
    assert m15['max_ld'] is not None and m15['max_ld'] > 0
    assert m15['max_ld_thrust_mode'] == 'afterburner'
    for pt in dash['points']:
        mach = pt.get('mach')
        if mach is None or mach > vmax + 1e-9:
            continue
        assert pt['max_ld'] is not None and pt['max_ld'] > 0, pt['id']


def test_run_combat_radius_new_actions():
    dash = run_combat_radius('aircraft_dashboard', _radius_params())
    assert dash['success'] is True
    search = run_combat_radius('search_best_cruise', {**_radius_params(), 'mach': 0.8})
    assert search['feasible'] is True
    cycle = run_combat_radius('estimate_engine_cycle', {
        'bpr': 0.30, 'opr': 26.0, 't4_K': 1922, 'mach': 0.8, 'alt_m': 12000, 'load': 0.4,
    })
    assert cycle['eta_o'] > 0

