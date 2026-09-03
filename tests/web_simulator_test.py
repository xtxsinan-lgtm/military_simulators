"""web_simulator 单元测试。"""
import json

import pytest

from apps.web_simulator import (
    _wing_geom,
    compute_aircraft_aero,
    filter_aircraft_for_mode,
    filter_carriers_for_mode,
    format_output_summary,
    resolve_ski_jump_geom,
    result_distance_m,
    run_simulation,
    run_simulation_json,
)
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV


@pytest.fixture(scope='module')
def aircraft():
    return load_aircraft_csv(AIRCRAFT_CSV)


@pytest.fixture(scope='module')
def carriers():
    return load_carriers_csv(CARRIERS_CSV)


def test_format_output_summary_with_margin():
    """有余量时显示起飞距离与甲板余量。"""
    assert format_output_summary(85.6, 120.4) == '起飞 85.6 m · 余量 120.4 m'


def test_format_output_summary_with_overrun():
    """甲板不足时显示超出距离。"""
    assert format_output_summary(300.0, -12.3) == '起飞 300.0 m · 超出 12.3 m'


def test_format_output_summary_distance_only():
    """仅有起飞距离时不附带甲板字段。"""
    assert format_output_summary(52.4, None) == '起飞 52.4 m'
    assert format_output_summary(None, 10.0) == ''
    assert format_output_summary(0.0, 250.0) == '起飞 0.0 m · 余量 250.0 m'


def test_result_distance_m_keeps_zero():
    """垂起 0 m 不得被布尔 or 丢掉。"""
    assert result_distance_m({'distance_m': 0.0}) == 0.0
    assert result_distance_m({'total_m': 0}) == 0.0
    assert result_distance_m({'distance_m': None, 'total_m': 12.5}) == 12.5
    assert result_distance_m({}) is None


def test_resolve_ski_jump_from_height():
    geom = resolve_ski_jump_geom(12.0, height_m=5.099)
    assert geom['lip_height_m'] == pytest.approx(5.099)
    assert geom['arc_length_m'] > 0


def test_resolve_ski_jump_from_arc_length():
    geom = resolve_ski_jump_geom(12.0, arc_length_m=41.9)
    assert geom['arc_length_m'] == pytest.approx(41.9)
    assert geom['lip_height_m'] > 0


def test_filter_carriers_ski_jump_mode(carriers):
    ids = {c.id for c in filter_carriers_for_mode('ski_jump', carriers)}
    assert 'SHANDONG' in ids
    assert 'WASP' not in ids


def test_filter_aircraft_short_takeoff(aircraft):
    ac = filter_aircraft_for_mode('short_takeoff', list(aircraft.values()))
    assert len(ac) == 3
    ids = {a.id for a in ac}
    assert ids == {'F-35B', 'AV-8B', 'NG6B'}


def test_filter_aircraft_tiltrotor_and_ski_jump_excludes_tiltrotor(aircraft):
    tilt = filter_aircraft_for_mode('tiltrotor_short_takeoff', list(aircraft.values()))
    assert {a.id for a in tilt} == {'MV-22'}
    ski = filter_aircraft_for_mode('ski_jump', list(aircraft.values()))
    assert all(a.type_label == 'conventional' for a in ski)
    assert 'MV-22' not in {a.id for a in ski}


def test_wing_geom_includes_canard_fields(aircraft):
    """起飞几何须带上布局与鸭翼面积，供滑跃增升使用。"""
    ac = aircraft['J-10C']
    geom = _wing_geom(ac, ac.a2a_mass_kg)
    assert geom['layout'] == 'canard'
    assert geom['canard_htail_area_m2'] == pytest.approx(4.9)
    assert geom['s_ref_m2'] == pytest.approx(37.0)


def test_compute_aircraft_aero_j15(aircraft):
    aero = compute_aircraft_aero(aircraft['J-15'])
    assert aero['aspect_ratio'] == pytest.approx(14.7 ** 2 / 67.84)
    assert aero['cl_20deg'] > aero['cl_taxi']


def test_compute_aircraft_aero_j10c_includes_canard_lift(aircraft):
    """歼-10C 预览 C_Lα 含近距耦合鸭翼净增升。"""
    from dataclasses import replace
    from utils.takeoff.takeoff_physics import calc_canard_lift_factor

    ac = aircraft['J-10C']
    factor = calc_canard_lift_factor(ac.layout, ac.canard_htail_area_m2, ac.wing_area_m2)
    assert factor > 1.0
    with_canard = compute_aircraft_aero(ac)
    without = compute_aircraft_aero(replace(ac, layout='conventional'))
    assert with_canard['cl_taxi'] == pytest.approx(without['cl_taxi'] * factor)
    assert with_canard['cl_alpha_per_rad'] == pytest.approx(without['cl_alpha_per_rad'] * factor)


