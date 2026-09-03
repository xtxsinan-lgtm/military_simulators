"""ski_jump_take_off.py 核心仿真单元测试。"""
import pytest

import simulators.takeoff.ski_jump_take_off as ski_conv


def _restore_ski_conv_defaults():
    """恢复模块默认参数，避免其他测试的 apply_* 污染基线对比。"""
    ski_conv.apply_aircraft_geometry(
        mass_kg=29500,
        s_ref_m2=68.9,
        wingspan_m=13.6,
        wing_height_m=1.96,
        sweep_le_deg=38,
        cd0=0.039,
        t_max_sl_n=186000,
    )
    ski_conv.apply_thrust_temperature(30.0)
    ski_conv.apply_wind_knots(30.0)
    ski_conv.apply_ski_jump_deck(14.0)


def test_simulate_100m_15deg_prefix_matches_baseline(baseline):
    _restore_ski_conv_defaults()
    sim = ski_conv.simulate(100.0, 15.0)
    assert sim[:5] == pytest.approx(tuple(baseline['ski_conv']['simulate_100_15']), rel=0, abs=1e-6)


def test_simulate_rejects_excessive_pitch():
    with pytest.raises(ValueError, match='超过硬上限'):
        ski_conv.simulate(50.0, ski_conv.PITCH_MAX_DEG + 1)


def test_total_takeoff_distance_adds_horizontal():
    _restore_ski_conv_defaults()
    flat_m = 80.0
    total = ski_conv.total_takeoff_distance_m(flat_m)
    assert total == pytest.approx(flat_m + ski_conv.SKI_JUMP_HORIZONTAL_M)


def _apply_c2_ski_jump():
    """把滑跃模块配成 C-2A 几何与涡桨功率。"""
    from utils.database_csv import load_aircraft_csv
    from utils.paths import AIRCRAFT_CSV

    ac = load_aircraft_csv(AIRCRAFT_CSV)['C-2']
    ski_conv.apply_aircraft_geometry(
        mass_kg=ac.a2a_mass_kg,
        s_ref_m2=ac.wing_area_m2,
        wingspan_m=ac.wingspan_m,
        wing_height_m=ac.wing_height_m,
        sweep_le_deg=ac.sweep_le_deg,
        cd0=ac.cd0,
        t_max_sl_n=ac.t_max_sl_n,
    )
    ski_conv.apply_thrust_temperature(15.0)
    ski_conv.apply_wind_knots(30.0)
    ski_conv.apply_ski_jump_deck(14.0)
    ski_conv.apply_propulsion_sl(
        ac.shaft_power_sl_w,
        ac.prop_diameter_m,
        nacelle_blockage_frac=ac.nacelle_blockage_frac,
    )
    return ac


def test_current_thrust_n_jet_is_constant():
    """喷气机滑跃推力不随空速变化。"""
    _restore_ski_conv_defaults()
    assert ski_conv.uses_propeller_power_model() is False
    t0 = ski_conv.current_thrust_n(0.0)
    t40 = ski_conv.current_thrust_n(40.0)
    assert t0 == pytest.approx(ski_conv.T_MAX_N)
    assert t40 == pytest.approx(t0)


def test_current_thrust_n_propeller_falls_with_speed():
    """涡桨恒定功率：前飞推力低于静推力，零速与机库静推力一致。"""
    ac = _apply_c2_ski_jump()
    try:
        assert ski_conv.uses_propeller_power_model() is True
        t0 = ski_conv.current_thrust_n(0.0)
        t40 = ski_conv.current_thrust_n(40.0)
        assert t40 < t0
        assert t0 == pytest.approx(ac.t_max_sl_n, rel=1e-3)
    finally:
        _restore_ski_conv_defaults()


def test_apply_aircraft_geometry_clears_propeller_power():
    """换喷气机后不得残留上一架涡桨的功率模型。"""
    _apply_c2_ski_jump()
    _restore_ski_conv_defaults()
    assert ski_conv.uses_propeller_power_model() is False
    assert ski_conv.current_thrust_n(30.0) == pytest.approx(ski_conv.T_MAX_N)


def test_propeller_ski_jump_slower_than_constant_static_thrust():
    """同一平直段上，恒定功率离舰速度低于把静推力当恒定推力。"""
    _apply_c2_ski_jump()
    try:
        flat_m, pitch_deg = 80.0, 12.0
        _, _, v_power, *_ = ski_conv.simulate(flat_m, pitch_deg)
        ski_conv.apply_propulsion_sl(0.0, 0.0)
        _, _, v_const, *_ = ski_conv.simulate(flat_m, pitch_deg)
        assert v_power < v_const
    finally:
        _restore_ski_conv_defaults()
