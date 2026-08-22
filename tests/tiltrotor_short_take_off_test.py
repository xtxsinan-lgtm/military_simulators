"""倾转旋翼短距起飞仿真单元测试。"""
from __future__ import annotations

import pytest

import simulators.takeoff.tiltrotor_short_take_off as tilt
from utils.database_csv import load_aircraft_csv
from utils.paths import AIRCRAFT_CSV
from utils.takeoff.takeoff_physics import G, KT_TO_MPS, M_TO_FT


def _restore_mv22_defaults():
    """恢复模块默认推进与参考质量，避免用例互相污染。"""
    ac = load_aircraft_csv(AIRCRAFT_CSV)['MV-22']
    tilt.apply_thrust_temperature(15.0)
    tilt.apply_propulsion_sl(
        ac.shaft_power_sl_w, ac.prop_diameter_m,
        nacelle_blockage_frac=ac.nacelle_blockage_frac,
    )
    tilt.apply_wind_knots(22.0)
    tilt.apply_aircraft_geometry(
        20827.0, ac.wing_area_m2, ac.wingspan_m, ac.wing_height_m,
        ac.sweep_le_deg, ac.cd0,
    )


def _configure(mass_kg: float, temp_c: float, wind_kt: float):
    ac = load_aircraft_csv(AIRCRAFT_CSV)['MV-22']
    tilt.apply_thrust_temperature(temp_c)
    tilt.apply_propulsion_sl(
        ac.shaft_power_sl_w, ac.prop_diameter_m,
        nacelle_blockage_frac=ac.nacelle_blockage_frac,
    )
    tilt.apply_wind_knots(wind_kt)
    tilt.apply_aircraft_geometry(
        mass_kg, ac.wing_area_m2, ac.wingspan_m, ac.wing_height_m,
        ac.sweep_le_deg, ac.cd0,
    )


def test_nacelle_rate_from_wikipedia_12s_for_90deg():
    assert tilt.NACELLE_RATE_DEG_S == pytest.approx(7.5)


def test_current_prop_thrust_positive_at_hover():
    t = tilt.current_prop_thrust_n(0.0, 90.0)
    assert t > 150000  # 约 >150 kN，足以支撑中等重量


def test_net_vertical_force_n_hover_near_vtol_weight():
    _configure(23859.0, 15.0, 0.0)
    try:
        net = tilt.net_vertical_force_n(0.0, 90.0, tilt.CL_ROTATION)
        assert net == pytest.approx(23859.0 * G, rel=0.02)
    finally:
        _restore_mv22_defaults()


def test_slipstream_q_increases_at_sto_nacelle():
    q_hover = tilt._slipstream_q(8.0, 90.0, 260000.0)
    q_sto = tilt._slipstream_q(8.0, 60.0, 250000.0)
    assert q_sto > q_hover


def test_thrust_components_split_at_45deg():
    t_h, t_v = tilt._thrust_components(0.0, 45.0)
    assert t_h == pytest.approx(t_v, rel=0.02)


def test_aero_step_returns_five_forces():
    t_h, t_v, lift, lift_rot, drag = tilt._aero_step(10.0, 60.0)
    assert t_h > 0 and t_v > 0
    assert lift_rot >= lift
    assert drag > 0


def test_evaluate_liftoff_hover_is_zero_distance():
    _configure(23859.0, 15.0, 0.0)
    try:
        hist, airborne = tilt.simulate_strategy_b(90.0)
        assert airborne is True
        lo = tilt.evaluate_liftoff(hist)
        assert lo is not None
        assert lo['x_m'] == pytest.approx(0.0)
    finally:
        _restore_mv22_defaults()


def test_simulate_strategy_b_can_liftoff():
    hist, airborne = tilt.simulate_strategy_b(45.0)
    assert airborne is True
    lo = tilt.evaluate_liftoff(hist)
    assert lo is not None
    assert lo['x_m'] >= 0


def test_run_strategy_a_search_returns_feasible():
    best = tilt.run_strategy_a_search()
    assert best is not None
    assert best['x_m'] >= 0
    assert 0 <= best['nozzle_deg'] <= 90


def test_run_strategy_b_search_returns_feasible():
    best = tilt.run_strategy_b_search()
    assert best is not None
    assert best['x_m'] >= 0


def test_run_strategy_c_search_raises():
    with pytest.raises(ValueError, match='策略 C'):
        tilt.run_strategy_c_search()


def test_apply_propulsion_sl_updates_power():
    tilt.apply_propulsion_sl(8e6, 11.0, nacelle_blockage_frac=0.12)
    assert tilt.SHAFT_POWER_SL_W == 8e6
    assert tilt.PROP_DIAMETER_M == 11.0
    assert tilt.NACELLE_BLOCKAGE_FRAC == 0.12
    _restore_mv22_defaults()


def test_vtol_weight_strategy_b_lifts_at_zero():
    """官方垂起重量 52,600 lb 在 15°C 无风时应 0 m 离地。"""
    _configure(23859.0, 15.0, 0.0)
    try:
        best = tilt.run_strategy_b_search()
        assert best is not None
        assert best['x_m'] == pytest.approx(0.0, abs=0.5)
    finally:
        _restore_mv22_defaults()


def test_official_sto_60deg_about_300ft():
    """官方短距：25,855 kg、60° 短舱、15 kt、15°C，约 300 英尺。"""
    _configure(25855.0, 15.0, 15.0)
    try:
        hist, airborne = tilt.simulate_strategy_b(60.0)
        assert airborne is True
        lo = tilt.evaluate_liftoff(hist)
        assert lo is not None
        dist_ft = lo['x_m'] * M_TO_FT
        assert 200.0 < dist_ft < 420.0
        assert lo['x_m'] < 130.0
    finally:
        _restore_mv22_defaults()