def test_run_simulation_ski_jump_j15(aircraft, carriers):
    carrier = next(c for c in carriers if c.id == 'SHANDONG')
    ac = aircraft['J-15']
    result = run_simulation(
        'ski_jump', ac, carrier, ac.a2a_mass_kg, 30.0, carrier.max_speed_kt,
    )
    assert result['success'] is True
    assert result['distance_m'] == pytest.approx(82.6, rel=0.03)
    assert result['deck_launch_ok'] is True
    assert '起飞' in result['output_summary']
    assert '余量' in result['output_summary']
    assert result['plume_applicable'] is False
    assert result['min_plume_trailing_edge_m'] is None
    assert result['trajectory']
    assert result['deck_profile']
    assert result['highlights']
    assert any(c['key'] == 'distance' for c in result['highlights'])
    assert result['trajectory'][0]['phase'] == 'flat'
    assert any(p['phase'] == 'arc' for p in result['trajectory'])


def test_run_simulation_short_takeoff_no_trajectory(aircraft, carriers):
    carrier = next(c for c in carriers if c.id == 'WASP')
    ac = aircraft['F-35B']
    result = run_simulation(
        'short_takeoff', ac, carrier, ac.a2a_mass_kg, 30.0, 22.0,
    )
    assert result['success'] is True
    assert result['plume_applicable'] is True
    assert result['min_plume_trailing_edge_m'] is not None
    assert result['trajectory'] is None
    assert result['deck_profile'] is None


def test_run_simulation_json_string(aircraft, carriers):
    carrier = next(c for c in carriers if c.id == 'WASP')
    ac = aircraft['F-35B']
    payload = {
        'mode': 'short_takeoff',
        'aircraft': {
            'id': ac.id, 'name': ac.name, 'type_label': ac.type_label,
            'mtow_kg': ac.mtow_kg, 'empty_kg': ac.empty_kg,
            'internal_fuel_kg': ac.internal_fuel_kg,
            'max_payload_kg': ac.max_payload_kg,
            'bvr_missile': ac.bvr_missile, 'missile_mass_kg': ac.missile_mass_kg,
            'sweep_le_deg': ac.sweep_le_deg, 'wingspan_m': ac.wingspan_m,
            'wing_area_m2': ac.wing_area_m2, 'wing_height_m': ac.wing_height_m,
            'cd0': ac.cd0,
            't_main_stovl_sl_n': ac.t_main_stovl_sl_n,
            't_liftfan_sl_n': ac.t_liftfan_sl_n,
            't_rollposts_sl_n': ac.t_rollposts_sl_n,
        },
        'carrier': {
            'id': carrier.id, 'name': carrier.name, 'nation': carrier.nation,
            'max_speed_kt': carrier.max_speed_kt, 'ski_jump': carrier.ski_jump,
            'total_deck_length_m': carrier.total_deck_length_m,
            'ski_jump_angle_deg': carrier.ski_jump_angle_deg,
            'f35b_capable': carrier.f35b_capable,
        },
        'mass_kg': ac.a2a_mass_kg,
        'temp_c': 30.0,
        'wind_kt': 22.0,
    }
    result = run_simulation_json(json.dumps(payload))
    assert result['success'] is True
    assert result['distance_m'] == pytest.approx(52.4, rel=0.05)


def test_run_simulation_rejects_negative_mass(aircraft, carriers):
    """负重量在搜索前拒绝，不进入物理引擎。"""
    carrier = next(c for c in carriers if c.id == 'SHANDONG')
    ac = aircraft['J-15']
    result = run_simulation('ski_jump', ac, carrier, -500.0, 30.0, carrier.max_speed_kt)
    assert result['success'] is False
    assert '正数' in result['error']


def test_run_simulation_rejects_mass_above_mtow(aircraft, carriers):
    """超出 MTOW 在搜索前拒绝。"""
    carrier = next(c for c in carriers if c.id == 'WASP')
    ac = aircraft['F-35B']
    result = run_simulation('short_takeoff', ac, carrier, 50000.0, 30.0, 22.0)
    assert result['success'] is False
    assert '超出最大起飞重量' in result['error']
    assert str(int(ac.mtow_kg)) in result['error']
