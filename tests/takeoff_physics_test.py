"""Unit tests for takeoff_physics.py."""
import pytest

from utils.takeoff.takeoff_physics import (
    FLAP_DEFLECTION_DEG,
    FLAP_EFFICIENCY,
    PITCH_MAX_DEG,
    RHO_ISA_KG_M3,
    WING_INCIDENCE_DEG,
    calc_cl_alpha,
    calc_cl_from_alpha_deg,
    calc_ground_effect_phi,
    calc_oswald_e,
    calc_sea_level_density_kg_m3,
    calc_thrust_temp_factor,
    check_pitch_deg,
    drag_coefficient,
    dynamic_pressure,
    taxi_alpha_deg,
    wind_knots_to_mps,
    KT_TO_MPS,
)


def test_sea_level_density_at_15c_is_isa():
    assert calc_sea_level_density_kg_m3(15.0) == pytest.approx(RHO_ISA_KG_M3)


def test_sea_level_density_at_30c():
    assert calc_sea_level_density_kg_m3(30.0) == pytest.approx(1.1643864423552697)


def test_thrust_temp_factor_at_reference_is_one():
    assert calc_thrust_temp_factor(15.0) == pytest.approx(1.0)


def test_thrust_temp_factor_at_30c():
    assert calc_thrust_temp_factor(30.0) == pytest.approx(0.9577824912253099)


def test_oswald_and_cl_alpha_f35b_defaults():
    ar = 10.7 ** 2 / 42.7
    eta = calc_oswald_e(ar, 35.0)
    cla = calc_cl_alpha(ar, eta, 35.0)
    assert eta == pytest.approx(0.9803776689554655)
    assert cla == pytest.approx(2.8593134123778405)


def test_ground_effect_phi_f35b():
    phi = calc_ground_effect_phi(1.96, 10.7)
    assert phi == pytest.approx(0.8957228612575774)


def test_taxi_alpha_default():
    assert taxi_alpha_deg() == FLAP_DEFLECTION_DEG * FLAP_EFFICIENCY + WING_INCIDENCE_DEG


def test_cl_from_alpha_linear():
    assert calc_cl_from_alpha_deg(10.0, 2.0) == pytest.approx(0.3490658503988659)


def test_dynamic_pressure():
    assert dynamic_pressure(1.225, 10.0) == pytest.approx(61.25)


def test_drag_coefficient_ground_effect():
    cd = drag_coefficient(0.039, 0.1, 0.5, 0.9)
    assert cd == pytest.approx(0.039 + 0.1 * 0.25 * 0.9)


def test_wind_knots_to_mps():
    assert wind_knots_to_mps(30.0) == pytest.approx(30.0 * KT_TO_MPS)


def test_check_pitch_deg_accepts_limit():
    assert check_pitch_deg(PITCH_MAX_DEG) == PITCH_MAX_DEG


def test_check_pitch_deg_rejects_over_limit():
    with pytest.raises(ValueError, match='超过硬上限'):
        check_pitch_deg(PITCH_MAX_DEG + 1)


def test_canard_lift_factor_only_for_canard_layout():
    """常规布局为 1；鸭式为 1 + 0.5·Sc/S。"""
    from utils.takeoff.takeoff_physics import calc_canard_lift_factor

    assert calc_canard_lift_factor('conventional', 4.9, 37.0) == pytest.approx(1.0)
    assert calc_canard_lift_factor('canard', 0.0, 37.0) == pytest.approx(1.0)
    assert calc_canard_lift_factor('canard', 4.9, 37.0) == pytest.approx(1.0 + 0.5 * 4.9 / 37.0)


def test_cl_alpha_with_canard_scales_helmbold():
    from utils.takeoff.takeoff_physics import calc_cl_alpha_with_canard

    ar, sweep = 2.6, 50.0
    eta = calc_oswald_e(ar, sweep)
    base = calc_cl_alpha(ar, eta, sweep)
    scaled = calc_cl_alpha_with_canard(ar, eta, sweep, 'canard', 4.9, 37.0)
    assert scaled == pytest.approx(base * (1.0 + 0.5 * 4.9 / 37.0))
